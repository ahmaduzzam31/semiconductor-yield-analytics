-- Gaps-and-islands: find runs of consecutive failures.
-- Clustered failures point to a process excursion (a tool drifting) rather than random defects.
WITH seq AS (
    SELECT
        run_id,
        timestamp,
        is_fail,
        run_id - ROW_NUMBER() OVER (PARTITION BY is_fail ORDER BY run_id) AS island
    FROM wafers
),
streaks AS (
    SELECT
        island,
        COUNT(*)        AS consecutive_fails,
        MIN(run_id)     AS first_run_id,
        MIN(timestamp)  AS started_at,
        MAX(timestamp)  AS ended_at
    FROM seq
    WHERE is_fail = 1
    GROUP BY island
)
SELECT consecutive_fails, first_run_id, started_at, ended_at
FROM streaks
WHERE consecutive_fails >= 2
ORDER BY consecutive_fails DESC, started_at;
