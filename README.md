# 🛒 Boodschappenindex

An independent, daily measurement of Dutch supermarket prices, built on a fixed basket of **72 everyday products** at Albert Heijn. Live dashboard: **[nickzward.github.io/boodschappen-index](https://nickzward.github.io/boodschappen-index/)**

Every day an automated job records the price of the exact same products (same product IDs, so the comparison is always like-for-like) and recomputes three index series with the first collection day as base = 100:

| Series | What it measures |
|---|---|
| **Shelf-price index** | Shelf prices before any discount, adjusted for pack-size changes. The headline index. |
| **Paid-price index** | Prices actually paid, bonus discounts included, adjusted for pack-size changes. The gap with the shelf index shows how much promo pressure there is. |
| **Unit-price index** | AH's published price per liter/kilo, for the products that have one. A cross-check on the size adjustment. |

## Shrinkflation detection

Because products are tracked by ID, a package change is directly observable: same product, different `salesUnitSize`. Every such event lands in [data/shrinkflation.csv](data/shrinkflation.csv) and in the dashboard's shrinkflation watch, labelled `shrunk` or `grew` with the size change in percent and the price per unit before and after.

Pack-size changes are also corrected for in the index itself. On the day a pack changes, that product's price is compared per kilo or liter instead of per pack (quantity is derived from AH's per-unit price, falling back to parsing the size text). So a pack that shrinks from 200g to 180g at the same price counts as the +11% price rise it is, and a pack that grows at the same price per kilo counts as no change. This is the same principle statistical offices use for quality adjustment. If the quantity change can't be determined, the new pack starts a fresh base for that product rather than guessing.

## Method

- **Fixed basket (Laspeyres):** 72 staples across 11 categories (dairy, bread, meat & fish, produce, drinks, snacks, pantry, frozen, household, personal care), frozen on 2026-08-28 in [basket.json](basket.json). Products were chosen to be canonical long-lived items (house-brand basics and market-leading A-brands).
- **Weights:** categories are weighted with approximate CBS household spending shares (see `category_weight` in the basket). Products weigh equally within their category.
- **Aggregation:** each product's price is chained day to day from its own first observation (size-adjusted, see above); products average into their category; categories combine with the fixed weights.
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
