"""Command line: run the built-in demo cases against a profile and write a report.

    python -m gridcheck demo
    python -m gridcheck demo --profile profiles/nordic_type_d_synchronous_example.yaml --out report.md --ai
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .checks import check_frequency_withstand, check_frt, check_lfsm_o, check_voltage_band
from .loadflow import reactive_power_sweep
from .profiles import Profile, load_profile
from .report import to_markdown
from .simulate import frequency_metrics, frt_test_record, island_frequency, lfsm_o_test_record, time_axis
from .summary import openai_compatible_client, summarise

DEFAULT_PROFILE = Path(__file__).resolve().parent.parent / "profiles" / "nordic_type_d_synchronous_example.yaml"


def demo_checks(profile: Profile) -> list:
    results = []

    # Fault ride-through: a zero-voltage fault cleared after 150 ms.
    t = time_axis(3.0, 0.001, t_start=-0.2)
    u, connected = frt_test_record(t, u_dip=0.0, t_clear=0.15)
    results.append(check_frt(t, u, connected, profile.frt, check_id="frt_rides_through"))
    u, connected = frt_test_record(t, u_dip=0.0, t_clear=0.15, trip_at=0.40)
    results.append(check_frt(t, u, connected, profile.frt, check_id="frt_trips_too_early"))
    u, connected = frt_test_record(t, u_dip=0.0, t_clear=0.25, trip_at=0.40)
    results.append(check_frt(t, u, connected, profile.frt, check_id="frt_fault_too_long"))

    # LFSM-O: the frequency signal steps from 50.0 to 50.7 Hz at t = 5 s; 40 MW plant at 36 MW.
    t = time_axis(70.0, 0.05)
    f = np.where(t < 5.0, 50.0, 50.7)
    lfsm = dict(p_ref=40.0, threshold_hz=profile.lfsm_o_threshold_hz, droop=profile.lfsm_o_droop)
    for check_id, delay in (("lfsm_o_fast", 0.5), ("lfsm_o_slow", 2.5)):
        p = lfsm_o_test_record(t, f, p0=36.0, delay_s=delay, **lfsm)
        results.append(check_lfsm_o(t, f, p, max_delay_s=profile.lfsm_o_max_delay_s, check_id=check_id, **lfsm))

    # Frequency ranges: the frequency drops to 48.8 Hz and the unit trips after 5 minutes.
    t = time_axis(900.0, 1.0)
    f = np.where(t < 60.0, 50.0, 48.8)
    results.append(check_frequency_withstand(t, f, t < 360.0, profile.frequency_bands,
                                             check_id="frequency_low_trip"))

    # Steady-state voltage at the connection point, exporting 40 MW with 10 Mvar.
    row = reactive_power_sweep([10.0])[0]
    results.append(check_voltage_band(row["connection_point_pu"], profile.voltage_bands,
                                      check_id="voltage_operating_point"))
    return results


def demo_studies(profile: Profile) -> dict:
    t = time_axis(30.0, 0.01)
    inertia = []
    for h in (6.0, 3.0, 1.5):
        f, _ = island_frequency(t, load_step_pu=0.1, inertia_h_s=h, damping_pu=1.0, droop=0.05,
                                governor_tau_s=2.0, f_nominal_hz=profile.f_nominal_hz)
        inertia.append({"inertia_h_s": h, **frequency_metrics(t, f, profile.f_nominal_hz)})
    sweep = reactive_power_sweep([-15.0, 0.0, 15.0, 30.0])
    return {"island grid, 10 % load step (lower inertia = less synchronous generation)": inertia,
            "connection-point voltage vs reactive power, 40 MW export": sweep}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gridcheck")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the built-in cases and write a report")
    demo.add_argument("--profile", default=str(DEFAULT_PROFILE))
    demo.add_argument("--out", default="report.md")
    demo.add_argument("--ai", action="store_true", help="draft the summary with an OpenAI-compatible model")
    args = parser.parse_args(argv)

    profile = load_profile(args.profile)
    results = demo_checks(profile)
    summary, source = summarise(results, openai_compatible_client() if args.ai else None)
    report = to_markdown(results, profile, summary=summary, summary_source=source, studies=demo_studies(profile))
    Path(args.out).write_text(report, encoding="utf-8")
    for r in results:
        print(f"{r.verdict:<20} {r.check_id}")
    print(f"report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
