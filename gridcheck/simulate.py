"""Synthetic test records and simple dynamic models.

They let the checks run without plant measurements, and they make the physics visible.
They are deliberately simple (RMS-level, single machine). Detailed studies belong in tools
such as PowerFactory or PSCAD.
"""
from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp


def time_axis(t_end: float, dt: float, t_start: float = 0.0) -> np.ndarray:
    n = int(round((t_end - t_start) / dt)) + 1
    return np.round(t_start + dt * np.arange(n), 9)  # no 0.40099999 float noise


def frt_test_record(t, *, u_dip: float, t_clear: float, u_after_clear: float = 0.8,
                    recovery_tau_s: float = 0.3, trip_at: float | None = None):
    """Connection-point voltage for a fault test, and the connection status.

    1 pu before the fault, u_dip from t = 0 until the fault is cleared at t_clear, then a jump
    to u_after_clear and an exponential recovery towards 1 pu. trip_at simulates a protection
    trip at that time.
    """
    t = np.asarray(t, float)
    u = np.ones_like(t)
    u[(t >= 0) & (t < t_clear)] = u_dip
    after = t >= t_clear
    u[after] = 1.0 - (1.0 - u_after_clear) * np.exp(-(t[after] - t_clear) / recovery_tau_s)
    connected = np.ones(t.shape, dtype=bool)
    if trip_at is not None:
        connected[t >= trip_at] = False
    return u, connected


def lfsm_o_test_record(t, f, *, p0: float, p_ref: float, threshold_hz: float, droop: float,
                       f_nominal_hz: float = 50.0, delay_s: float = 0.5, tau_s: float = 2.0) -> np.ndarray:
    """Plant active power (MW) during an over-frequency test.

    The droop target, delayed by a dead time and smoothed by a first-order lag: a simple
    stand-in for governor and engine response.
    """
    t, f = np.asarray(t, float), np.asarray(f, float)
    target = p0 - p_ref * np.clip(f - threshold_hz, 0.0, None) / f_nominal_hz / droop
    delayed = np.interp(t - delay_s, t, target, left=target[0])
    p = np.empty_like(t)
    p[0] = p0
    for k in range(1, t.size):
        dt = t[k] - t[k - 1]
        p[k] = p[k - 1] + (delayed[k] - p[k - 1]) * dt / tau_s
    return p


def island_frequency(t, *, load_step_pu: float, inertia_h_s: float, damping_pu: float,
                     droop: float, governor_tau_s: float, f_nominal_hz: float = 50.0):
    """Frequency of an island grid after a sudden load increase at t = 0.

    Aggregated swing equation with a droop governor (per unit, on the generation base):
        2H d(df)/dt = dPm - dPload - D*df
        Tg d(dPm)/dt = -dPm - df/R
    Returns (frequency in Hz, change in mechanical power in pu).
    Steady state: df = -dPload / (D + 1/R). Initial rate of change: -dPload / (2H) pu/s.
    """
    t = np.asarray(t, float)

    def rhs(_, x):
        df, dpm = x
        return [(dpm - load_step_pu - damping_pu * df) / (2.0 * inertia_h_s),
                (-dpm - df / droop) / governor_tau_s]

    sol = solve_ivp(rhs, (t[0], t[-1]), [0.0, 0.0], t_eval=t, max_step=0.01, rtol=1e-8, atol=1e-10)
    if not sol.success:
        raise RuntimeError(sol.message)
    return f_nominal_hz * (1.0 + sol.y[0]), sol.y[1]


def frequency_metrics(t, f, f_nominal_hz: float = 50.0, rocof_window_s: float = 0.5) -> dict:
    """Nadir, time of nadir and the rate of change of frequency over the first window."""
    t, f = np.asarray(t, float), np.asarray(f, float)
    i_nadir = int(np.argmin(f))
    i_win = int(np.searchsorted(t, t[0] + rocof_window_s))
    rocof = (f[i_win] - f[0]) / (t[i_win] - t[0])
    return {"nadir_hz": round(float(f[i_nadir]), 3), "nadir_time_s": round(float(t[i_nadir]), 2),
            "rocof_hz_per_s": round(float(rocof), 3), "final_hz": round(float(f[-1]), 3)}
