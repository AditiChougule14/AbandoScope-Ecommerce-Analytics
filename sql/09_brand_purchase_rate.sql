
USE abando_scope;

SELECT
    brand,
    views,
    carts,
    purchases,
    ROUND(
        purchases * 100.0 / NULLIF(views, 0), 2
    ) AS purchase_rate
FROM brand_performance
WHERE brand != 'NO_BRAND'
  AND views >= 10000
ORDER BY purchase_rate DESC
LIMIT 10;
