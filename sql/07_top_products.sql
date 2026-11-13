
USE abando_scope;

SELECT
    product_id,
    views,
    carts,
    purchases,
    ROUND(revenue, 2) AS revenue
FROM top_products
ORDER BY revenue DESC
LIMIT 10;
