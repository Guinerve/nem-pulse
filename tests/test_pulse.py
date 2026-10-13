from datetime import date

import pandas as pd
import pytest

from nem_pulse import cli, records, store, summary

REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
DAY = date(2026, 9, 28)


def make_prices(n=288, price=100.0):
    t = pd.date_range("2026-09-28 00:05", periods=n, freq="5min")
    rows = [(ts, r, price + (i % 4), 5000.0 + 10 * i) for r in REGIONS for i, ts in enumerate(t)]
    return pd.DataFrame(rows, columns=["interval_end", "region", "rrp", "demand"])


def make_scada(n=288):
    t = pd.date_range("2026-09-28 00:05", periods=n, freq="5min")
    rows = [(ts, d, mw) for ts in t for d, mw in [("COAL", 100.0), ("WIND", 100.0), ("GAS", 0.0)]]
    return pd.DataFrame(rows, columns=["interval_end", "duid", "mw"])


GENS = pd.DataFrame({
    "duid": ["COAL", "WIND", "GAS"], "region": ["NSW1"] * 3,
    "ef_t_per_mwh": [0.9, 0.0, 0.5], "fuel": ["Black coal", "Wind", "Gas"],
})


def test_summary_has_one_row_per_region_and_nem():
    df = summary.summarise_day(DAY, make_prices(), make_scada(), GENS)
    assert list(df["region"]) == [*REGIONS, "NEM"]
    nsw = df[df["region"] == "NSW1"].iloc[0]
    assert nsw["intervals"] == 288
    assert nsw["renewable_share"] == pytest.approx(0.5) and nsw["coal_share"] == pytest.approx(0.5)
    assert nsw["intensity_g_per_kwh"] == pytest.approx(450.0)  # (0.9*100 + 0) / 200 t/MWh
    assert nsw["generation_mwh"] == pytest.approx(200 * 288 / 12, abs=1)


def test_negative_intervals_counted():
    p = make_prices()
    p.loc[(p["region"] == "SA1") & (p.index % 7 == 0), "rrp"] = -50.0
    sa = summary.summarise_day(DAY, p, make_scada(), GENS).query("region == 'SA1'").iloc[0]
    assert sa["negative_intervals"] > 0 and sa["min_price"] == -50.0


@pytest.mark.parametrize("bad", ["prices_short", "scada_short", "empty", "nan_price"])
def test_bad_source_data_fails_loudly(bad):
    prices, scada = make_prices(), make_scada()
    if bad == "prices_short":
        prices = make_prices(n=200)
    if bad == "scada_short":
        scada = make_scada(n=100)
    if bad == "empty":
        scada = scada.iloc[0:0]
    if bad == "nan_price":
        prices.loc[0, "rrp"] = float("nan")
    with pytest.raises(summary.SourceDataError):
        summary.summarise_day(DAY, prices, scada, GENS)


def test_write_day_only_reports_change_when_content_differs(tmp_path):
    df = summary.summarise_day(DAY, make_prices(), make_scada(), GENS)
    assert store.write_day(tmp_path, DAY, df) is True
    assert store.write_day(tmp_path, DAY, df) is False
    assert (tmp_path / "2026" / "09" / "28.csv").exists()
    assert store.write_day(tmp_path, DAY, df.assign(avg_price=1.0)) is True


def test_latest_keeps_a_rolling_window(tmp_path):
    frames = []
    for i in range(40):
        d = date(2026, 8, 1).toordinal() + i
        df = summary.summarise_day(date.fromordinal(d), make_prices(), make_scada(), GENS)
        store.write_day(tmp_path, date.fromordinal(d), df)
        frames.append(df)
    hist = store.read_all(tmp_path)
    store.write_latest(tmp_path, hist)
    latest = pd.read_csv(tmp_path / "latest.csv")
    assert latest["date"].nunique() == 30 and latest["date"].max() == hist["date"].max()


def history(values):
    return pd.DataFrame({"date": [f"2026-09-{i + 1:02d}" for i in range(len(values))], "region": "SA1",
                         **{m: 0.0 for m in records.RECORD_METRICS}, "renewable_share": values,
                         "intensity_g_per_kwh": [50.0] * len(values)})


def test_records_detected_against_history():
    h = history([0.5] * 10 + [0.9])
    recs = records.find_records(h, "2026-09-11")
    assert [r["metric"] for r in recs] == ["renewable_share"]
    assert recs[0]["previous"] == 0.5 and recs[0]["value"] == 0.9


def test_no_records_without_enough_history_or_without_beating():
    assert records.find_records(history([0.5, 0.9]), "2026-09-02") == []
    assert records.find_records(history([0.9] * 10 + [0.9]), "2026-09-11") == []


def test_missing_demand_fails_loudly():
    prices = make_prices()
    prices.loc[0, "demand"] = float("nan")
    with pytest.raises(summary.SourceDataError):
        summary.summarise_day(DAY, prices, make_scada(), GENS)


def test_default_day_is_two_days_back_because_the_archive_lags():
    from datetime import UTC, datetime

    from nem_pulse.cli import latest_archived_day

    now = datetime(2026, 10, 12, 20, 30, tzinfo=UTC)  # 06:30 AEST on the 13th
    assert latest_archived_day(now) == date(2026, 10, 11)  # NEM date is the 13th; archive trails by two days


README_TEMPLATE = "# Title\n\n<!-- PULSE:START -->\nold\n<!-- PULSE:END -->\n\nFooter\n"


def _seed(tmp_path, day=DAY):
    """Write one real summary day and a README with markers; return (data dir, readme path)."""
    data = tmp_path / "data"
    p = make_prices()
    p.loc[p["region"] == "VIC1", "rrp"] = -3.0
    store.write_day(data, day, summary.summarise_day(day, p, make_scada(), GENS))
    readme = tmp_path / "README.md"
    readme.write_text(README_TEMPLATE)
    return data, readme


def test_readme_block_is_replaced_between_markers(tmp_path):
    data, readme = _seed(tmp_path)
    cli.render_readme(data, store.read_all(data), readme)
    text = readme.read_text()
    assert text.startswith("# Title\n\n<!-- PULSE:START -->\n_Updated for 2026-09-28")
    assert "old" not in text and text.endswith("<!-- PULSE:END -->\n\nFooter\n")
    assert "| VIC1 | -$3/MWh |" in text  # sign before the dollar sign, not "$-3"


def test_readme_formats_previous_best_like_the_record_value(tmp_path):
    data, readme = _seed(tmp_path)
    pd.DataFrame([
        {"date": "2026-09-28", "region": "NSW1", "metric": "renewable_share",
         "label": "Highest renewable share", "value": 0.434, "previous": 0.4031, "kind": "max"},
        {"date": "2026-09-28", "region": "VIC1", "metric": "min_price",
         "label": "Lowest price", "value": -148.4, "previous": -60.0, "kind": "min"},
    ]).to_csv(data / "records.csv", index=False)
    cli.render_readme(data, store.read_all(data), readme)
    text = readme.read_text()
    assert "highest renewable share (43.4%, previous best 40.3%)" in text
    assert "lowest price (-148.4, previous best -60.0)" in text


class _StubClient:
    def generators(self):
        return GENS


def _stub_fetch(monkeypatch):
    p = make_prices()
    monkeypatch.setattr(cli, "NemClient", _StubClient)
    monkeypatch.setattr(cli, "load_prices_day", lambda day: p.assign(
        interval_end=p["interval_end"] + pd.Timedelta(days=(day - DAY).days)))
    monkeypatch.setattr(cli, "load_scada_day", lambda day: make_scada())


def test_cli_runs_offline_and_rewrites_readme(tmp_path, monkeypatch):
    data, readme = _seed(tmp_path)
    _stub_fetch(monkeypatch)
    argv = ["--date", "2026-09-28", "--data", str(data), "--readme", str(readme),
            "--assets", str(tmp_path / "assets")]
    assert cli.main(argv) == 0
    assert (data / "latest.csv").exists()
    assert sorted(p.name for p in (tmp_path / "assets").iterdir()) == [
        "intensity.png", "price.png", "renewables.png"]
    assert "_Updated for 2026-09-28" in readme.read_text()


def test_cli_exits_2_when_readme_markers_are_missing(tmp_path, monkeypatch, capsys):
    data, readme = _seed(tmp_path)
    readme.write_text("# No markers here\n")
    _stub_fetch(monkeypatch)
    argv = ["--date", "2026-09-28", "--data", str(data), "--readme", str(readme),
            "--assets", str(tmp_path / "assets")]
    assert cli.main(argv) == 2
    assert "PULSE markers" in capsys.readouterr().err


@pytest.mark.parametrize("days", ["0", "-1", "abc"])
def test_cli_rejects_a_days_value_below_one(days):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--days", days])
    assert exc.value.code == 2
