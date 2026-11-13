
USE abando_scope;

SELECT
    category_code,
    carts,
    purchases,
    ROUND(
        purchases * 100.0 / NULLIF(carts, 0), 2
    ) AS purchase_to_cart_event_ratio
FROM category_performance
WHERE category_code != 'UNKNOWN'
  AND carts >= 1000
ORDER BY purchase_to_cart_event_ratio ASC
LIMIT 10;
