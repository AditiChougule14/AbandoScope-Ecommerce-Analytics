
USE abando_scope;

SELECT
    SUM(views) AS total_views,
    SUM(carts) AS total_cart_events,
    SUM(purchases) AS total_purchases,
    ROUND(SUM(revenue), 2) AS total_revenue,
    ROUND(
        SUM(carts) * 100.0 / SUM(views), 2
    ) AS view_to_cart_rate,
    ROUND(
        SUM(purchases) * 100.0 / SUM(views), 2
    ) AS view_to_purchase_rate
FROM category_performance;
