# SVCE Campus Canteen

A Python-powered campus canteen menu, order calculator, and printable bill generator. The local HTTP server uses only the Python standard library and SQLite; the Vercel deployment uses a Flask entrypoint.

## Run locally

1. Install Python 3.10 or newer.
2. Double-click `start.bat`, or open a terminal in this project folder and run:

   ```powershell
   python server.py
   ```

3. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. Keep the terminal open while using the app; press `Ctrl+C` to stop the server.

The server creates `canteen.db` in the project folder on first start. `menu.json` contains the editable menu, prices, and an individual food-photo credit for each item. Each menu card has its own locally stored image under `food-images/`, so once the photos have been added, the menu no longer depends on an external image service. The SVCE Canteen logo and a food-photo fallback illustration are provided as local SVG files.

To find and download individually matched, openly licensed photos for the entire current menu, run:

```powershell
python fetch_food_images.py
```

This operation requires internet access. It downloads unique image files, stores their license and creator attribution in `FOOD_IMAGE_CREDITS.md`, and adds photo and attribution data to `menu.json`. Photos are sourced from Openverse and Wikimedia Commons; individual photo credits are also linked from each menu card.

## Deploy to Vercel

Import this project from GitHub in the Vercel dashboard. Vercel detects `app.py` as the Flask Python entrypoint and installs Flask from `requirements.txt`. The Python app serves the page, API, and local images.

Vercel's writable `/tmp` storage is temporary and isolated to a function instance. Deployed orders can generate bills, but order history is not durable or shared across instances. Local runs continue to use `canteen.db` and preserve orders. Do not add `canteen.db` to Git; it is excluded in `.gitignore`.

## Orders and bills

Add menu items to your bag, adjust quantities, and enter a name and payment method. The server validates the current catalog prices and quantities, calculates each line total, and saves the order in SQLite. Orders with a subtotal of ₹250 or more receive the automatic 5% Campus Saver discount. The confirmed bill includes a unique order number and can be printed or saved as a PDF from the browser.

For a different host or port, set `CANTEEN_HOST` or `CANTEEN_PORT` before starting the server. `CANTEEN_DB_PATH` can point to a different SQLite database file.

## Run the tests

```powershell
python -m unittest -v
```
