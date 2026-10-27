-- Headline production KPIs for the full observation window.
SELECT
    COUNT(*)                                            AS total_runs,
    SUM(is_fail)                                        AS failed_runs,
    ROUND(100.0 * (1 - AVG(is_fail)), 2)                AS yield_pct,
    MIN(timestamp)::DATE                                AS first_run,
    MAX(timestamp)::DATE                                AS last_run,
    DATE_DIFF('day', MIN(timestamp), MAX(timestamp))    AS days_observed,
    ROUND(COUNT(*) / DATE_DIFF('day', MIN(timestamp), MAX(timestamp)), 1) AS runs_per_day
FROM wafers;
