from pathlib import Path

import numpy as np

from gridcheck import (FAIL, NEEDS_JUSTIFICATION, NOT_APPLICABLE, PASS, check_frequency_withstand, check_frt,
                       check_lfsm_o, check_voltage_band, load_profile)
from gridcheck.simulate import frt_test_record, lfsm_o_test_record, time_axis

PROFILE = load_profile(Path(__file__).resolve().parent.parent / "profiles" / "nordic_type_d_synchronous_example.yaml")
LFSM = dict(p_ref=40.0, threshold_hz=50.2, droop=0.05)


def frt_case(**kwargs):
    t = time_axis(3.0, 0.001, t_start=-0.2)
    u, connected = frt_test_record(t, **kwargs)
    return check_frt(t, u, connected, PROFILE.frt)


def test_frt_pass_when_unit_stays_connected():
    assert frt_case(u_dip=0.0, t_clear=0.15).verdict == PASS


def test_frt_fail_when_unit_trips_above_the_profile():
    result = frt_case(u_dip=0.0, t_clear=0.15, trip_at=0.4)
    assert result.verdict == FAIL
    assert result.evidence["first_trip_s"] == 0.4


def test_frt_not_applicable_when_voltage_falls_below_the_profile_first():
    # The fault lasts 250 ms, longer than the profile's 150 ms clearing time.
    result = frt_case(u_dip=0.0, t_clear=0.25, trip_at=0.4)
    assert result.verdict == NOT_APPLICABLE
    assert result.evidence["below_profile_at_s"] == 0.15


def test_frt_trip_before_the_voltage_leaves_the_profile_is_still_a_fail():
    result = frt_case(u_dip=0.0, t_clear=0.25, trip_at=0.1)
    assert result.verdict == FAIL


def lfsm_case(delay_s=0.5, record_droop=0.05, end_hz=50.7, **check_kwargs):
    t = time_axis(70.0, 0.05)
    f = np.where(t < 5.0, 50.0, end_hz)
    p = lfsm_o_test_record(t, f, p0=36.0, p_ref=40.0, threshold_hz=50.2, droop=record_droop, delay_s=delay_s)
    return check_lfsm_o(t, f, p, **{**LFSM, **check_kwargs})


def test_lfsm_o_pass_with_droop_and_short_delay():
    result = lfsm_case()
    assert result.verdict == PASS
    assert abs(result.evidence["measured_droop"] - 0.05) < 1e-3
    # 0.5 Hz above the threshold with 5 % droop: 40 MW * (0.5/50) / 0.05 = 8 MW
    assert abs(result.evidence["reduction_mw"] - 8.0) < 0.01


def test_lfsm_o_long_delay_needs_justification():
    assert lfsm_case(delay_s=2.5).verdict == NEEDS_JUSTIFICATION


def test_lfsm_o_wrong_droop_fails():
    assert lfsm_case(record_droop=0.08).verdict == FAIL


def test_lfsm_o_setting_outside_rfg_range_fails():
    result = lfsm_case(droop=0.15)
    assert result.verdict == FAIL
    assert any("2-12 %" in n for n in result.notes)


def test_lfsm_o_not_exercised_below_threshold():
    assert lfsm_case(end_hz=50.1).verdict == NOT_APPLICABLE


def frequency_case(trip_after_s, level_hz):
    t = time_axis(3600.0, 1.0)
    f = np.where(t < 60.0, 50.0, level_hz)
    connected = t < 60.0 + trip_after_s
    return check_frequency_withstand(t, f, connected, PROFILE.frequency_bands)


def test_frequency_trip_after_minimum_time_passes():
    assert frequency_case(31 * 60, 48.8).verdict == PASS


def test_frequency_trip_before_minimum_time_fails():
    result = frequency_case(5 * 60, 48.8)
    assert result.verdict == FAIL
    assert result.evidence["required_minutes"] == 30


def test_frequency_trip_in_the_unlimited_range_fails():
    assert frequency_case(20 * 60, 49.5).verdict == FAIL


def test_frequency_trip_outside_all_ranges_is_permitted():
    assert frequency_case(10, 47.0).verdict == PASS


def test_voltage_band():
    assert check_voltage_band(1.02, PROFILE.voltage_bands).verdict == PASS
    assert check_voltage_band(1.07, PROFILE.voltage_bands).verdict == FAIL
    assert check_voltage_band(0.85, PROFILE.voltage_bands).verdict == FAIL
