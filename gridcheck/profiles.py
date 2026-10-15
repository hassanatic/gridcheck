"""Requirement profiles: what a grid code asks of a power-generating module.

The shapes and the allowed parameter ranges come from Commission Regulation (EU) 2016/631,
the EU network code on requirements for generators ("RfG"). The values inside a profile are
chosen by the relevant TSO (transmission system operator) within those ranges, so a profile
file always says where its numbers came from.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np
import yaml

# Fault-ride-through parameter ranges for SYNCHRONOUS power-generating modules.
# Table 3.1 (Art. 14(3)(a)) applies to types B and C; Table 7.1 (Art. 16(3)(a)) to type D.
# (lo, hi) is an inclusive range. A string means "must equal that parameter".
# A tuple whose lower end is a string means "from that parameter up to hi".
RFG_FRT_RANGES: dict[str, dict] = {
    "3.1": {
        "u_ret": (0.05, 0.30),
        "u_clear": (0.70, 0.90),
        "u_rec1": "u_clear",
        "u_rec2": (0.85, 0.90),
        "t_clear": (0.14, 0.25),
        "t_rec1": "t_clear",
        "t_rec2": ("t_rec1", 0.70),
        "t_rec3": ("t_rec2", 1.50),
    },
    "7.1": {
        "u_ret": (0.0, 0.0),
        "u_clear": (0.25, 0.25),
        "u_rec1": (0.50, 0.70),
        "u_rec2": (0.85, 0.90),
        "t_clear": (0.14, 0.25),
        "t_rec1": ("t_clear", 0.45),
        "t_rec2": ("t_rec1", 0.70),
        "t_rec3": ("t_rec2", 1.50),
    },
}

RFG_FRT_ARTICLE = {"3.1": "RfG Art. 14(3)(a), Table 3.1", "7.1": "RfG Art. 16(3)(a), Table 7.1"}


@dataclass(frozen=True)
class FrtProfile:
    """Voltage-against-time profile for fault ride-through (RfG Figure 3).

    It is the LOWER LIMIT of the phase-to-phase voltage at the connection point, in pu,
    with t = 0 at fault inception. While the voltage stays above it, the module must stay
    connected and keep operating stably.
    """

    u_ret: float
    u_clear: float
    u_rec1: float
    u_rec2: float
    t_clear: float
    t_rec1: float
    t_rec2: float
    t_rec3: float
    table: str = "7.1"

    def lower_limit(self, t) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        u = np.full(t.shape, self.u_rec2)
        u[t < self.t_rec3] = self.u_rec1  # overwritten below for the earlier segments

        # t_rec2 .. t_rec3: straight line from u_rec1 up to u_rec2
        ramp2 = (t >= self.t_rec2) & (t < self.t_rec3)
        if self.t_rec3 > self.t_rec2:
            share = (t[ramp2] - self.t_rec2) / (self.t_rec3 - self.t_rec2)
            u[ramp2] = self.u_rec1 + (self.u_rec2 - self.u_rec1) * share

        # t_clear .. t_rec1: straight line from u_clear up to u_rec1
        ramp1 = (t >= self.t_clear) & (t < self.t_rec1)
        if self.t_rec1 > self.t_clear:
            share = (t[ramp1] - self.t_clear) / (self.t_rec1 - self.t_clear)
            u[ramp1] = self.u_clear + (self.u_rec1 - self.u_clear) * share

        u[(t >= 0) & (t < self.t_clear)] = self.u_ret  # during the fault
        u[t < 0] = np.nan  # before the fault the profile says nothing
        return u

    def rfg_range_problems(self) -> list[str]:
        """Parameters that fall outside the RfG range for this table (empty list = all inside)."""
        problems = []
        for name, rule in RFG_FRT_RANGES[self.table].items():
            value = getattr(self, name)
            if isinstance(rule, str):
                if not math.isclose(value, getattr(self, rule)):
                    problems.append(f"{name}={value} must equal {rule}={getattr(self, rule)}")
                continue
            lo, hi = rule
            lo = getattr(self, lo) if isinstance(lo, str) else lo
            if not lo - 1e-9 <= value <= hi + 1e-9:
                problems.append(f"{name}={value} is outside [{lo}, {hi}] ({RFG_FRT_ARTICLE[self.table]})")
        if self.table == "3.1" and self.u_rec2 < self.u_clear:
            problems.append(f"u_rec2={self.u_rec2} must be >= u_clear={self.u_clear} (Table 3.1)")
        return problems


@dataclass(frozen=True)
class Band:
    """A frequency or voltage range and how long the module must (or may) operate in it."""

    low: float
    high: float
    minutes: float | None  # None means unlimited

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high


@dataclass(frozen=True)
class Profile:
    name: str
    source: str
    note: str
    frt: FrtProfile
    lfsm_o_threshold_hz: float
    lfsm_o_droop: float
    lfsm_o_max_delay_s: float
    frequency_bands: tuple[Band, ...]
    voltage_bands: tuple[Band, ...]
    f_nominal_hz: float = 50.0


def _bands(rows, low_key, high_key, minutes_key) -> tuple[Band, ...]:
    return tuple(Band(float(r[low_key]), float(r[high_key]), r.get(minutes_key)) for r in rows)


def load_profile(path: str | Path) -> Profile:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    frt_fields = {f.name for f in fields(FrtProfile)}
    frt = FrtProfile(**{k: (str(v) if k == "table" else float(v)) for k, v in data["frt"].items() if k in frt_fields})
    lfsm = data["lfsm_o"]
    return Profile(
        name=data["name"],
        source=data["source"],
        note=data.get("note", "").strip(),
        frt=frt,
        lfsm_o_threshold_hz=float(lfsm["f_threshold_hz"]),
        lfsm_o_droop=float(lfsm["droop"]),
        lfsm_o_max_delay_s=float(lfsm["max_delay_s"]),
        frequency_bands=_bands(data["frequency_ranges"], "f_min", "f_max", "min_minutes"),
        voltage_bands=_bands(data["voltage_ranges_110_300kv"], "u_min", "u_max", "max_minutes"),
        f_nominal_hz=float(data.get("f_nominal_hz", 50.0)),
    )
