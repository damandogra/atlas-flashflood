import numpy as np

from pipeline.data import rainfall


def test_gev_lmom_recovers_known_parameters():
    # Hosking parameterisation: xi=50, alpha=15, k=-0.1 (heavy upper tail)
    rng = np.random.default_rng(0)
    xi, alpha, k = 50.0, 15.0, -0.1
    u = rng.uniform(size=20000)
    sample = xi + alpha / k * (1 - (-np.log(u)) ** k)
    fit = rainfall.gev_lmom(sample)
    assert abs(fit[0] - xi) < 0.5
    assert abs(fit[1] - alpha) < 0.5
    assert abs(fit[2] - k) < 0.02


def test_gev_quantile_is_increasing_in_return_period():
    q = rainfall.gev_quantile((50.0, 15.0, -0.1), rainfall.RETURN_PERIODS)
    assert np.all(np.diff(q) > 0)


def test_alternating_block_conserves_depth_and_peaks_in_centre():
    dd = rainfall.depth_duration([30, 40, 45, 55, 70, 90, 110])   # one value per DURATIONS_H
    h = rainfall.alternating_block(dd)
    assert np.isclose(h.sum(), dd(24 * 60))
    assert abs(int(np.argmax(h)) - len(h) // 2) <= 1
    assert np.isclose(h.max(), dd(rainfall.STORM_DT_MIN))
