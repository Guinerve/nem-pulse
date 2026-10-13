# nem-pulse

> A self-updating dataset repo for the NEM, maintained by a scheduled GitHub Action.

**Status:** v0.1 core built; seeded with 10 days; reconciles with AEMO · Portfolio project #8 · see `../README.md`

## The idea

The "git scraping" pattern: a scheduled Action pulls a daily NEM summary (prices, renewable share, records broken), commits it as CSV, and regenerates charts in the README. The repo stays useful with no upkeep and becomes a small public dataset.

## Stack

Python (uv), the shared `nem` client, matplotlib, GitHub Actions cron.

Python project managed with `uv`; target a one-command run (`uv run ...`).

## Build plan (v1)

- [x] Daily summary script → `data/YYYY/MM/DD.csv` plus a rolling `latest.csv`
- [x] Records detector (`data/records.csv`; needs at least 7 days of history) (e.g. highest renewable share, lowest operational demand)
- [x] Regenerate charts on each run (`assets/*.png`; not yet embedded in this README)
- [x] Scheduled workflow (`.github/workflows/daily.yml`, 06:30 AEST; untested on GitHub) with a commit-only-if-changed step

## Run it

```bash
uv sync
uv run nem-pulse                              # newest archived day (NEM today minus 2)
uv run nem-pulse --date 2026-10-10 --days 10  # backfill
uv run pytest -q                              # 11 tests
```

Depends on `nem-mcp` as a git dependency on `github.com/Guinerve/nem-mcp`. It is public, so the workflow needs no secret.

## How I know it's right

**Reconciliation with AEMO's published "Aggregated price and demand" CSVs** (`scripts/reconcile.py`, `docs/reconciliation-2026-10.txt`), 50 region-days (2026-10-01 to 10):

- daily average price: max difference **0.0049 $/MWh** (mean 0.0026)
- daily average demand: max difference **0.048 MW** (mean 0.027)
- daily max price: max difference **0.0000**
- 288 intervals per day in both sources, every day

The small differences are rounding.

**Fails loudly**: `summarise_day` raises `SourceDataError` for an empty source, fewer than 285 of 288 intervals, or NaN prices; the CLI exits with status 2 so the workflow goes red and nothing partial is committed (tested). The same applies to missing demand, a missing README marker, an unlistable archive or a failed download. The commit step only commits when files changed. Archive days are cached only if they look complete (≥280 intervals), and cache writes are atomic.

## Limits

Generation shares come from scheduled/semi-scheduled SCADA and **exclude rooftop solar**, so "renewable share" understates daytime renewables in NSW, QLD and SA. The NEM price is demand-weighted across regions. "Records" are relative to this dataset's own history only (10 days so far, so early records are meaningless).

Daily resolution only; derived figures, not an official AEMO dataset.

## Next (tomorrow)

- Add rooftop PV; embed the charts above in this README.
- Backfill a longer history (the archive goes back years) so records mean something.
- Make `nem` installable from git so the workflow runs standalone; then test the Action.

## Stretch

Datasette or a static explorer page on GitHub Pages.

## Definition of done

- [ ] Hero GIF or screenshot at the top of this README
- [x] Live demo link or one-command run (`uv run nem-pulse`)
- [ ] "How I know it's right" section filled in with real results
- [ ] Tests passing in CI, badge added
- [ ] "Limits" section written
- [ ] Licence chosen, repo description and topics set
- [ ] Pinned on GitHub profile and added to guinerve.github.io
- [ ] Added to `career-radar/data/cv/portfolio.json`

## Latest

<!-- PULSE:START -->
_Updated for 2026-10-11 (NEM time)._

| Region | Avg price | Renewables | Intensity | Neg. price intervals |
|---|---:|---:|---:|---:|
| NSW1 | $134/MWh | 39% | 504 g/kWh | 34 |
| QLD1 | $109/MWh | 27% | 620 g/kWh | 96 |
| VIC1 | $3/MWh | 33% | 772 g/kWh | 162 |
| SA1 | $-28/MWh | 75% | 104 g/kWh | 164 |
| TAS1 | $6/MWh | 100% | 0 g/kWh | 140 |
| NEM | $82/MWh | 38% | 573 g/kWh | 82 |

### Recent records

- **2026-10-11** VIC1: lowest price (-365.2, previous best -148.4)
- **2026-10-11** SA1: most negative-price intervals (164.0, previous best 158)
- **2026-10-11** SA1: lowest price (-415.0, previous best -294.4)
- **2026-10-11** QLD1: highest solar share (16.3%, previous best 0.1592)
- **2026-10-11** NSW1: most negative-price intervals (34.0, previous best 2)
- **2026-10-11** NSW1: lowest price (-9.6, previous best -5.59)
- **2026-10-11** NSW1: highest solar share (23.4%, previous best 0.2053)
- **2026-10-11** NEM: most negative-price intervals (82.0, previous best 13)
- **2026-10-11** NEM: lowest price (-71.6, previous best -9.51)
- **2026-10-10** NSW1: lowest emissions intensity (465.1, previous best 488.4)
<!-- PULSE:END -->

> The AEMO archive trails real time by about two days, so this dataset is two days behind the grid. (Found when the first scheduled run on GitHub failed with a 404 for "yesterday".)
