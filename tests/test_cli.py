from gridcheck.__main__ import main


def test_demo_writes_a_report(tmp_path, capsys):
    out = tmp_path / "report.md"
    assert main(["demo", "--out", str(out)]) == 0
    report = out.read_text()
    assert "## Checks" in report and "## Study:" in report
    assert "All fault-ride-through parameters are inside the RfG ranges." in report
    printed = capsys.readouterr().out
    for line in ("PASS                 frt_rides_through", "FAIL                 frt_trips_too_early",
                 "NOT APPLICABLE       frt_fault_too_long", "NEEDS JUSTIFICATION  lfsm_o_slow",
                 "FAIL                 frequency_low_trip"):
        assert line in printed
