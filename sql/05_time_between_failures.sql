-- Mean time between failures (MTBF) in hours, by month, using LAG().
WITH fails AS (
    SELECT
        timestamp,
        DATE_TRUNC('month', timestamp) AS month,
        timestamp - LAG(timestamp) OVER (ORDER BY timestamp) AS gap
    FROM wafers
    WHERE is_fail = 1
)
SELECT
    STRFTIME(month, '%Y-%m')                         AS month,
    COUNT(*)                                         AS failures,
    ROUND(AVG(EPOCH(gap)) / 3600.0, 1)               AS mtbf_hours
FROM fails
WHERE gap IS NOT NULL
GROUP BY month
ORDER BY month;
