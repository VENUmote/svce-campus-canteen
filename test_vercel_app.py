import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app


class VercelAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "orders.sqlite3"
        self.client = app.test_client()
        self.database_patch = patch("app.DB_PATH", self.database)
        self.database_patch.start()

    def tearDown(self):
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    def test_serves_menu_assets_and_only_valid_local_images(self):
        menu_response = self.client.get("/api/menu")
        menu = menu_response.get_json()["items"]

        self.assertEqual(menu_response.status_code, 200)
        self.assertEqual(len(menu), 79)
        self.assertEqual(len({item["image"] for item in menu}), 79)
        for path in ("/", "/script.js", "/food-images/5.jpg"):
            with self.subTest(path=path), self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/canteen.db").status_code, 404)
        self.assertEqual(self.client.get("/food-images/999.jpg").status_code, 404)

    def test_generates_authoritative_receipt_and_rejects_bad_requests(self):
        payload = {
            "customerName": "Aanya",
            "studentId": "23A91A",
            "paymentMethod": "UPI",
            "items": [{"id": 11, "quantity": 2}],
        }

        response = self.client.post("/api/orders", json=payload)
        bill = response.get_json()["bill"]

        self.assertEqual(response.status_code, 201)
        self.assertEqual((bill["subtotal"], bill["discount"], bill["total"]), (160, 0, 160))
        self.assertRegex(bill["orderNumber"], r"^SVCE-\d{8}-\d{6}-[A-F0-9]{8}$")
        self.assertEqual(self.client.post("/api/orders", data="{", content_type="application/json").status_code, 400)
        self.assertEqual(
            self.client.post(
                "/api/orders",
                data=json.dumps({**payload, "items": [{"id": 11, "quantity": 21}]}),
                content_type="application/json",
            ).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
