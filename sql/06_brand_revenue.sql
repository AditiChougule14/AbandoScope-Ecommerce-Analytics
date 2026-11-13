
USE abando_scope;

SELECT
    brand,
    views,
    carts,
    purchases,
    ROUND(revenue, 2) AS revenue
FROM brand_performance
ORDER BY revenue DESC
LIMIT 10;
