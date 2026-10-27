-- Weekly yield trend with a 4-week rolling yield to smooth week-to-week noise.
WITH weekly AS (
    SELECT
        week_start,
        COUNT(*)       AS runs,
        SUM(is_fail)   AS fails
    FROM wafers
    GROUP BY week_start
)
SELECT
    week_start,
    runs,
    fails,
    ROUND(100.0 * (1 - fails / runs), 2) AS yield_pct,
    ROUND(100.0 * (1 - SUM(fails) OVER w / SUM(runs) OVER w), 2) AS rolling_4wk_yield_pct
FROM weekly
WINDOW w AS (ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
ORDER BY week_start;
