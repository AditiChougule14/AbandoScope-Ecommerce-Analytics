
USE abando_scope;

SELECT
    event_type,
    event_count
FROM event_distribution
ORDER BY event_count DESC;
