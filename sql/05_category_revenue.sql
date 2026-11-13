
USE abando_scope;

SELECT
    category_code,
    views,
    carts,
    purchases,
    ROUND(revenue, 2) AS revenue
FROM category_performance
ORDER BY revenue DESC
LIMIT 10;
