from gridcheck.loadflow import engine_plant, reactive_power_sweep, solve


def test_load_flow_converges_and_exports_power():
    result = solve(engine_plant(q_mvar=0.0))
    assert 0.95 < result["connection_point_pu"] < 1.05
    # 40 MW generated; the grid receives it minus transformer and line losses
    assert -40.0 < result["grid_import_mw"] < -38.5


def test_exporting_reactive_power_raises_the_connection_point_voltage():
    rows = reactive_power_sweep([-15.0, 0.0, 15.0])
    voltages = [row["connection_point_pu"] for row in rows]
    assert voltages == sorted(voltages)


def test_longer_line_means_a_bigger_voltage_rise():
    short = solve(engine_plant(q_mvar=15.0, line_km=5.0))["connection_point_pu"]
    long = solve(engine_plant(q_mvar=15.0, line_km=40.0))["connection_point_pu"]
    assert long > short
