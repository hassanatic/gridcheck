import numpy as np
import pytest

from gridcheck.simulate import frequency_metrics, island_frequency, lfsm_o_test_record, time_axis


def test_time_axis_has_no_float_noise():
    t = time_axis(1.0, 0.001, t_start=-0.2)
    assert t[600] == 0.4
    assert t[0] == -0.2 and t[-1] == 1.0


def test_island_frequency_matches_the_steady_state_formula():
    t = time_axis(60.0, 0.01)
    f, dpm = island_frequency(t, load_step_pu=0.1, inertia_h_s=3.0, damping_pu=1.0, droop=0.05, governor_tau_s=2.0)
    # df = -dPload / (D + 1/R) = -0.1 / 21
    assert f[-1] == pytest.approx(50.0 * (1 - 0.1 / 21), abs=1e-4)
    # the governor ends up covering the load step minus what damping absorbs
    assert dpm[-1] == pytest.approx((0.1 / 21) / 0.05, abs=1e-4)


def test_initial_rate_of_change_of_frequency_is_set_by_inertia():
    t = time_axis(0.2, 0.001)
    f, _ = island_frequency(t, load_step_pu=0.1, inertia_h_s=3.0, damping_pu=1.0, droop=0.05, governor_tau_s=2.0)
    initial_rocof = (f[10] - f[0]) / (t[10] - t[0])
    assert initial_rocof == pytest.approx(-0.1 * 50.0 / (2 * 3.0), rel=0.02)


def test_less_inertia_means_a_deeper_and_faster_nadir():
    t = time_axis(30.0, 0.01)
    metrics = []
    for h in (6.0, 1.5):
        f, _ = island_frequency(t, load_step_pu=0.1, inertia_h_s=h, damping_pu=1.0, droop=0.05, governor_tau_s=2.0)
        metrics.append(frequency_metrics(t, f))
    high, low = metrics
    assert low["nadir_hz"] < high["nadir_hz"]
    assert low["nadir_time_s"] < high["nadir_time_s"]
    assert low["final_hz"] == high["final_hz"]  # inertia changes the path, not the end point


def test_lfsm_o_record_settles_on_the_droop_target():
    t = time_axis(60.0, 0.05)
    f = np.where(t < 5.0, 50.0, 50.45)
    p = lfsm_o_test_record(t, f, p0=30.0, p_ref=40.0, threshold_hz=50.2, droop=0.05)
    assert p[-1] == pytest.approx(30.0 - 40.0 * (0.25 / 50.0) / 0.05, abs=1e-3)
    assert np.all(p[t < 5.0 + 0.5] == 30.0)  # nothing happens during the dead time
