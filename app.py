"""Vercel-compatible Flask entrypoint for the SVCE campus canteen."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import BadRequest

if os.environ.get("VERCEL") == "1":
    os.environ.setdefault("CANTEEN_DB_PATH", "/tmp/canteen.db")

from server import (
    BASE_DIR,
    DB_PATH,
    MENU,
    create_order,
    get_food_image,
    initialize_database,
)

app = Flask(__name__)
MAX_REQUEST_BYTES = 32_768
STATIC_FILES = {
    "style.css",
    "script.js",
    "canteen-logo.svg",
    "food-placeholder.svg",
    "FOOD_IMAGE_CREDITS.md",
}


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/menu")
def get_menu():
    return jsonify({"items": MENU})


@app.get("/api/menu/<int:item_id>/image")
def get_menu_image(item_id: int):
    image = get_food_image(item_id)
    if not image:
        return jsonify({"error": "A photo for this menu item has not been added yet."}), 404
    response = app.response_class(image[0], mimetype=image[1])
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/orders")
def post_order():
    if request.content_length is None or request.content_length < 1:
        return jsonify({"error": "The order request is empty."}), 400
    if request.content_length > MAX_REQUEST_BYTES:
        return jsonify({"error": "The order request is too large."}), 413
    try:
        payload: Any = request.get_json()
    except BadRequest:
        return jsonify({"error": "Send valid JSON to create an order."}), 400
    try:
        initialize_database(DB_PATH)
        bill = create_order(payload, DB_PATH)
    except (ValueError, TypeError) as error:
        return jsonify({"error": str(error)}), 400
    except sqlite3.Error:
        logging.exception("Unable to save the canteen order.")
        return jsonify({"error": "The order could not be saved. Please try again."}), 500
    return jsonify({"bill": bill}), 201


@app.get("/<path:filename>")
def static_file(filename: str):
    if filename in STATIC_FILES:
        return send_from_directory(BASE_DIR, filename)
    image = re.fullmatch(r"food-images/([1-9][0-9]*)\.jpg", filename)
    if image and (BASE_DIR / filename).is_file():
        response = send_from_directory(BASE_DIR, filename)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
    return jsonify({"error": "File not found."}), 404
