import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fetch_food_images import IMAGE_SCORE_THRESHOLD, score_photo_match
from server import CanteenRequestHandler, calculate_bill, create_order, get_food_image, initialize_database


class BillCalculationTests(unittest.TestCase):
    def test_calculates_line_totals_and_campus_saver_at_threshold(self):
        bill = calculate_bill([{"id": 11, "quantity": 2}, {"id": 21, "quantity": 5}])

        self.assertEqual(bill["subtotal"], 260)
        self.assertEqual(bill["discount"], 13)
        self.assertEqual(bill["total"], 247)
        self.assertEqual([item["lineTotal"] for item in bill["items"]], [160, 100])

    def test_does_not_apply_campus_saver_below_threshold(self):
        bill = calculate_bill([{"id": 11, "quantity": 3}])

        self.assertEqual((bill["subtotal"], bill["discount"], bill["total"]), (240, 0, 240))

    def test_new_drink_items_are_billable_from_the_expanded_menu(self):
        bill = calculate_bill([{"id": 70, "quantity": 1}, {"id": 71, "quantity": 4}])

        self.assertEqual([item["name"] for item in bill["items"]], ["Water Bottle (1 L)", "Chocolate Milkshake"])
        self.assertEqual((bill["subtotal"], bill["discount"], bill["total"]), (310, 16, 294))

    def test_rejects_invalid_or_manipulated_items(self):
        for items in (
            [],
            [{"id": 999, "quantity": 1}],
            [{"id": 11, "quantity": 21}],
            [{"id": 11, "quantity": True}],
            [{"id": [], "quantity": 1}],
            [{"id": 11, "quantity": 1}, {"id": 11, "quantity": 1}],
        ):
            with self.subTest(items=items), self.assertRaises(ValueError):
                calculate_bill(items)

    def test_photo_matcher_selects_the_dish_not_keyword_lookalikes(self):
        aliases = ["Idli"]
        standalone_idli = {
            "title": "Steamed Idli",
            "tags": [{"name": tag} for tag in ("food", "idli", "indian")],
        }
        tamil_flower = {
            "title": "Ixora coccinea - Idly poo in Tamil",
            "tags": [{"name": tag} for tag in ("flower", "idlypoo", "ixora")],
        }
        plate_with_vada = {
            "title": "Idli with Sambar and Vada",
            "tags": [{"name": tag} for tag in ("food", "idli", "vada")],
        }

        self.assertGreaterEqual(score_photo_match("Idly", aliases, standalone_idli), IMAGE_SCORE_THRESHOLD)
        self.assertLess(score_photo_match("Idly", aliases, tamil_flower), IMAGE_SCORE_THRESHOLD)
        self.assertGreater(
            score_photo_match("Idly", aliases, standalone_idli),
            score_photo_match("Idly", aliases, plate_with_vada),
        )
        self.assertLess(
            score_photo_match("Veg Meals", ["Vegetarian thali"], {"title": "South Indian non-veg meals"}),
            IMAGE_SCORE_THRESHOLD,
        )
        for name, title in (
            ("Onion Samosa", "Aloo Bonda, Samosa & Onion Bhaji"),
            ("Masala Peanuts", "Vegetable tikka masala, peanuts, and chili with wild rice"),
            ("Chocolate Brownie", "Vegan Double Chocolate Brownie Chunk Ice Cream"),
        ):
            with self.subTest(name=name):
                self.assertLess(
                    score_photo_match(name, [], {"title": title}),
                    IMAGE_SCORE_THRESHOLD,
                )

    def test_persists_order_and_generates_a_unique_receipt_number(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "orders.sqlite3"
            initialize_database(database)
            request = {
                "customerName": "Aanya",
                "studentId": "23A91A",
                "paymentMethod": "UPI",
                "items": [{"id": 1, "quantity": 2}],
            }

            first = create_order(request, database)
            second = create_order(request, database)

            self.assertNotEqual(first["orderNumber"], second["orderNumber"])
            self.assertEqual(first["total"], 60)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 2)

    def test_rejects_non_string_payment_methods(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "orders.sqlite3"
            initialize_database(database)
            payload = {
                "customerName": "Aanya",
                "paymentMethod": [],
                "items": [{"id": 1, "quantity": 1}],
            }

            with self.assertRaisesRegex(ValueError, "Cash or UPI"):
                create_order(payload, database)


class OrderEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temp_directory.name) / "api.sqlite3"
        initialize_database(cls.database)
        handler = type("TestCanteenHandler", (CanteenRequestHandler,), {"db_path": cls.database})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.temp_directory.cleanup()

    def test_menu_api_returns_a_unique_local_photo_for_every_menu_item(self):
        with urlopen(f"{self.base_url}/api/menu") as response:
            result = json.load(response)

        self.assertEqual(len(result["items"]), 79)
        image_paths = [item["image"] for item in result["items"]]
        self.assertEqual(len(set(image_paths)), 79)
        self.assertTrue(all(image.startswith("/food-images/") for image in image_paths))
        self.assertTrue(all(item.get("imageSourceUrl") for item in result["items"]))
        self.assertEqual(
            {category: sum(item["category"] == category for item in result["items"]) for category in (
                "tiffins", "lunch", "snacks", "cooldrinks", "fastfood"
            )},
            {"tiffins": 17, "lunch": 16, "snacks": 16, "cooldrinks": 15, "fastfood": 15},
        )
        drinks = {item["name"] for item in result["items"] if item["category"] == "cooldrinks"}
        self.assertTrue({"Water Bottle", "Water Bottle (1 L)", "Milkshake", "Chocolate Milkshake"} <= drinks)

    def test_poori_and_idly_have_separate_food_images_and_real_image_endpoint(self):
        with urlopen(f"{self.base_url}/api/menu") as response:
            menu = json.load(response)["items"]
        idly = next(item for item in menu if item["name"] == "Idly")
        poori = next(item for item in menu if item["name"] == "Poori")

        self.assertNotEqual(idly["image"], poori["image"])
        for item in (idly, poori):
            with urlopen(f"{self.base_url}/api/menu/{item['id']}/image") as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.headers["Content-Type"].startswith("image/"))
                self.assertGreater(len(response.read()), 2_000)
        self.assertIsNone(get_food_image(999999))

    def test_order_api_returns_authoritative_receipt_and_rejects_bad_quantity(self):
        payload = json.dumps({
            "customerName": "Aanya",
            "studentId": "",
            "paymentMethod": "Cash",
            "items": [{"id": 11, "quantity": 4}],
        }).encode()
        request = Request(
            f"{self.base_url}/api/orders",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            bill = json.load(response)["bill"]
            self.assertEqual(response.status, 201)

        self.assertEqual(bill["subtotal"], 320)
        self.assertEqual(bill["discount"], 16)
        self.assertEqual(bill["total"], 304)
        self.assertTrue(bill["orderNumber"].startswith("SVCE-"))

        invalid = Request(
            f"{self.base_url}/api/orders",
            data=json.dumps({
                "customerName": "Aanya",
                "paymentMethod": "Cash",
                "items": [{"id": 11, "quantity": 0}],
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(invalid)
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
