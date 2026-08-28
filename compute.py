"""Compute the index series and shrinkflation log from data/prices.csv.

Method: Laspeyres-style fixed-basket index. Each product's price is expressed
relative to its own base price (the first date it appears). Products average
into their category, categories combine with fixed weights (approximate CBS
household spending shares). Base date = 100.

Three series:
  index_list  : shelf price before any discount (the headline index)
  index_paid  : price actually paid, bonus discounts included
  index_unit  : price per liter/kg where AH publishes one; this one moves when
                a package shrinks at an unchanged shelf price (shrinkflation)

Writes docs/data.json (dashboard input) and data/shrinkflation.csv (event log).
"""
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
PRICES = ROOT / "data" / "prices.csv"


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def weighted_index(per_product_ratio, product_category, weights):
    """Average ratios within category, then weight categories."""
    by_cat = defaultdict(list)
    for pid, ratio in per_product_ratio.items():
        by_cat[product_category[pid]].append(ratio)
    num = den = 0.0
    for cat, ratios in by_cat.items():
        w = weights[cat]
        num += w * (sum(ratios) / len(ratios))
        den += w
    return 100.0 * num / den if den else None


def main():
    basket = json.loads((ROOT / "basket.json").read_text())
    weights = {b["category"]: b["category_weight"] for b in basket}

    with open(PRICES, newline="") as f:
        rows = list(csv.DictReader(f))
    dates = sorted({r["date"] for r in rows})
    by_date = defaultdict(dict)
    category = {}
    for r in rows:
        pid = r["webshopId"]
        by_date[r["date"]][pid] = r
        category[pid] = r["category"]

    # Base prices: first observation per product, per price concept.
    base = {}
    for d in dates:
        for pid, r in by_date[d].items():
            if pid in base:
                continue
            lp = fnum(r["list_price"])
            cp = fnum(r["current_price"]) or lp
            up = fnum(r["unit_price"])
            if lp:
                base[pid] = {"list": lp, "paid": cp, "unit": up}

    series = {"index_list": [], "index_paid": [], "index_unit": [],
              "basket_cost": [], "paid_cost": [], "bonus_count": [], "n_products": []}
    for d in dates:
        ratios = {"list": {}, "paid": {}, "unit": {}}
        cost = paid = 0.0
        bonus = n = 0
        for pid, r in by_date[d].items():
            if pid not in base:
                continue
            lp = fnum(r["list_price"])
            cp = fnum(r["current_price"]) or lp
            up = fnum(r["unit_price"])
            if not lp:
                continue
            n += 1
            cost += lp
            paid += cp
            bonus += r["is_bonus"] == "True"
            ratios["list"][pid] = lp / base[pid]["list"]
            ratios["paid"][pid] = cp / base[pid]["paid"]
            if up and base[pid]["unit"]:
                ratios["unit"][pid] = up / base[pid]["unit"]
        series["index_list"].append(round(weighted_index(ratios["list"], category, weights), 2))
        series["index_paid"].append(round(weighted_index(ratios["paid"], category, weights), 2))
        iu = weighted_index(ratios["unit"], category, weights)
        series["index_unit"].append(round(iu, 2) if iu else None)
        series["basket_cost"].append(round(cost, 2))
        series["paid_cost"].append(round(paid, 2))
        series["bonus_count"].append(bonus)
        series["n_products"].append(n)

    # Shrinkflation: same product, changed package size string.
    events = []
    for pid in category:
        prev = None
        for d in dates:
            r = by_date[d].get(pid)
            if not r or not r["sales_unit_size"]:
                continue
            if prev and r["sales_unit_size"] != prev["sales_unit_size"]:
                events.append({
                    "date": d, "title": r["title"],
                    "old_size": prev["sales_unit_size"], "new_size": r["sales_unit_size"],
                    "old_unit_price": prev["unit_price"], "new_unit_price": r["unit_price"],
                })
            prev = r
    with open(ROOT / "data" / "shrinkflation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "title", "old_size", "new_size",
                                          "old_unit_price", "new_unit_price"])
        w.writeheader()
        w.writerows(events)

    # Latest per-category relatives and product table.
    latest = dates[-1]
    cat_rel = defaultdict(list)
    products_latest = []
    for pid, r in sorted(by_date[latest].items(), key=lambda kv: (kv[1]["category"], kv[1]["title"])):
        lp = fnum(r["list_price"])
        if pid in base and lp:
            cat_rel[r["category"]].append(lp / base[pid]["list"])
        products_latest.append({
            "title": r["title"], "category": r["category"],
            "list_price": fnum(r["list_price"]), "current_price": fnum(r["current_price"]),
            "is_bonus": r["is_bonus"] == "True", "size": r["sales_unit_size"],
            "unit_price": fnum(r["unit_price"]), "unit": r["unit"],
        })
    categories = [{"name": c, "weight": weights[c],
                   "rel_latest": round(100 * sum(v) / len(v), 2)}
                  for c, v in sorted(cat_rel.items(), key=lambda kv: -weights[kv[0]])]

    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_date": dates[0], "latest_date": latest, "dates": dates,
        **series, "categories": categories,
        "products_latest": products_latest, "shrinkflation": events,
    }
    (ROOT / "docs" / "data.json").write_text(json.dumps(out, ensure_ascii=False))
    print(f"{latest}: index_list={series['index_list'][-1]} "
          f"index_paid={series['index_paid'][-1]} basket=€{series['basket_cost'][-1]} "
          f"shrinkflation_events={len(events)}")


if __name__ == "__main__":
    main()
