"""Forecast core: AMC equivalence, library matching, and the fixture the TypeScript port is tested on."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import config
from pipeline.forecast import core

META = config.WEB_DATA / "meta.json"
FIXTURE = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "forecast.fixture.json"


def setup_module():
    core._CTX.clear()
    core.use_meta(META)


def test_amc_equivalent_depth_orders_dry_normal_wet():
    p = 60.0
    dry, normal, wet = (core.amc_equivalent_depth(p, a) for a in (1, 2, 3))
    assert dry < normal == p < wet
    # equivalence means equal runoff under AMC II
    assert np.isclose(core.basin_runoff(dry, 2), core.basin_runoff(p, 1), rtol=1e-6)


def test_match_picks_largest_library_depth_not_above():
    lib = core.lib()
    names, depths = list(lib), list(lib.values())
    assert core.match(depths[0] - 1) == (None, names[0])
    assert core.match(depths[3] + 0.01)[0] == names[3]


def test_write_fixture_for_typescript_port():
    rng = np.random.default_rng(7)
    cases = []
    t = pd.date_range("2026-01-01", periods=96, freq="h", tz="UTC")
    for scale, ante in ((0.5, 3.0), (2.5, 20.0), (4.0, 35.0), (6.0, 10.0)):
        rain = np.round(np.clip(rng.gamma(0.4, scale, len(t)), 0, None), 3)
        a = core.assess(pd.Series(rain, index=t), ante)
        cases.append({"time": [x.isoformat().replace("+00:00", "Z") for x in t], "rain": rain.tolist(),
                      "antecedent": ante, "expected": a})
    FIXTURE.write_text(json.dumps(cases), encoding="utf8")
    assert len(cases) == 4
