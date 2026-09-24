"""Compute the index series and package-size change log from data/prices.csv.

Method: Laspeyres-style fixed-basket index. Each product's price is chained
day to day from its own first observation. Products average into their
category, categories combine with fixed weights (approximate CBS household
spending shares). Base date = 100.

Package-size adjustment: when a product's pack size changes, that day's link
compares price per unit (per kg/liter/piece) instead of the pack price. A pack
that shrinks at the same price therefore counts as the price rise it is
(shrinkflation), and a pack that grows is not mistaken for one.

Three series:
  index_list  : shelf price before any discount, size-adjusted (the headline)
  index_paid  : price actually paid, bonus discounts included, size-adjusted
  index_unit  : AH's published price per liter/kg, for the products that have
                one; a cross-check on the size adjustment

Writes docs/data.json (dashboard input) and data/shrinkflation.csv (event log).
"""
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
PRICES = ROOT / "data" / "prices.csv"

# Size changes smaller than this are relabels ("170g" -> "170 g"), not events.
SIZE_TOLERANCE = 0.005

SIZE_UNITS = {"kg": (1000, "g"), "g": (1, "g"), "l": (1000, "ml"), "cl": (10, "ml"),
              "ml": (1, "ml"), "stuks": (1, "pcs"), "stuk": (1, "pcs"),
              "rollen": (1, "pcs"), "wasbeurten": (1, "pcs")}
MULTI_RE = re.compile(r"^(\d+)\s*x\s*([\d.]+)\s*([a-z]+)$")
SINGLE_RE = re.compile(r"^([\d.]+)\s*([a-z]+)$")


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_size(s):
    """'1,5 kg' -> (1500.0, 'g'); '24 x 0,3 l' -> (7200.0, 'ml'); None if unparseable."""
    s = s.lower().replace(",", ".").replace("ca.", "").strip()
    m = MULTI_RE.match(s)
    if m:
        count, value, unit = int(m.group(1)), float(m.group(2)), m.group(3)
    else:
        m = SINGLE_RE.match(s)
        if not m:
            return None
        count, value, unit = 1, float(m.group(1)), m.group(2)
    if unit not in SIZE_UNITS:
        return None
    factor, dim = SIZE_UNITS[unit]
    return count * value * factor, dim


def size_ratio(prev, cur):
    """New pack quantity divided by old, or None if it can't be determined.

    Prefers AH's per-unit price (always based on the shelf price, so
    quantity = shelf price / unit price); falls back to parsing the size text.
    """
    lp0, up0 = fnum(prev["list_price"]), fnum(prev["unit_price"])
    lp1, up1 = fnum(cur["list_price"]), fnum(cur["unit_price"])
    if lp0 and up0 and lp1 and up1 and prev["unit"] == cur["unit"]:
        return (lp1 / up1) / (lp0 / up0)
    a, b = parse_size(prev["sales_unit_size"]), parse_size(cur["sales_unit_size"])
    if a and b and a[1] == b[1] and a[0] > 0:
        return b[0] / a[0]
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

    # Chain each product's shelf and paid price relatives through time,
    # switching to per-unit comparison on days its pack size changes.
    rel = defaultdict(dict)       # rel[date][pid] = {"list": x, "paid": y}
    unit_base = {}
    events = []
    for pid in category:
        prev = None
        chain_list = chain_paid = 1.0
        for d in dates:
            r = by_date[d].get(pid)
            if not r or not fnum(r["list_price"]):
                continue
            lp = fnum(r["list_price"])
            cp = fnum(r["current_price"]) or lp
            if prev is None:
                unit_base[pid] = fnum(r["unit_price"])
            else:
                lp0 = fnum(prev["list_price"])
                cp0 = fnum(prev["current_price"]) or lp0
                q = 1.0
                if r["sales_unit_size"] != prev["sales_unit_size"]:
                    q = size_ratio(prev, r)
                    if q is None or abs(q - 1) > SIZE_TOLERANCE:
                        direction = ("changed" if q is None
                                     else "shrunk" if q < 1 else "grew")
                        events.append({
                            "date": d, "title": r["title"], "direction": direction,
                            "size_change_pct": "" if q is None else round((q - 1) * 100, 1),
                            "old_size": prev["sales_unit_size"], "new_size": r["sales_unit_size"],
                            "old_unit_price": prev["unit_price"], "new_unit_price": r["unit_price"],
                        })
                # Unknown quantity change (q is None): the new pack starts a fresh
                # base, so this day contributes no price movement for the product.
                if q is not None:
                    chain_list *= (lp / lp0) / q
                    chain_paid *= (cp / cp0) / q
            rel[d][pid] = {"list": chain_list, "paid": chain_paid}
            prev = r

    series = {"index_list": [], "index_paid": [], "index_unit": [],
              "basket_cost": [], "paid_cost": [], "bonus_count": [], "n_products": []}
    for d in dates:
        ratios = {"list": {}, "paid": {}, "unit": {}}
        cost = paid = 0.0
        bonus = n = 0
        for pid, rr in rel[d].items():
            r = by_date[d][pid]
            lp = fnum(r["list_price"])
            cp = fnum(r["current_price"]) or lp
            up = fnum(r["unit_price"])
            n += 1
            cost += lp
            paid += cp
            bonus += r["is_bonus"] == "True"
            ratios["list"][pid] = rr["list"]
            ratios["paid"][pid] = rr["paid"]
            if up and unit_base.get(pid):
                ratios["unit"][pid] = up / unit_base[pid]
        series["index_list"].append(round(weighted_index(ratios["list"], category, weights), 2))
        series["index_paid"].append(round(weighted_index(ratios["paid"], category, weights), 2))
        iu = weighted_index(ratios["unit"], category, weights)
        series["index_unit"].append(round(iu, 2) if iu else None)
        series["basket_cost"].append(round(cost, 2))
        series["paid_cost"].append(round(paid, 2))
        series["bonus_count"].append(bonus)
        series["n_products"].append(n)

    with open(ROOT / "data" / "shrinkflation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "title", "direction", "size_change_pct",
                                          "old_size", "new_size",
                                          "old_unit_price", "new_unit_price"])
        w.writeheader()
        w.writerows(events)

    # Latest per-category relatives and product table.
    latest = dates[-1]
    cat_rel = defaultdict(list)
    for pid, rr in rel[latest].items():
        cat_rel[category[pid]].append(rr["list"])
    products_latest = []
    for pid, r in sorted(by_date[latest].items(), key=lambda kv: (kv[1]["category"], kv[1]["title"])):
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
          f"size_changes={len(events)}")


if __name__ == "__main__":
    main()
