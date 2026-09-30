"""Download one accurately matched, freely licensed photograph per menu item."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")

BASE_DIR = Path(__file__).resolve().parent
MENU_PATH = BASE_DIR / "menu.json"
IMAGE_DIR = BASE_DIR / "food-images"
CREDITS_PATH = BASE_DIR / "FOOD_IMAGE_CREDITS.md"
STAGING_DIR = BASE_DIR / ".food-image-staging"
STAGING_MANIFEST = STAGING_DIR / "progress.json"
API_URL = "https://api.openverse.org/v1/images/"
USER_AGENT = "SVCECampusCanteen/1.0 (local canteen menu photography)"
MAX_IMAGE_BYTES = 20_000_000
MIN_IMAGE_BYTES = 2_000
API_PAUSE_SECONDS = 3.1
IMAGE_SCORE_THRESHOLD = 53

SEARCH_ALIASES = {
    "Idly": ["Idli"],
    "Vada": ["Medu Vada", "Vadai"],
    "Poori": ["Puri", "Indian puri"],
    "Upma": ["Upma South Indian", "Indian Upma"],
    "Chapathi": ["Chapati", "Roti"],
    "Pesarattu": ["Pesarattu dosa"],
    "Mysore Bonda": ["Mysuru Bonda", "Mysore Bajji", "Goli Baje"],
    "Pongal": ["Ven Pongal"],
    "Veg Meals": ["Vegetarian thali", "Vegetarian meals"],
    "Curd Rice with Pickle": ["Curd Rice"],
    "Paneer Biryani": ["Paneer Biriyani"],
    "Onion Samosa": ["Vengaia Samosa"],
    "Masala Peanuts": ["Congress Kadlekai"],
    "Chocolate Brownie": ["Chocolate brownie"],
    "Fried Rice": ["Fried rice dish"],
    "Sambar Rice": ["Sambar Rice", "Sambar sadam"],
    "Paneer Rice": ["Paneer Rice", "Paneer rice dish"],
    "Veg Biryani": ["Vegetarian biryani", "Veg biryani"],
    "Water Bottle": ["Water Bottle", "Bottled water"],
    "Water Bottle (1 L)": ["Bottled water", "One litre bottled water", "1 litre water bottle", "Water bottle"],
    "Sprite": ["Sprite soda", "Sprite drink"],
    "Coke": ["Coca-Cola", "Coca-Cola drink", "Coke drink"],
    "Fanta": ["Fanta orange soda", "Fanta"],
    "Lemon Juice": ["Nimbu pani", "Lemon juice drink"],
    "Milkshake": ["Vanilla milkshake"],
    "Buttermilk": ["Indian buttermilk drink", "Indian chaas"],
    "Punugulu": ["Punugulu food", "Punugulu"],
    "Bajji": ["Indian bajji"],
    "Pakoda": ["Pakora"],
    "French Fries": ["French fries"],
    "Veg Cutlet": ["Vegetable cutlet"],
    "Veg Puff": ["Veg Puff"],
    "Pasta": ["Pasta dish"],
    "Biscuits": ["Biscuit", "Biscuits snack"],
    "Manchurian": ["Gobi Manchurian"],
    "Ghee Podi Idly": ["Ghee podi idli", "Podi idli"],
    "Rava Dosa": ["Rava dosa"],
    "Onion Uttapam": ["Onion uttapam", "Onion uthappam"],
    "Aloo Paratha": ["Aloo paratha"],
    "Andhra Veg Thali": ["Andhra thali", "Indian vegetarian thali"],
    "Mango Lassi": ["Mango lassi"],
    "Fresh Lime Soda": ["Fresh Lime Soda", "Indian lime soda"],
    "Paneer Kathi Roll": ["Paneer kathi roll"],
    "Chicken Kathi Roll": ["Chicken kathi roll"],
    "Cheese Garlic Bread": ["Cheese garlic bread"],
    "Peri Peri Fries": ["Peri peri fries"],
    "Veg Momos": ["Vegetable momos"],
}

COMBINED_DISH_MARKERS = (" and ", " with ", " & ", " + ", " platter", " combo")
IRRELEVANT_CONTEXT = {
    "beach", "sunrise", "sunset", "festival", "harvest", "wedding", "honeymoon", "honey moon",
    "selfie", "portrait", "blurry", "cocktail", "gin", "vodka", "whiskey",
    "whisky", "beer", "wine", "pub", "bento", "sanza", "sorghum", "flower", "flowers",
    "botanical", "plant", "plants", "machine", "mla", "salad",
}
OTHER_DISH_WORDS = {
    "vada", "vadai", "wada", "idly", "idli", "dosa", "uttapam", "uthappam", "upma",
    "poori", "puri", "samosa", "biryani", "noodles", "burger", "pizza",
    "sandwich", "pasta", "manchurian", "pulao", "paratha", "momo", "momos",
    "cutlet", "pakoda", "pakora", "bajji", "lassi", "milkshake", "shake", "wada",
    "sundae",
}
OTHER_DISH_PHRASES = {"ice cream"}
REFRESH_IMAGE_IDS = {70, 71, 72, 74, 77}
OTHER_PRODUCT_WORDS = {"sprite", "coke", "cola", "fanta", "pepsi"}
DIETARY_CONFLICTS = {
    "non veg", "non vegetarian", "chicken", "beef", "pork", "fish", "mutton",
    "lamb", "meat",
}
MEAT_WORDS = {"chicken", "beef", "pork", "fish", "mutton", "lamb", "meat"}
REJECTED_SOURCE_IDS = {
    1: {"4c89e3d3-e59a-4b77-8c1e-a511daaed1ed"},
    9: {
        "b1f27d00-80a3-45f9-a29f-9db38ba4b445",
        "585ca9a2-b184-43f9-8ef9-551507c8ac1b",
    },
    19: {"7f3bf158-9912-4f84-b847-dbab28774021"},
    21: {"d81ee1d3-5ed2-4298-9d98-98597569135c"},
    20: {
        "915faa7d-a49b-47e4-adc8-38d9c81b2824",
        "c91ee2b2-e444-449a-a2fe-9b5f47910bb1",
    },
    23: {"53814488-57cd-4d9c-8fdf-d313688e7fe7"},
    37: {"074b4740-7092-4a50-bd62-2a071b924857"},
    39: {"674b8c03-a316-4cfd-841e-39f5a81d8e2c"},
    70: {"d81ee1d3-5ed2-4298-9d98-98597569135c"},
    71: {"0530ea16-36f9-4601-ac2a-a31ea8cbed1b"},
    72: {"e2f91351-22c1-4a6b-96c6-351b0c80ba38"},
}
MANUAL_PHOTO_OVERRIDES = {
    9: {
        "id": "commons-16998436",
        "title": "Pesarattu",
        "url": "https://upload.wikimedia.org/wikipedia/commons/6/6c/Pesarattu.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Pesarattu.jpg",
        "creator": "Ryallabandi",
        "license": "by-sa",
        "license_version": "3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "_match_score": 160,
    },
    19: {
        "id": "commons-40681816",
        "title": "Sambar Rice",
        "url": "https://upload.wikimedia.org/wikipedia/commons/6/64/Sambar_Rice.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Sambar_Rice.jpg",
        "creator": "Rashmiwalia85",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    20: {
        "id": "commons-40872114",
        "title": "Methi Paneer Rice",
        "url": "https://upload.wikimedia.org/wikipedia/commons/4/43/Methi_Paneer_Rice%21%21.JPG",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Methi_Paneer_Rice%21%21.JPG",
        "creator": "Sachinchati",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    37: {
        "id": "commons-153080424",
        "title": "Spring roll 5",
        "url": "https://upload.wikimedia.org/wikipedia/commons/b/b4/Spring_roll_5.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Spring_roll_5.jpg",
        "creator": "Gannu03",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    39: {
        "id": "commons-143549276",
        "title": "Biscuit 3",
        "url": "https://upload.wikimedia.org/wikipedia/commons/e/e0/Biscuit_3.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Biscuit_3.jpg",
        "creator": "Harpreet 712",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    61: {
        "id": "commons-paneer-biriyani-02",
        "title": "Paneer Biriyani 02",
        "url": "https://upload.wikimedia.org/wikipedia/commons/c/cc/Paneer_Biriyani_02.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Paneer_Biriyani_02.jpg",
        "creator": "Vis M",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    65: {
        "id": "commons-vengaia-samosa",
        "title": "Vengaia Samosa",
        "url": "https://upload.wikimedia.org/wikipedia/commons/0/02/Vengaia_Samosa-_Coimbatore-_Tamil_Nadu.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Vengaia_Samosa-_Coimbatore-_Tamil_Nadu.jpg",
        "creator": "Lohith Aswa M",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    67: {
        "id": "commons-congress-kadlekai",
        "title": "Congress Kadlekai",
        "url": "https://upload.wikimedia.org/wikipedia/commons/b/ba/Congress_Kadlekai.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Congress_Kadlekai.jpg",
        "creator": "Chindeep87",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    69: {
        "id": "commons-chocolate-brownie-2",
        "title": "Chocolate brownie 2",
        "url": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Chocolate_brownie_2.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Chocolate_brownie_2.jpg",
        "creator": "Roozitaa",
        "license": "by-sa",
        "license_version": "3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0",
        "_match_score": 160,
    },
    70: {
        "id": "commons-bottled-water",
        "title": "Bottled water",
        "url": "https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b1/Bottled_water.jpg/960px-Bottled_water.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Bottled_water.jpg",
        "creator": "H.A.W.C 101",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    71: {
        "id": "commons-dark-chocolate-milkshake",
        "title": "Dark chocolate milkshake, Bengaluru (2026)",
        "url": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/61/Dark_chocolate_milkshake%2C_Bengaluru_%282026%29.jpg/960px-Dark_chocolate_milkshake%2C_Bengaluru_%282026%29.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Dark_chocolate_milkshake,_Bengaluru_(2026).jpg",
        "creator": "Gpkp",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
    72: {
        "id": "9a5e7575-2106-489c-886d-9c2908060e3e",
        "title": "Strawberry Milkshake",
        "url": "https://live.staticflickr.com/1283/4675313359_38d6e6d55e_b.jpg",
        "foreign_landing_url": "https://www.flickr.com/photos/92945296@N00/4675313359",
        "creator": "Vancouver Bites!",
        "license": "by-sa",
        "license_version": "2.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/2.0/",
        "_match_score": 160,
    },
    74: {
        "id": "0a25dfcc-d170-4319-af6a-5f98ad434ca5",
        "title": "Fresh Lime Soda",
        "url": "https://live.staticflickr.com/5212/5529876021_f5ea181cda_b.jpg",
        "foreign_landing_url": "https://www.flickr.com/photos/84539227@N00/5529876021",
        "creator": "reivax",
        "license": "by-sa",
        "license_version": "2.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/2.0/",
        "_match_score": 160,
    },
    77: {
        "id": "commons-cheese-garlic-bread",
        "title": "Cheese Garlic Bread",
        "url": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d7/Cheese_Garlic_Bread.jpg/960px-Cheese_Garlic_Bread.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Cheese_Garlic_Bread.jpg",
        "creator": "Saisumanth532",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "_match_score": 160,
    },
}
SPECIFIC_MODIFIERS = {
    "masala", "rava", "rawa", "ghee", "podi", "onion", "egg", "chicken",
    "veg", "cheese", "butter", "plain", "spicy", "peri", "chocolate",
    "strawberry", "mango", "orange",
}
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def score_photo_match(name: str, aliases: list[str], result: dict[str, Any]) -> int:
    """Prefer single-dish photos and reject misleading word-only image hits."""
    title = result.get("title") or ""
    title_normalized = f" {normalize(title)} "
    title_words = set(normalize(title).split())
    tags = {normalize(tag.get("name", "")) for tag in result.get("tags", [])}
    tags_words = set(" ".join(tags).split())
    normalized_name = normalize(name)
    target_words = set(normalized_name.split())
    for alias in aliases:
        target_words.update(normalize(alias).split())

    score = 0
    for search_name in [normalized_name, *(normalize(alias) for alias in aliases)]:
        name_words = search_name.split()
        if not name_words:
            continue
        matched = sum(word in title_words for word in name_words)
        variant_score = round(72 * matched / len(name_words))
        if matched == len(name_words):
            variant_score += 30 if search_name == normalized_name else 14
        if f" {search_name} " in title_normalized:
            variant_score += 20 if search_name == normalized_name else 12
        unmatched_modifiers = (SPECIFIC_MODIFIERS & title_words) - target_words
        variant_score -= min(52, 26 * len(unmatched_modifiers))
        score = max(score, variant_score)

    for search_name in [normalized_name, *(normalize(alias) for alias in aliases)]:
        tag_words = search_name.split()
        if tag_words and all(any(word in tag for tag in tags) for word in tag_words):
            score += 16
            break
    if any(
        marker in f" {title.casefold()} "
        and marker not in f" {name.casefold()} "
        for marker in COMBINED_DISH_MARKERS
    ):
        score -= 100
    if any(f" {phrase} " in title_normalized for phrase in OTHER_DISH_PHRASES):
        score -= 100
    other_dishes = (OTHER_DISH_WORDS & (title_words | tags_words)) - target_words
    score -= min(120, 70 * len(other_dishes))
    other_products = (OTHER_PRODUCT_WORDS & (title_words | tags_words)) - target_words
    score -= min(120, 60 * len(other_products))
    context = f"{title_normalized} {' '.join(tags_words)}"
    if any(normalize(marker) in context for marker in IRRELEVANT_CONTEXT):
        score -= 120
    item_words = set(normalize(name).split())
    forbidden_meat = (MEAT_WORDS & (title_words | tags_words)) - item_words
    if forbidden_meat or (
        name.lower().startswith(("veg ", "vegetarian "))
        and any(normalize(marker) in context for marker in DIETARY_CONFLICTS)
    ):
        score -= 100
    return score


def search_photos(name: str, aliases: list[str], used_ids: set[str]) -> list[dict[str, Any]]:
    query = aliases[0] if aliases else name
    params = urllib.parse.urlencode(
        {
            "q": query,
            "page_size": 20,
            "license": "cc0,pdm,by,by-sa",
            "extension": "jpg",
        }
    )
    request = urllib.request.Request(
        f"{API_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )

    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 4:
                raise RuntimeError(f"Openverse photo search failed for {name}: HTTP {error.code}") from error
            try:
                delay = float(error.headers.get("Retry-After", "2"))
            except ValueError:
                delay = 2.0
            time.sleep(min(max(delay, 2.0 * (attempt + 1)), 20.0))
        except (TimeoutError, urllib.error.URLError) as error:
            if attempt == 4:
                raise RuntimeError(f"Openverse photo search failed for {name}: {error}") from error
            time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"Openverse did not return a photo search result for {name}.")

    normalized_name = normalize(name)
    ranked = []
    for result in payload.get("results", []):
        result_id = result.get("id")
        if not result_id or result_id in used_ids or not result.get("url"):
            continue
        result["_match_score"] = score_photo_match(name, aliases, result)
        ranked.append(result)
    ranked.sort(key=lambda result: result["_match_score"], reverse=True)
    time.sleep(API_PAUSE_SECONDS)
    return ranked


def download_photo(result: dict[str, Any]) -> tuple[bytes, str]:
    request = urllib.request.Request(result["url"], headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                data = response.read(MAX_IMAGE_BYTES + 1)
            if content_type not in IMAGE_EXTENSIONS:
                raise RuntimeError(f"Openverse returned an unsupported photo format: {content_type}.")
            if len(data) > MAX_IMAGE_BYTES:
                raise RuntimeError("The selected image is larger than 20 MB.")
            if len(data) < MIN_IMAGE_BYTES:
                raise RuntimeError("The selected photo download is incomplete.")
            return data, content_type
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 3:
                raise RuntimeError(f"Could not download the selected food photo: HTTP {error.code}") from error
            time.sleep(min(2.0 * (attempt + 1), 10.0))
        except (TimeoutError, urllib.error.URLError) as error:
            if attempt == 3:
                raise RuntimeError(f"Could not download the selected food photo: {error}") from error
            time.sleep(attempt + 1)
    raise RuntimeError("The selected food photo could not be downloaded.")


def creator_name(result: dict[str, Any]) -> str:
    value = re.sub(r"<[^>]*>", "", result.get("creator") or "Unknown creator")
    return value.replace("&amp;", "&").strip() or "Unknown creator"


def cached_menu_photo(
    item: dict[str, Any],
) -> tuple[dict[str, Any], bytes, str, str] | None:
    image = item.get("image")
    if not isinstance(image, str) or not image.startswith("/food-images/"):
        return None
    filename = image.removeprefix("/food-images/")
    if not filename or Path(filename).name != filename:
        return None
    image_path = IMAGE_DIR / filename
    if not image_path.is_file() or image_path.resolve().parent != IMAGE_DIR.resolve():
        return None

    content_type = next(
        (mime for mime, extension in IMAGE_EXTENSIONS.items() if image_path.suffix == extension),
        None,
    )
    if content_type is None:
        return None
    title = item.get("imageTitle")
    creator = item.get("imageCreator")
    source_url = item.get("imageSourceUrl")
    license_label = item.get("imageLicense")
    if not all(isinstance(value, str) and value for value in (title, creator, source_url, license_label)):
        return None

    license_parts = license_label.lower().removeprefix("cc ").split()
    license_code = license_parts[0]
    license_version = license_parts[1] if len(license_parts) > 1 else None
    if license_code == "cc0":
        license_url = "https://creativecommons.org/publicdomain/zero/1.0/"
    elif license_code == "pdm":
        license_url = "https://creativecommons.org/publicdomain/mark/1.0/"
    elif license_code in {"by", "by-sa"} and license_version:
        license_url = f"https://creativecommons.org/licenses/{license_code}/{license_version}/"
    else:
        raise ValueError(f"Unsupported cached photo license for menu item {item['id']}: {license_label}.")

    image_bytes = image_path.read_bytes()
    result = {
        "id": f"existing-local-{item['id']}",
        "title": title,
        "foreign_landing_url": source_url,
        "creator": creator,
        "license": license_code,
        "license_version": license_version,
        "license_url": license_url,
        "_match_score": score_photo_match(
            item["name"], SEARCH_ALIASES.get(item["name"], []), {"title": title}
        ),
    }
    if result["_match_score"] < IMAGE_SCORE_THRESHOLD:
        return None
    return result, image_bytes, content_type, hashlib.sha256(image_bytes).hexdigest()


def build_gallery() -> None:
    with MENU_PATH.open(encoding="utf-8") as menu_file:
        menu = json.load(menu_file)
    if not isinstance(menu, list) or not menu:
        raise ValueError("menu.json must contain menu items before generating the gallery.")

    prepared: list[tuple[dict[str, Any], dict[str, Any], bytes, str, str]] = []
    used_ids: set[str] = set()
    used_hashes: set[str] = set()
    STAGING_DIR.mkdir(exist_ok=True)
    if STAGING_MANIFEST.exists():
        with STAGING_MANIFEST.open(encoding="utf-8") as manifest_file:
            staging_manifest = json.load(manifest_file)
    else:
        staging_manifest = {}
    if not isinstance(staging_manifest, dict):
        raise ValueError(f"{STAGING_MANIFEST} is not a valid photo progress manifest.")

    for index, item in enumerate(menu, start=1):
        name = item["name"]
        existing = staging_manifest.get(str(item["id"]))
        existing_source = existing.get("source") if isinstance(existing, dict) else None
        existing_extension = existing.get("extension") if isinstance(existing, dict) else None
        staged_photo = (
            STAGING_DIR / f"{item['id']}{existing_extension}"
            if isinstance(existing_extension, str) else None
        )
        if (
            isinstance(existing, dict)
            and existing.get("name") == name
            and isinstance(existing_source, dict)
            and existing_source.get("id") not in used_ids
            and existing_source.get("id") not in REJECTED_SOURCE_IDS.get(item["id"], set())
            and item["id"] not in REFRESH_IMAGE_IDS
            and score_photo_match(
                name, SEARCH_ALIASES.get(name, []), existing_source
            ) >= IMAGE_SCORE_THRESHOLD
            and staged_photo is not None
            and staged_photo.is_file()
        ):
            result = existing_source
            image_bytes = staged_photo.read_bytes()
            content_type = existing["content_type"]
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            if image_hash in used_hashes:
                raise ValueError(f"Duplicate photo data found in staged menu item {item['id']} ({name}).")
            print(f"[{index:02}/{len(menu):02}] {name}: reusing its verified photo")
        elif item["id"] not in REFRESH_IMAGE_IDS and (cached := cached_menu_photo(item)):
            result, image_bytes, content_type, image_hash = cached
            if result["id"] in used_ids or image_hash in used_hashes:
                raise ValueError(f"Duplicate photo data found in existing menu item {item['id']} ({name}).")
            print(f"[{index:02}/{len(menu):02}] {name}: reusing its verified local photo")
        else:
            manual_photo = MANUAL_PHOTO_OVERRIDES.get(item["id"])
            candidates = (
                [{**manual_photo}]
                if manual_photo
                else search_photos(name, SEARCH_ALIASES.get(name, []), used_ids)
            )
            selected = None
            failure_details = "no matching, freely licensed photograph was returned"
            for result in candidates:
                if result["_match_score"] < IMAGE_SCORE_THRESHOLD:
                    break
                try:
                    image_bytes, content_type = download_photo(result)
                except RuntimeError as error:
                    failure_details = str(error)
                    continue
                image_hash = hashlib.sha256(image_bytes).hexdigest()
                if image_hash in used_hashes:
                    continue
                selected = (result, image_bytes, content_type, image_hash)
                break
            if selected is None:
                top_match = candidates[0] if candidates else None
                detail = (
                    f"Best match was '{top_match.get('title')}' (score {top_match['_match_score']}). "
                    if top_match else ""
                )
                raise RuntimeError(
                    f"Could not find a unique, sufficiently accurate licensed photo for "
                    f"menu item {item['id']} ({name}). {detail}{failure_details} "
                    f"Successfully matched photos are saved in {STAGING_DIR}; correct the query and rerun."
                )
            result, image_bytes, content_type, image_hash = selected
            extension = IMAGE_EXTENSIONS[content_type]
            staged_photo = STAGING_DIR / f"{item['id']}{extension}"
            staged_photo.write_bytes(image_bytes)
            source_manifest = {
                key: result.get(key)
                for key in (
                    "id", "title", "url", "foreign_landing_url", "creator",
                    "creator_url", "license", "license_version", "license_url", "_match_score",
                )
            }
            staging_manifest[str(item["id"])] = {
                "name": name,
                "content_type": content_type,
                "extension": extension,
                "source": source_manifest,
            }
            manifest_tmp = STAGING_DIR / "progress.tmp"
            manifest_tmp.write_text(
                json.dumps(staging_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(manifest_tmp, STAGING_MANIFEST)
            print(
                f"[{index:02}/{len(menu):02}] {name}: {result['title']} "
                f"(score {result['_match_score']}, {result['license']})"
            )
        used_ids.add(result["id"])
        used_hashes.add(image_hash)
        prepared.append((item, result, image_bytes, content_type, image_hash))

    with tempfile.TemporaryDirectory(prefix="canteen-gallery-", dir=BASE_DIR) as staging_folder:
        staging_dir = Path(staging_folder)
        credits = [
            "# SVCE Canteen Food Photo Credits",
            "",
            "Every food photo is individually matched to its menu item and served from the local `food-images/` folder. "
            "Photos are sourced through [Openverse](https://openverse.org/) and [Wikimedia Commons](https://commons.wikimedia.org/) and each file is used under its stated "
            "license. Follow the linked source for the original image, creator, and full license terms.",
            "",
            "| Item | Photo | Creator | License | Local file |",
            "|---|---|---|---|---|",
        ]
        for item, result, image_bytes, content_type, _image_hash in prepared:
            extension = IMAGE_EXTENSIONS[content_type]
            image_filename = f"{item['id']}{extension}"
            (staging_dir / image_filename).write_bytes(image_bytes)
            source_url = result.get("foreign_landing_url") or result["detail_url"]
            license_name = f"CC {result['license'].upper()} {result.get('license_version') or ''}".strip()
            creator = creator_name(result)
            item["image"] = f"/food-images/{image_filename}"
            item["imageTitle"] = result.get("title") or item["name"]
            item["imageCreator"] = creator
            item["imageLicense"] = license_name
            item["imageSourceUrl"] = source_url
            markdown_title = item["imageTitle"].replace("|", "\\|")
            markdown_name = item["name"].replace("|", "\\|")
            markdown_creator = creator.replace("|", "\\|")
            credits.append(
                f"| {markdown_name} | [{markdown_title}]({source_url}) | {markdown_creator} "
                f"| [{license_name}]({result['license_url']}) | `food-images/{image_filename}` |"
            )

        staged_menu = staging_dir / "menu.json"
        staged_menu.write_text(json.dumps(menu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged_credits = staging_dir / "FOOD_IMAGE_CREDITS.md"
        staged_credits.write_text("\n".join(credits) + "\n", encoding="utf-8")

        IMAGE_DIR.mkdir(exist_ok=True)
        for item, _result, _data, content_type, _image_hash in prepared:
            filename = f"{item['id']}{IMAGE_EXTENSIONS[content_type]}"
            os.replace(staging_dir / filename, IMAGE_DIR / filename)
        os.replace(staged_menu, MENU_PATH)
        os.replace(staged_credits, CREDITS_PATH)

    try:
        shutil.rmtree(STAGING_DIR)
    except PermissionError as error:
        print(f"Gallery is complete, but could not remove its staging folder: {error}")
    print(f"\nSaved {len(prepared)} unique, individually credited food photos to {IMAGE_DIR}.")
    print(f"Photo credits saved to {CREDITS_PATH}.")


if __name__ == "__main__":
    build_gallery()
