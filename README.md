# gridcheck

Grid code compliance checks for power plant test records, in Python.

Compliance testing of a power plant produces many time-series records: voltage dips for fault
ride-through, frequency steps for active power response, long frequency excursions. Each one has
to be checked against the grid code and the result documented. `gridcheck` automates that check
and keeps the evidence next to every verdict. It can also ask a language model to draft a
plain-language summary, but the model cannot change a verdict (see [AI summary](#ai-summary)).

The requirements come from the EU network code on requirements for generators,
Commission Regulation (EU) 2016/631 ("RfG").

## What it checks

| Check | Grid code clause | Question it answers |
|---|---|---|
| `check_frt` | RfG Art. 14(3)(a) Table 3.1 (types B, C) and Art. 16(3)(a) Table 7.1 (type D), synchronous modules | Did the unit stay connected while the voltage stayed above the voltage-against-time profile? |
| `check_lfsm_o` | RfG Art. 13(2) | Above the threshold, did active power drop along the set droop, and how long was the initial delay? |
| `check_frequency_withstand` | RfG Art. 13(1)(a) Table 2 | Did the unit stay connected for the minimum time in each frequency range? |
| `check_voltage_band` | RfG Art. 16(2)(a) Table 6.1 | Is a planned operating point inside the voltage range with unlimited operation time? |
| `FrtProfile.rfg_range_problems` | Tables 3.1 and 7.1 | Are a profile's chosen parameters inside the RfG ranges? |

Verdicts are `PASS`, `FAIL`, `NOT APPLICABLE` (the record cannot show either way) and
`NEEDS JUSTIFICATION` (allowed only with technical evidence to the TSO, the transmission system
operator).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
python -m gridcheck demo          # runs the built-in cases, writes report.md
pytest -q                         # 38 tests
```

```text
PASS                 frt_rides_through
FAIL                 frt_trips_too_early
NOT APPLICABLE       frt_fault_too_long
PASS                 lfsm_o_fast
NEEDS JUSTIFICATION  lfsm_o_slow
FAIL                 frequency_low_trip
PASS                 voltage_operating_point
report written to report.md
```

## How the checks work

### Fault ride-through (FRT)
The profile is the **lower limit** of the connection-point voltage during and after a fault, in
per unit (pu), with t = 0 at fault inception. It is built from eight parameters.

The line joins these points (t in seconds, u in pu):

| From | To | Shape |
|---|---|---|
| (0, u_ret) | (t_clear, u_ret) | flat: the fault is on |
| (t_clear, u_ret) | (t_clear, u_clear) | vertical step: the fault is cleared |
| (t_clear, u_clear) | (t_rec1, u_rec1) | straight ramp |
| (t_rec1, u_rec1) | (t_rec2, u_rec1) | flat |
| (t_rec2, u_rec1) | (t_rec3, u_rec2) | straight ramp |
| (t_rec3, u_rec2) | onwards | flat |

The example type D profile uses u_ret 0, u_clear 0.25, u_rec1 0.5, u_rec2 0.9 pu and t_clear
0.15, t_rec1 0.45, t_rec2 0.7, t_rec3 1.5 s, all inside the ranges of RfG Table 7.1.

While the voltage stays above this line, the unit must stay connected. So for a test record:
- voltage above the profile and the unit stayed connected: **PASS**
- voltage above the profile and the unit tripped: **FAIL**
- voltage went below the profile before any trip: **NOT APPLICABLE**, because a trip was
  permitted from that moment, so the record cannot demonstrate ride-through.

### LFSM-O (limited frequency sensitive mode, over-frequency)
Above the threshold frequency the unit reduces active power along the droop:

```
dP / Pref = -((f - f_threshold) / f_nominal) / droop
```

Example: threshold 50.2 Hz, droop 5 %, frequency at 50.7 Hz, Pref 40 MW:
`40 x (0.5 / 50) / 0.05 = 8 MW` less. The RfG allows thresholds of 50.2 to 50.5 Hz and droops
of 2 to 12 %. The initial delay should be as short as possible; above two seconds it must be
justified to the TSO, which is why a slow response gets `NEEDS JUSTIFICATION`, not `FAIL`.

### Frequency ranges
Table 2 gives the minimum time a unit must stay connected in each range. For the Nordic area:
47.5 to 48.5 Hz for 30 minutes, 48.5 to 49.0 Hz for at least 30 minutes (set by the TSO),
49.0 to 51.0 Hz without limit, and 51.0 to 51.5 Hz for 30 minutes. A disconnection is judged
by the range the frequency was in and how long it had been there.

### Voltage ranges
Table 6.1 (110 to 300 kV connection points, Nordic): 0.90 to 1.05 pu without time limit,
1.05 to 1.10 pu for 60 minutes. A steady operating point outside the unlimited range is flagged.

## Models and studies

`simulate.py` creates test records so every check can run without plant data:
- a fault test: dip, clearance, then recovery, with an optional protection trip;
- an over-frequency test: the droop target with a dead time and a first-order lag, a simple
  stand-in for governor and engine response;
- an island grid after a load step: the aggregated **swing equation** with a droop governor,

```
2H d(df)/dt = dPm - dPload - D*df
Tg d(dPm)/dt = -dPm - df/R
```

where H is the inertia constant, D the load damping, R the droop and Tg the governor time
constant (all per unit). The tests check it against the textbook results: the steady-state
deviation `-dPload / (D + 1/R)` and the initial rate of change of frequency `-dPload / (2H)`.

`loadflow.py` is a [pandapower](https://www.pandapower.org/) model of an engine power plant:
four 10 MW generating sets at 11 kV, an 11/110 kV step-up transformer and a 20 km 110 kV line to
the grid. It sweeps the reactive power setpoint and reports the connection-point voltage and the
line and transformer loading.

The demo report includes two small studies:

| Inertia H (s) | Nadir (Hz) | Time of nadir (s) | RoCoF over first 0.5 s (Hz/s) | Final (Hz) |
|---|---|---|---|---|
| 6.0 | 49.521 | 2.03 | -0.395 | 49.762 |
| 3.0 | 49.367 | 1.33 | -0.748 | 49.762 |
| 1.5 | 49.161 | 0.89 | -1.343 | 49.762 |

Less inertia (less synchronous generation online) makes the frequency fall faster and deeper
after the same 10 % load step, while the final frequency, set by droop and damping, is the same.

| Q (Mvar) | Connection point (pu) | Line loading (%) | Transformer loading (%) |
|---|---|---|---|
| -15 | 0.9996 | 49.3 | 73.6 |
| 0 | 1.0104 | 44.2 | 66.0 |
| 15 | 1.0203 | 45.7 | 67.9 |
| 30 | 1.0294 | 51.9 | 76.8 |

## AI summary

`python -m gridcheck demo --ai` asks an OpenAI-compatible model (set `GRIDCHECK_LLM_BASE_URL`,
`GRIDCHECK_LLM_MODEL`, `GRIDCHECK_LLM_API_KEY`) to write the summary for a reader who is not a
power systems engineer. The verdicts never come from the model. A draft is used only if it names
every failed check and does not claim full compliance while something failed; otherwise, or if
the model is unreachable, the summary is built from the results. The report says which one wrote
it.

## Profiles

`profiles/nordic_type_d_synchronous_example.yaml` holds an example profile. The **ranges** are
from the RfG; the **values** are illustrative choices inside those ranges. Binding values come
from the relevant TSO's national requirements (in Finland, Fingrid). Copy the file and enter the
real values for a real project.

## Limits

- RMS-level, single-machine models. No electromagnetic transients, no protection models, no
  detailed excitation or governor models. Detailed studies belong in tools such as PowerFactory
  or PSCAD; this project checks test records and makes the basic physics visible.
- The generating sets are one PQ injection in the load flow (reactive power control mode).
- Only the first disconnection in a record is judged.
- Covers a subset of the RfG. It is a learning and automation project, not a certification tool.

## License

MIT
