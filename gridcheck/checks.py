"""Compliance checks on measured or simulated test records.

Every check returns a CheckResult with a verdict and the numbers behind it, so a reviewer can
see why, not just what. Verdicts:

PASS                 the record shows the requirement is met
FAIL                 the record shows it is not met
NOT APPLICABLE       the record cannot show either way (for example the test never reached
                     the condition the requirement is about)
NEEDS JUSTIFICATION  allowed by the grid code only with technical evidence given to the TSO
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .profiles import RFG_FRT_ARTICLE, Band, FrtProfile

PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT APPLICABLE"
NEEDS_JUSTIFICATION = "NEEDS JUSTIFICATION"


@dataclass
class CheckResult:
    check_id: str
    requirement: str
    verdict: str
    evidence: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.verdict == FAIL


def check_frt(t, u, connected, frt: FrtProfile, *, check_id: str = "frt", tol_pu: float = 0.0) -> CheckResult:
    """Fault ride-through: did the module stay connected while the voltage stayed above the profile?

    t is in seconds with t = 0 at fault inception, u is the connection-point voltage in pu, and
    connected is True while the module is connected to the network.
    """
    requirement = f"{RFG_FRT_ARTICLE[frt.table]}: stay connected while the voltage is above the profile"
    t, u, connected = np.asarray(t, float), np.asarray(u, float), np.asarray(connected, bool)
    after = t >= 0
    if not after.any():
        raise ValueError("the record has no samples at or after fault inception (t >= 0)")

    ta, ua, ca = t[after], u[after], connected[after]
    margin = ua - frt.lower_limit(ta)
    tripped = np.flatnonzero(~ca)
    first_trip = round(float(ta[tripped[0]]), 4) if tripped.size else None
    evidence = {"min_margin_pu": round(float(margin.min()), 4), "first_trip_s": first_trip}

    below = np.flatnonzero(margin < -tol_pu)
    if below.size:
        first_below = round(float(ta[below[0]]), 4)
        if first_trip is None or first_below <= first_trip:
            evidence["below_profile_at_s"] = first_below
            return CheckResult(check_id, requirement, NOT_APPLICABLE, evidence, [
                f"The voltage went below the lower limit at {first_below:.3f} s, so disconnection "
                "was permitted from then on. This record cannot demonstrate fault ride-through."])

    if first_trip is not None:
        return CheckResult(check_id, requirement, FAIL, evidence, [
            f"Disconnected at {first_trip:.3f} s while the voltage was still above the lower limit."])
    return CheckResult(check_id, requirement, PASS, evidence)


def check_lfsm_o(t, f, p, *, p_ref: float, threshold_hz: float, droop: float, f_nominal_hz: float = 50.0,
                 max_delay_s: float = 2.0, detect_fraction: float = 0.01, settle_s: float = 10.0,
                 droop_tolerance: float = 0.10, check_id: str = "lfsm_o") -> CheckResult:
    """Limited frequency sensitive mode, over-frequency (RfG Art. 13(2)).

    Above the threshold the module reduces active power along the droop:
        dP / Pref = -((f - f_threshold) / f_nominal) / droop
    The record must end with a steady over-frequency plateau of at least settle_s seconds,
    which is where the steady-state droop is measured.
    """
    requirement = "RfG Art. 13(2): LFSM-O active power reduction along the set droop"
    t, f, p = np.asarray(t, float), np.asarray(f, float), np.asarray(p, float)

    settings = []
    if not 50.2 <= threshold_hz <= 50.5:
        settings.append(f"threshold {threshold_hz} Hz is outside the RfG range 50.2-50.5 Hz")
    if not 0.02 <= droop <= 0.12:
        settings.append(f"droop {droop:.0%} is outside the RfG range 2-12 %")

    above = np.flatnonzero(f > threshold_hz)
    if not above.size:
        return CheckResult(check_id, requirement, NOT_APPLICABLE, {}, settings + [
            "The frequency never exceeded the threshold, so LFSM-O was not exercised."])

    i_cross = above[0]
    t_cross = float(t[i_cross])
    p_pre = float(np.median(p[: max(i_cross, 1)]))
    reduced = np.flatnonzero((t >= t_cross) & (p <= p_pre - detect_fraction * p_ref))
    if not reduced.size:
        return CheckResult(check_id, requirement, FAIL, {"p_before_mw": round(p_pre, 3)}, settings + [
            "No active power reduction was detected after the threshold was crossed."])
    delay = float(t[reduced[0]]) - t_cross

    tail = t >= t[-1] - settle_s
    if not np.all(f[tail] > threshold_hz):
        return CheckResult(check_id, requirement, NOT_APPLICABLE, {"delay_s": round(delay, 3)}, settings + [
            f"The record must end with at least {settle_s:g} s above the threshold to measure the droop."])
    f_ss, p_ss = float(f[tail].mean()), float(p[tail].mean())
    reduction = p_pre - p_ss
    measured_droop = ((f_ss - threshold_hz) / f_nominal_hz) / (reduction / p_ref) if reduction > 0 else float("inf")
    expected_reduction = p_ref * ((f_ss - threshold_hz) / f_nominal_hz) / droop

    evidence = {
        "delay_s": round(delay, 3),
        "p_before_mw": round(p_pre, 3),
        "p_steady_mw": round(p_ss, 3),
        "reduction_mw": round(reduction, 3),
        "expected_reduction_mw": round(expected_reduction, 3),
        "measured_droop": round(measured_droop, 4),
        "set_droop": droop,
    }
    notes = list(settings)
    droop_ok = abs(measured_droop - droop) <= droop_tolerance * droop
    if not droop_ok:
        notes.append(f"Measured droop {measured_droop:.2%} differs from the set {droop:.0%} "
                     f"by more than {droop_tolerance:.0%}.")
    if settings or not droop_ok:
        return CheckResult(check_id, requirement, FAIL, evidence, notes)
    if delay > max_delay_s:
        return CheckResult(check_id, requirement, NEEDS_JUSTIFICATION, evidence, notes + [
            f"Initial delay {delay:.2f} s is above {max_delay_s:g} s: the owner must justify it to the TSO."])
    return CheckResult(check_id, requirement, PASS, evidence, notes)


def _band_for(value: float, bands: tuple[Band, ...]) -> Band | None:
    """The most demanding band containing value (unlimited beats any finite time)."""
    matches = [b for b in bands if b.contains(value)]
    if not matches:
        return None
    return max(matches, key=lambda b: float("inf") if b.minutes is None else b.minutes)


def check_frequency_withstand(t, f, connected, bands: tuple[Band, ...], *,
                              check_id: str = "frequency_ranges") -> CheckResult:
    """Frequency ranges (RfG Art. 13(1)(a), Table 2): no disconnection before the minimum time.

    t is in seconds, f in Hz. Only the first disconnection is judged.
    """
    requirement = "RfG Art. 13(1)(a), Table 2: stay connected for the minimum time in each frequency range"
    t, f, connected = np.asarray(t, float), np.asarray(f, float), np.asarray(connected, bool)
    trips = np.flatnonzero(~connected)
    if not trips.size:
        return CheckResult(check_id, requirement, PASS, {"first_trip_s": None},
                           ["Stayed connected for the whole record."])

    i = int(trips[0])
    f_trip = float(f[i - 1] if i > 0 else f[i])
    band = _band_for(f_trip, bands)
    evidence = {"first_trip_s": round(float(t[i]), 3), "frequency_at_trip_hz": round(f_trip, 3)}
    if band is None:
        return CheckResult(check_id, requirement, PASS, evidence, [
            "The frequency was outside every required range, so disconnection was permitted."])
    if band.minutes is None:
        return CheckResult(check_id, requirement, FAIL, evidence, [
            f"Disconnected at {f_trip:.2f} Hz, inside the range {band.low}-{band.high} Hz where "
            "operation must be unlimited."])

    j = i - 1
    while j >= 0 and band.contains(float(f[j])):
        j -= 1
    minutes_in_band = (float(t[i]) - float(t[j + 1])) / 60.0
    evidence["minutes_in_range_before_trip"] = round(minutes_in_band, 2)
    evidence["required_minutes"] = band.minutes
    if minutes_in_band < band.minutes:
        return CheckResult(check_id, requirement, FAIL, evidence, [
            f"Disconnected after {minutes_in_band:.1f} min in {band.low}-{band.high} Hz; "
            f"the requirement is at least {band.minutes:g} min."])
    return CheckResult(check_id, requirement, PASS, evidence, [
        "Disconnected only after the minimum time in that range."])


def check_voltage_band(u_pu: float, bands: tuple[Band, ...], *, check_id: str = "voltage_range") -> CheckResult:
    """Is a planned steady-state operating point inside the unlimited-time voltage range?

    Table 6.1 says how long the module must be able to run at each connection-point voltage
    without disconnecting. A steady operating point outside the unlimited range is only covered
    for a limited time, so this check flags it.
    """
    requirement = "RfG Art. 16(2)(a), Table 6.1: operating point inside the unlimited-time voltage range"
    band = _band_for(u_pu, bands)
    evidence = {"voltage_pu": round(float(u_pu), 4)}
    if band is None:
        return CheckResult(check_id, requirement, FAIL, evidence, ["Outside every required voltage range."])
    if band.minutes is None:
        return CheckResult(check_id, requirement, PASS, evidence)
    return CheckResult(check_id, requirement, FAIL, evidence, [
        f"{u_pu:.3f} pu is only required for {band.minutes:g} min ({band.low}-{band.high} pu), "
        "not for continuous operation."])
