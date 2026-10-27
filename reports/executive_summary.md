# Executive Summary: Wafer Yield Improvement

**To:** Plant Manager, Process Engineering Lead
**Re:** Root causes of yield loss and recommended actions
**Data:** 1,567 production runs, 590 sensors per run, Jul to Oct 2008 (UCI SECOM)

## Situation
Line yield over the quarter was **93.4%** (104 failed runs). At an assumed €2,500 per failed run, poor
quality costs about **€1.05M per year**. Yield started near 77% and recovered to about 95% by October,
but the cause of the recovery was not documented.

## Key findings
1. **One sensor explains most of the recovery.** Sensor S059 was unstable until 28 August, with 47% of runs
   outside control limits. After it stabilised, the failure rate fell from **11.8% to 4.2%**. Runs outside its
   control limits fail **3.6x** more often than runs inside them.
2. **Failures come from equipment, not people.** Failure rates are the same across all three shifts
   (chi-square p = 0.88). Failures cluster in time, which is typical of tool drift.
3. **Only 16 of 590 sensors matter.** 54% of sensors are constant, empty or duplicated. 16 differ significantly
   between pass and fail runs after false-discovery-rate correction.
4. **Risk-based inspection pays back.** A random forest early-warning score catches **43% of failures by
   inspecting 16% of runs**, a net saving of about **€125k per year**. On future data the model degrades because
   the process drifted, so it needs rolling retraining.

## Recommendations
| # | Action | Owner | Expected impact |
|---|---|---|---|
| 1 | Live SPC alarms and an upper spec limit on S059 | Process Engineering | Prevent a return to a 12% fail rate |
| 2 | Root-cause review of the other 15 short-listed sensors | Process Engineering | Each +1pp of yield is worth about €159k per year |
| 3 | Pilot risk-based inspection with monthly model retraining | Quality / Data | About €125k per year net |
| 4 | Remove dead and duplicate sensors from the MES export | IT / Data | Cleaner, faster reporting |
| 5 | Weekly KPI review: yield, 4-week rolling yield, MTBF, SPC alarm rate | Operations | Early detection of drift |

*Cost inputs are assumptions. Replace them with actual scrap and rework costs to finalise the business case.*
