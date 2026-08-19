"""One-time download of cosmetic listing photos from Picsum Lorem Photos
(picsum.photos) -- free-to-use, no API key/account required, deterministic
per-listing via seeded URLs (https://picsum.photos/seed/<seed>/<w>/<h>) so
the same "hotel photo" stays stable across runs.

Purely decorative: these files are referenced by the UI only and are never
read by, or passed as input to, any agent's reasoning.

Usage: python travel_booking/scripts/fetch_images.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
IMAGES_DIR = DATA_DIR / "images"

WIDTH, HEIGHT = 800, 600


def _download(seed: str, dest: Path) -> None:
    if dest.exists():
        print(f"  skip (exists): {dest.name}")
        return
    url = f"https://picsum.photos/seed/{seed}/{WIDTH}/{HEIGHT}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"  saved: {dest.name} ({len(resp.content)} bytes)")
    time.sleep(0.2)


def main() -> None:
    hotels = json.loads((DATA_DIR / "hotels.json").read_text())
    flights = json.loads((DATA_DIR / "flights.json").read_text())

    (IMAGES_DIR / "hotels").mkdir(parents=True, exist_ok=True)
    (IMAGES_DIR / "flights").mkdir(parents=True, exist_ok=True)

    print(f"Fetching {len(hotels)} hotel images...")
    for h in hotels:
        _download(h["image_seed"], IMAGES_DIR / "hotels" / f"{h['id']}.jpg")

    print(f"Fetching {len(flights)} flight images...")
    for f in flights:
        _download(f["image_seed"], IMAGES_DIR / "flights" / f"{f['id']}.jpg")

    print("Done.")


if __name__ == "__main__":
    main()
