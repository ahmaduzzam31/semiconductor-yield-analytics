-- Does yield depend on the production shift? Compare each shift to the plant average.
WITH plant AS (SELECT AVG(is_fail) AS plant_fail_rate FROM wafers)
SELECT
    shift,
    COUNT(*)                                              AS runs,
    SUM(is_fail)                                          AS fails,
    ROUND(100.0 * AVG(is_fail), 2)                        AS fail_rate_pct,
    ROUND(100.0 * (AVG(is_fail) - ANY_VALUE(plant_fail_rate)), 2) AS vs_plant_pp
FROM wafers, plant
GROUP BY shift
ORDER BY fail_rate_pct DESC;
