
USE abando_scope;

SELECT
    category_code,
    views,
    carts,
    purchases,
    ROUND(
        purchases * 100.0 / NULLIF(views, 0), 2
    ) AS view_to_purchase_rate
FROM category_performance
WHERE category_code != 'UNKNOWN'
  AND views >= 10000
ORDER BY view_to_purchase_rate DESC
LIMIT 10;
