import numpy as np

from pipeline.hydrology import hms


def test_scs_excess_matches_closed_form():
    # 100 mm on CN 80: S = 63.5 mm, Ia = 12.7, Q = (100 - 12.7)^2 / (100 + 50.8) = 50.54 mm
    p = np.full(100, 1.0)
    assert np.isclose(hms.scs_excess(p, 80.0).sum(), (100 - 12.7) ** 2 / (100 + 0.8 * 63.5), rtol=1e-6)
    # below the initial abstraction nothing runs off
    assert hms.scs_excess(np.full(10, 1.0), 80.0).sum() == 0.0


def test_clark_uh_carries_one_mm_over_the_area():
    area = 50.0
    uh = hms.clark_uh(area, tc_h=2.0, r_h=2.0)
    volume_m3 = uh.sum() * hms.DT_S
    assert np.isclose(volume_m3, area * 1e6 * 1e-3, rtol=0.01)


def test_muskingum_cunge_conserves_volume_and_attenuates():
    t = np.arange(600)
    inflow = 200.0 * np.exp(-((t - 100) / 25.0) ** 2) + 0.5
    reach = {"length_m": 15000.0, "slope": 0.01, "width_m": 40.0, "n": 0.045}
    out = hms.route(inflow, reach)
    assert np.isclose(out.sum(), inflow.sum(), rtol=0.02)
    assert out.max() < inflow.max()
    assert np.argmax(out) > np.argmax(inflow)


def test_network_outlet_volume_equals_sum_of_subbasin_excess():
    basin = hms.load_basin()
    rain = np.zeros(hms.SIM_HOURS * 3600 // hms.DT_S * 2)     # long enough for the recession
    rain[100:124] = 4.0                                        # 96 mm in 2 h
    res = hms.run_network(basin, lambda sb: rain)
    excess_m3 = sum(res[sb.id]["excess_mm"] * 1e-3 * sb.area_km2 * 1e6 for sb in basin)
    outlet_m3 = res[1]["total"].sum() * hms.DT_S
    assert np.isclose(outlet_m3, excess_m3, rtol=0.02)


def test_amc_conversion_brackets_amc2():
    for cn in (60.0, 75.0, 86.0):
        assert hms.cn_amc(cn, 1) < cn < hms.cn_amc(cn, 3)
