from pathlib import Path

import numpy as np
import pytest

from gridcheck import FrtProfile, load_profile

EXAMPLE = Path(__file__).resolve().parent.parent / "profiles" / "nordic_type_d_synchronous_example.yaml"


def type_d(**changes):
    values = dict(u_ret=0.0, u_clear=0.25, u_rec1=0.5, u_rec2=0.9,
                  t_clear=0.15, t_rec1=0.45, t_rec2=0.7, t_rec3=1.5, table="7.1")
    values.update(changes)
    return FrtProfile(**values)


def test_lower_limit_follows_the_profile_corners():
    frt = type_d()
    t = np.array([-0.1, 0.0, 0.1, 0.15, 0.30, 0.45, 0.6, 0.7, 1.1, 1.5, 3.0])
    expected = [np.nan, 0.0, 0.0, 0.25, 0.375, 0.5, 0.5, 0.5, 0.7, 0.9, 0.9]
    np.testing.assert_allclose(frt.lower_limit(t), expected, atol=1e-12)


def test_type_b_profile_jumps_straight_to_u_clear():
    # Table 3.1: u_rec1 = u_clear and t_rec1 = t_clear, so there is no first ramp.
    frt = FrtProfile(u_ret=0.3, u_clear=0.7, u_rec1=0.7, u_rec2=0.9,
                     t_clear=0.15, t_rec1=0.15, t_rec2=0.7, t_rec3=1.5, table="3.1")
    np.testing.assert_allclose(frt.lower_limit([0.14, 0.15, 0.5, 1.1]), [0.3, 0.7, 0.7, 0.8], atol=1e-12)
    assert frt.rfg_range_problems() == []


def test_example_profile_is_inside_rfg_ranges():
    profile = load_profile(EXAMPLE)
    assert profile.frt.rfg_range_problems() == []
    assert 50.2 <= profile.lfsm_o_threshold_hz <= 50.5
    assert 0.02 <= profile.lfsm_o_droop <= 0.12


@pytest.mark.parametrize("change, fragment", [
    ({"u_rec1": 0.4}, "u_rec1=0.4"),
    ({"u_clear": 0.3}, "u_clear=0.3"),
    ({"t_rec1": 0.5}, "t_rec1=0.5"),
    ({"t_rec3": 2.0}, "t_rec3=2.0"),
])
def test_out_of_range_parameters_are_reported(change, fragment):
    problems = type_d(**change).rfg_range_problems()
    assert any(fragment in p for p in problems)


def test_table_3_1_requires_u_rec1_equal_to_u_clear():
    frt = FrtProfile(u_ret=0.3, u_clear=0.7, u_rec1=0.8, u_rec2=0.9,
                     t_clear=0.15, t_rec1=0.15, t_rec2=0.7, t_rec3=1.5, table="3.1")
    assert any("must equal u_clear" in p for p in frt.rfg_range_problems())


def test_nordic_frequency_bands_load():
    bands = load_profile(EXAMPLE).frequency_bands
    unlimited = [b for b in bands if b.minutes is None]
    assert [(b.low, b.high) for b in unlimited] == [(49.0, 51.0)]
