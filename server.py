"""Local Python web server and SQLite API for the SVCE campus canteen."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
MENU_PATH = BASE_DIR / "menu.json"
DB_PATH = Path(os.environ.get("CANTEEN_DB_PATH", BASE_DIR / "canteen.db"))
MAX_QUANTITY = 20
SAVER_MINIMUM = 250
SAVER_RATE_PERCENT = 5
MAX_REQUEST_BYTES = 32_768
CATEGORY_LABELS = {
    "tiffins": "Tiffins",
    "lunch": "Lunch",
    "cooldrinks": "Drinks",
    "snacks": "Snacks",
    "fastfood": "Fast food",
}
CATEGORY_DESCRIPTIONS = {
    "tiffins": "A freshly made South Indian favourite.",
    "lunch": "A comforting, freshly prepared campus meal.",
    "cooldrinks": "A refreshing sip for your campus break.",
    "snacks": "A tasty little something between classes.",
    "fastfood": "A satisfying made-to-order favourite.",
}
CATEGORY_IMAGES = {
    "tiffins": [
        "photo-1630383249896-424e482df921",
        "photo-1589302168068-964664d93dc0",
        "photo-1601050690597-df0568f70950",
        "photo-1567188040759-fb8a883dc6d8",
    ],
    "lunch": [
        "photo-1512621776951-a57141f2eefd",
        "photo-1546069901-ba9599a7e63c",
        "photo-1547592180-85f173990554",
        "photo-1512058564366-18510be2db19",
    ],
    "cooldrinks": [
        "photo-1556679343-c7306c1976bc",
        "photo-1544145945-f90425340c7e",
        "photo-1517701604599-bb29b565090c",
        "photo-1543255006-d6395b6f1171",
    ],
    "snacks": [
        "photo-1573080496219-bb080dd4f877",
        "photo-1601050690597-df0568f70950",
        "photo-1576107232684-1279f390859f",
        "photo-1565299624946-b28f40a0ae38",
    ],
    "fastfood": [
        "photo-1565299624946-b28f40a0ae38",
        "photo-1568901346375-23c9450c58cd",
        "photo-1569718212165-3a8278d5f624",
        "photo-1528735602780-2552fd46c7af",
    ],
}
PAYMENT_METHODS = {"Cash", "UPI"}


def load_menu() -> list[dict[str, Any]]:
    """Load the editable menu and enrich entries with presentation details."""
    with MENU_PATH.open(encoding="utf-8") as menu_file:
        source = json.load(menu_file)
    if not isinstance(source, list) or not source:
        raise ValueError("menu.json must contain a non-empty list of menu items.")

    items = []
    seen_ids = set()
    for item in source:
        if not isinstance(item, dict):
            raise ValueError("Every menu entry must be a JSON object.")
        item_id, name, category, price = (
            item.get("id"),
            item.get("name"),
            item.get("category"),
            item.get("price"),
        )
        if (
            isinstance(item_id, bool)
            or not isinstance(item_id, int)
            or item_id <= 0
            or item_id in seen_ids
            or not isinstance(name, str)
            or not name.strip()
            or not isinstance(category, str)
            or category not in CATEGORY_LABELS
            or isinstance(price, bool)
            or not isinstance(price, int)
            or price < 0
        ):
            raise ValueError(f"Invalid menu entry: {item!r}")
        seen_ids.add(item_id)
        image_ids = CATEGORY_IMAGES[category]
        image_id = image_ids[(item_id - 1) % len(image_ids)]
        items.append(
            {
                "id": item_id,
                "name": name.strip(),
                "category": category,
                "categoryLabel": CATEGORY_LABELS[category],
                "price": price,
                "description": CATEGORY_DESCRIPTIONS[category],
                "image": item.get("image", f"/food-images/{item_id}.jpg"),
                "imageTitle": item.get("imageTitle", name.strip()),
                "imageCreator": item.get("imageCreator", "SVCE Canteen"),
                "imageLicense": item.get("imageLicense", "Original illustration"),
                "imageSourceUrl": item.get("imageSourceUrl", ""),
            }
        )
    return items


MENU = load_menu()
MENU_BY_ID = {item["id"]: item for item in MENU}


def get_food_image(item_id: int) -> tuple[bytes, str] | None:
    """Return a validated local menu photo and its content type."""
    food = MENU_BY_ID.get(item_id)
    if not food:
        return None
    relative_image = food.get("image", "")
    if not isinstance(relative_image, str) or not relative_image.startswith("/food-images/"):
        return None
    image_path = (BASE_DIR / relative_image.lstrip("/")).resolve()
    food_images_dir = (BASE_DIR / "food-images").resolve()
    if image_path.parent != food_images_dir or image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        return None
    try:
        image_data = image_path.read_bytes()
    except FileNotFoundError:
        return None
    if not image_data or len(image_data) > 20_000_000:
        return None
    content_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }[image_path.suffix.lower()]
    return image_data, content_type


def calculate_bill(request_items: Any) -> dict[str, Any]:
    """Calculate line totals and the automatic Campus Saver deal in rupees."""
    if not isinstance(request_items, list) or not request_items:
        raise ValueError("Add at least one item before creating a bill.")
    if len(request_items) > len(MENU):
        raise ValueError(f"A bill cannot contain more than {len(MENU)} different items.")

    seen_ids: set[int] = set()
    lines = []
    subtotal = 0
    for requested in request_items:
        if not isinstance(requested, dict):
            raise ValueError("Each bill item must include an item ID and quantity.")
        item_id = requested.get("id")
        quantity = requested.get("quantity")
        if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id not in MENU_BY_ID:
            raise ValueError("The basket contains an item that is not on this menu.")
        if item_id in seen_ids:
            raise ValueError("Each menu item should appear only once in the basket.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QUANTITY:
            raise ValueError("Choose a quantity between 1 and 20 for each item.")

        seen_ids.add(item_id)
        food = MENU_BY_ID[item_id]
        line_total = food["price"] * quantity
        subtotal += line_total
        lines.append(
            {
                "id": item_id,
                "name": food["name"],
                "unitPrice": food["price"],
                "quantity": quantity,
                "lineTotal": line_total,
            }
        )

    discount = (subtotal * SAVER_RATE_PERCENT + 50) // 100 if subtotal >= SAVER_MINIMUM else 0
    return {
        "items": lines,
        "subtotal": subtotal,
        "discount": discount,
        "total": subtotal - discount,
    }


def initialize_database(db_path: Path = DB_PATH) -> None:
    """Create the persistent order tables if they do not already exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT UNIQUE,
                customer_name TEXT NOT NULL,
                student_id TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                subtotal INTEGER NOT NULL,
                discount INTEGER NOT NULL,
                total INTEGER NOT NULL,
                items_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def create_order(payload: Any, db_path: Path = DB_PATH) -> dict[str, Any]:
    """Validate a checkout, calculate its bill, and save it as an order."""
    if not isinstance(payload, dict):
        raise ValueError("Order details must be sent as a JSON object.")
    name = payload.get("customerName")
    student_id = payload.get("studentId", "")
    payment_method = payload.get("paymentMethod")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError("Enter your name (up to 80 characters) to create a bill.")
    if not isinstance(student_id, str) or len(student_id.strip()) > 40:
        raise ValueError("The student / staff ID must be 40 characters or fewer.")
    if not isinstance(payment_method, str) or payment_method not in PAYMENT_METHODS:
        raise ValueError("Choose Cash or UPI as your payment method.")

    bill = calculate_bill(payload.get("items"))
    created_at = datetime.now().astimezone()
    timestamp = created_at.strftime("%d %b %Y, %I:%M %p")
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.execute(
            """
            INSERT INTO orders (
                customer_name, student_id, payment_method, subtotal, discount,
                total, items_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                student_id.strip(),
                payment_method,
                bill["subtotal"],
                bill["discount"],
                bill["total"],
                json.dumps(bill["items"], ensure_ascii=False),
                created_at.isoformat(timespec="seconds"),
            ),
        )
        order_id = cursor.lastrowid
        order_number = f"SVCE-{created_at:%Y%m%d}-{order_id:06d}-{uuid.uuid4().hex[:8].upper()}"
        connection.execute(
            "UPDATE orders SET order_number = ? WHERE id = ?",
            (order_number, order_id),
        )
        connection.commit()

    return {
        "orderNumber": order_number,
        "customerName": name.strip(),
        "studentId": student_id.strip(),
        "paymentMethod": payment_method,
        "createdAt": timestamp,
        **bill,
    }


class CanteenRequestHandler(SimpleHTTPRequestHandler):
    """Serve the web app and its JSON menu and order APIs."""

    db_path = DB_PATH

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def send_json(self, status_code: int, body: dict[str, Any]) -> None:
        response = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/menu":
            self.send_json(200, {"items": MENU})
            return
        if path.startswith("/api/menu/") and path.endswith("/image"):
            item_id = path.removeprefix("/api/menu/").removesuffix("/image").strip("/")
            if not item_id.isdigit():
                self.send_json(400, {"error": "A valid menu item number is required."})
                return
            image = get_food_image(int(item_id))
            if not image:
                self.send_json(404, {"error": "A photo for this menu item has not been added yet."})
                return
            self.send_response(200)
            self.send_header("Content-Type", image[1])
            self.send_header("Content-Length", str(len(image[0])))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(image[0])
            return
        if path == "/api/health":
            self.send_json(200, {"status": "ok"})
            return
        if path.startswith("/api/"):
            self.send_json(404, {"error": "API endpoint not found."})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/orders":
            self.send_json(404, {"error": "API endpoint not found."})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "The request has an invalid content length."})
            return
        if content_length < 1 or content_length > MAX_REQUEST_BYTES:
            self.send_json(413, {"error": "The order request is empty or too large."})
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            bill = create_order(payload, self.db_path)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Send valid UTF-8 JSON to create an order."})
            return
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return
        except sqlite3.Error:
            logging.exception("Unable to save the canteen order.")
            self.send_json(500, {"error": "The order could not be saved. Please try again."})
            return
        self.send_json(201, {"bill": bill})


def run_server() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    initialize_database()
    host = os.environ.get("CANTEEN_HOST", "127.0.0.1")
    port = int(os.environ.get("CANTEEN_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), CanteenRequestHandler)
    print(f"SVCE Canteen is ready at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping the canteen server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
