# Olist dataset setup

The Olist adapter reads local CSV files from `datasets/olist/data/`. This directory is intentionally ignored by Git. Do not add the source files, copied extracts, participant material, or derived data to a commit, release archive, or public issue.

Place exactly these nine files directly in `datasets/olist/data/`:

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_customers_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`
- `olist_geolocation_dataset.csv`

The default Olist configuration already points `dataset.data_dir` to this directory. If a private local configuration uses another location, keep that configuration ignored as well. This repository does not distribute the CSV files or make a licensing conclusion about them; confirm the applicable source terms before obtaining, sharing, or using the data.

## Reference snapshot integrity

The migration was validated against the following local snapshot. Verify a
replacement download before running a study; a mismatch means the dataset
version has changed and results may not be comparable.

| File | Bytes | SHA-256 |
|---|---:|---|
| `olist_orders_dataset.csv` | 17,654,914 | `8DF58EF3D2D7E9944010F7BEECD9B75367F5588EC6E3C91CEC19AE3345EF9ECF` |
| `olist_order_items_dataset.csv` | 15,438,671 | `0BC4D068C4FE38CBB01BD90E8746E3C613FE7B4BAEF75FAB7B0E329701C3E279` |
| `olist_order_payments_dataset.csv` | 5,777,138 | `4F713964F2815DBBAA40B9488268C55AAC3627BFCE5AA96CF58D1F3616DE3CC0` |
| `olist_order_reviews_dataset.csv` | 14,451,670 | `012B61C7593E34F51FA614EFDF802B9C7056CE6AAE5307DDB93236E7CFC797D7` |
| `olist_customers_dataset.csv` | 9,033,957 | `983A422239E1712DED753B3BF9ECF47DC73F144D306029DCFA99E70A226883D2` |
| `olist_products_dataset.csv` | 2,379,446 | `3E6569628A17FBC75FD206EE357B59E20364B9AFA90F5B6CD5B4D624C58AA9CC` |
| `olist_sellers_dataset.csv` | 174,703 | `1F643D2B950373B85735E7794B20986F528D7A000432E7C6F9BCBB44D0846A0E` |
| `product_category_name_translation.csv` | 2,613 | `A81F0D1F27B27E7293F761BC79E3CE8F348EE39C4B3ED3E49BDE38F478586278` |
| `olist_geolocation_dataset.csv` | 61,273,883 | `B514F6FC991B9566AEBA02AA5D67E2C3630F034B60A0E05AA0D082A3B66D88D6` |

Expected total size: `126,186,995` bytes. The adapter reports this snapshot as
`olist-5-8e2b55985d02985e`.
