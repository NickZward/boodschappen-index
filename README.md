# 🛒 Boodschappenindex

An independent, daily measurement of Dutch supermarket prices, built on a fixed basket of **72 everyday products** at Albert Heijn. Live dashboard: **[nickzward.github.io/boodschappen-index](https://nickzward.github.io/boodschappen-index/)**

Every day an automated job records the price of the exact same products (same product IDs, so the comparison is always like-for-like) and recomputes three index series with the first collection day as base = 100:

| Series | What it measures |
|---|---|
| **Schapprijs-index** | Shelf prices before any discount. The headline index. |
| **Betaalprijs-index** | Prices actually paid, bonus discounts included. The gap with the shelf index shows how much promo pressure there is. |
| **Eenheidsprijs-index** | Price per liter/kilo. This one also moves when a package quietly shrinks while the shelf price stays the same. |

## Shrinkflation detection

Because products are tracked by ID, a package change is directly observable: same product, smaller `salesUnitSize`, same or higher shelf price. Every such event lands in [data/shrinkflation.csv](data/shrinkflation.csv) and in the dashboard's krimpflatie-log, with the price per unit before and after.

## Method

- **Fixed basket (Laspeyres):** 72 staples across 11 categories (dairy, bread, meat & fish, produce, drinks, snacks, pantry, frozen, household, personal care), frozen on 2026-08-28 in [basket.json](basket.json). Products were chosen to be canonical long-lived items (house-brand basics and market-leading A-brands).
- **Weights:** categories are weighted with approximate CBS household spending shares (see `category_weight` in the basket). Products weigh equally within their category.
- **Aggregation:** each product's price is expressed relative to its own base price; products average into their category; categories combine with the fixed weights.
- **Data:** one snapshot per day, stored append-only in [data/prices.csv](data/prices.csv). The git history doubles as an audit trail: every observation is traceable to a commit.

## Honest caveats

- One retailer, one channel (the AH webshop). This is a price signal, not an official inflation measure; for that, see [CBS](https://www.cbs.nl/nl-nl/cijfers/detail/83131NED).
- 72 products is a basket, not the full CPI universe. Category weights are approximations.
- Bonus prices are national webshop prices; personal discounts are not included.
- If a product is discontinued, it drops out and a successor is added in `basket.json` (documented in the commit message). The index chains through such changes because every product is measured against its own base.

## Running it yourself

Pure Python standard library, no dependencies:

```bash
python collect.py   # fetch today's prices (one polite request per second)
python compute.py   # rebuild index + dashboard data
```

The [daily workflow](.github/workflows/daily.yml) does exactly this and commits the result.

## Data source & fair use

Prices come from Albert Heijn's mobile API (the same data their app shows). This project is not affiliated with Albert Heijn. It performs one small read-only snapshot per day (~72 requests at one request per second), stores only factual price data, and exists for research and journalism-style price transparency.

## License

MIT. Price data in `data/` is factual public information; attribution appreciated.
