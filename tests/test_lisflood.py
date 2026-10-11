import numpy as np

from pipeline.hydraulics import lisflood2d as lf

DX = 30.0


def _channel(slope=0.01, n_manning=0.035, width_cells=6, length_cells=120):
    active = np.ones((length_cells, width_cells), dtype=bool)
    z = (length_cells - np.arange(length_cells))[:, None] * DX * slope * np.ones((1, width_cells))
    n = np.full(active.shape, n_manning)
    dom = lf.build(active, z, n)
    top = [dom["idx"][0, c] for c in range(width_cells)]
    bottom = [dom["idx"][length_cells - 1, c] for c in range(width_cells)]
    return dom, top, bottom


def test_tilted_plane_reaches_manning_normal_depth_and_conserves_mass():
    slope, n_manning, w_cells, Q = 0.01, 0.035, 6, 60.0
    dom, top, bottom = _channel(slope, n_manning, w_cells)
    sources = ([c for c in top], [0] * len(top), [1.0 / len(top)] * len(top))
    q_local = np.full((1, 400), Q)                               # constant 60 m3/s for 400 x 60 s
    out = lf.simulate(dom, sources, q_local, 60.0, 0.0, 6 * 3600.0, (bottom, [slope] * len(bottom)))
    q_unit = Q / (w_cells * DX)
    h_normal = (q_unit * n_manning / np.sqrt(slope)) ** 0.6
    mid = dom["idx"][60, :]
    assert np.allclose(out["h_end"][mid], h_normal, rtol=0.05)
    assert abs(out["mass_error"]) < 0.01
    # steady state: outflow equals inflow
    assert np.isclose(out["outflow"][-1], Q, rtol=0.03)


def test_dry_domain_stays_dry():
    dom, top, bottom = _channel()
    out = lf.simulate(dom, ([top[0]], [0], [1.0]), np.zeros((1, 10)), 60.0, 0.0, 600.0, (bottom, [0.01] * len(bottom)))
    assert out["hmax"].max() == 0.0
