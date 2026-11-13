# Data Dictionary - 2019-Oct.csv

The following columns are present in the CSV (as observed from the header).
- **event_time**: Timestamp of the event (UTC).
- **event_type**: Interaction type - one of view, cart, remove_from_cart, purchase.
- **product_id**: Unique identifier of the product (integer).
- **category_id**: Numeric identifier of the product category.
- **category_code**: Hierarchical category code (e.g., "electronics.smartphone"); may contain nulls.
- **brand**: Brand name of the product; nullable.
- **price**: Price of the product at the time of the event (float).
- **user_id**: Anonymous unique identifier for the customer (integer).
- **user_session**: UUID representing a browsing session; resets when the user leaves the site.

All values are stored as plain-text strings in the CSV; numeric columns can be cast to int/float during analysis.
