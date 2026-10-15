"""Load-flow model of an engine power plant connected to a 110 kV grid, built with pandapower.

  engine generating sets (11 kV) -> step-up transformer 11/110 kV -> 110 kV line -> grid

The generating sets are one PQ injection: fixed active and reactive power, as in reactive
power control mode. For voltage control mode use pandapower's create_gen with a vm_pu setpoint.
"""
from __future__ import annotations

import pandapower as pp

CONNECTION_POINT = "connection point 110 kV"


def engine_plant(*, units: int = 4, unit_mw: float = 10.0, q_mvar: float = 0.0,
                 line_km: float = 20.0, grid_vm_pu: float = 1.0):
    net = pp.create_empty_network(name="engine power plant", f_hz=50.0)
    gen_bus = pp.create_bus(net, vn_kv=11.0, name="generator bus 11 kV")
    poc = pp.create_bus(net, vn_kv=110.0, name=CONNECTION_POINT)
    grid = pp.create_bus(net, vn_kv=110.0, name="grid 110 kV")
    pp.create_ext_grid(net, grid, vm_pu=grid_vm_pu, name="transmission grid")
    pp.create_line(net, poc, grid, length_km=line_km, std_type="149-AL1/24-ST1A 110.0", name="110 kV line")
    pp.create_transformer_from_parameters(
        net, hv_bus=poc, lv_bus=gen_bus, sn_mva=60.0, vn_hv_kv=110.0, vn_lv_kv=11.0,
        vkr_percent=0.4, vk_percent=12.0, pfe_kw=25.0, i0_percent=0.05, name="step-up transformer")
    pp.create_sgen(net, gen_bus, p_mw=units * unit_mw, q_mvar=q_mvar, name="engine generating sets")
    return net


def solve(net) -> dict:
    """Run the load flow and return the numbers a compliance review looks at first."""
    pp.runpp(net, numba=False)  # numba is optional; without it pandapower warns on every run
    poc = net.bus.index[net.bus.name == CONNECTION_POINT][0]
    return {
        "connection_point_pu": round(float(net.res_bus.vm_pu.at[poc]), 4),
        "line_loading_percent": round(float(net.res_line.loading_percent.iloc[0]), 1),
        "transformer_loading_percent": round(float(net.res_trafo.loading_percent.iloc[0]), 1),
        "grid_import_mw": round(float(net.res_ext_grid.p_mw.iloc[0]), 3),
    }


def reactive_power_sweep(q_values_mvar, **plant_kwargs) -> list[dict]:
    """Connection-point voltage for several reactive power setpoints (positive = export)."""
    rows = []
    for q in q_values_mvar:
        row = solve(engine_plant(q_mvar=q, **plant_kwargs))
        rows.append({"q_mvar": q, **row})
    return rows
