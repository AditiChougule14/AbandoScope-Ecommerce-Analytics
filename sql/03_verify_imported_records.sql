
USE abando_scope;

SELECT 'brand_performance' AS table_name, COUNT(*) AS total_records
FROM brand_performance

UNION ALL

SELECT 'category_performance', COUNT(*)
FROM category_performance

UNION ALL

SELECT 'event_distribution', COUNT(*)
FROM event_distribution

UNION ALL

SELECT 'top_products', COUNT(*)
FROM top_products;
