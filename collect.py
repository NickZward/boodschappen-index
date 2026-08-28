"""Daily price snapshot of the frozen basket.

Fetches every basket product from the AH mobile API (politely: one request
per second at most) and appends one row per product to data/prices.csv.
Re-running on the same day replaces that day's rows, so the job is idempotent.
"""
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import ah

ROOT = Path(__file__).parent
PRICES = ROOT / "data" / "prices.csv"
FIELDS = ["date", "webshopId", "category", "title", "list_price", "current_price",
          "is_bonus", "bonus_mechanism", "sales_unit_size", "unit_price", "unit"]

UNIT_RE = re.compile(r"per\s+(.+?)\s*€\s*([\d.,]+)")


def parse_unit_price(desc):
    """'prijs per liter €1.29' -> ('liter', 1.29)."""
    if not desc:
        return "", ""
    m = UNIT_RE.search(desc)
    if not m:
        return "", ""
    return m.group(1).strip(), float(m.group(2).replace(",", "."))


def main():
    basket = json.loads((ROOT / "basket.json").read_text())
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date().isoformat()
    token = ah.anonymous_token()

    rows, missing = [], []
    for item in basket:
        card = None
        for attempt in range(3):
            try:
                card = ah.product_detail(token, item["webshopId"])
                break
            except Exception as e:
                if attempt == 2:
                    missing.append((item["title"], str(e)[:80]))
                else:
                    time.sleep(2.0 * (attempt + 1))
        if card is None:
            continue
        unit, unit_price = parse_unit_price(card.get("unitPriceDescription"))
        rows.append({
            "date": today,
            "webshopId": item["webshopId"],
            "category": item["category"],
            "title": card.get("title") or item["title"],
            "list_price": card.get("priceBeforeBonus", ""),
            "current_price": card.get("currentPrice", ""),
            "is_bonus": card.get("isBonus", False),
            "bonus_mechanism": card.get("bonusMechanism", "") or "",
            "sales_unit_size": card.get("salesUnitSize", "") or "",
            "unit_price": unit_price,
            "unit": unit,
        })
        time.sleep(1.0)

    if missing:
        print(f"WARNING: {len(missing)} products failed:", file=sys.stderr)
        for title, err in missing:
            print(f"  {title}: {err}", file=sys.stderr)
    if len(rows) < 0.8 * len(basket):
        print("FATAL: more than 20% of the basket failed; not writing snapshot.",
              file=sys.stderr)
        sys.exit(1)

    existing = []
    if PRICES.exists():
        with open(PRICES, newline="") as f:
            existing = [r for r in csv.DictReader(f) if r["date"] != today]

    PRICES.parent.mkdir(exist_ok=True)
    with open(PRICES, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(existing)
        w.writerows(rows)
    print(f"{today}: wrote {len(rows)}/{len(basket)} products "
          f"({sum(1 for r in rows if r['is_bonus'])} in bonus)")


if __name__ == "__main__":
    main()
