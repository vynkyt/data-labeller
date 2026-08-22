"""
Seed script — creates a sample job with public image URLs and categories.

Usage:
    uv run python seed.py

Creates one job with 6 images and 4 categories. After running, open the
labeller page and you'll have tasks ready to label immediately.
"""

import urllib.request
import json

API_BASE = "http://localhost:8000"

SAMPLE_URLS = [
    "https://picsum.photos/seed/cat1/400/300",
    "https://picsum.photos/seed/dog2/400/300",
    "https://picsum.photos/seed/bird3/400/300",
    "https://picsum.photos/seed/car4/400/300",
    "https://picsum.photos/seed/food5/400/300",
    "https://picsum.photos/seed/nature6/400/300",
]

SAMPLE_CATEGORIES = ["animal", "vehicle", "food", "nature"]


def seed():
    data = json.dumps({
        "savedCats": SAMPLE_CATEGORIES,
        "savedUrls": SAMPLE_URLS,
        "client_id": "demo",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API_BASE}/createjob",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 200:
                print(f"Created demo job with {len(SAMPLE_URLS)} tasks")
                print(f"Categories: {', '.join(SAMPLE_CATEGORIES)}")
                print()
                print("Next steps:")
                print("  1. Open http://localhost:8000/labeller.html")
                print("  2. Enter your name and label tasks")
                print("  3. Open http://localhost:8000/qc.html to approve or relabel")
            else:
                print(f"Error: status {resp.status}")
    except urllib.error.URLError as e:
        print(f"Could not connect to {API_BASE}")
        print(f"Make sure the server is running: uv run uvicorn main:app --reload")
        print(f"Error: {e}")


if __name__ == "__main__":
    seed()
