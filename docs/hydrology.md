# Hydrology (Phase 2): HEC-HMS-equivalent event model

## Reproduce

```bash
python -m pipeline.hydrology.scenarios     # design library + checks  -> data/runs/hydrology/
python -m pipeline.hydrology.figures       # docs/figures/phase2_*.png
python -m pipeline.hydrology.hec_export    # hec/hms/Ounila/ (HEC-HMS project for cross-check)
python -m pytest tests                     # SCS, Clark, Muskingum-Cunge, network mass balance
```

## Model

The model is the same method stack as an HEC-HMS basin model (`pipeline/hydrology/hms.py`), run on 21 sub-basins and 20 reaches at a 5-minute step for 48 h.

| Component | Method | Parameters |
|---|---|---|
| Loss | SCS Curve Number, Ia = 0.2 S; AMC I/III conversion (Chow et al. 1988) for antecedent conditions | CN per sub-basin from Phase 1 (77–88) |
| Transform | Clark unit hydrograph with the HEC-HMS synthetic time-area curve | Tc = mean of Giandotti and Témez. R = 1.0 × Tc |
| Routing | Variable-parameter Muskingum-Cunge (Ponce & Yevjevich 1978), wide rectangular channel | Length and slope from the DEM; n = 0.045; width = 3·√A m |
| Baseflow | None | Ephemeral wadi: Agouillal's 365-day flow is 0.00 m³/s |
| Meteorology | 24 h alternating-block design storm (Phase 1) | Depth reduced by area to each point's drainage area, as HMS frequency storms are run per analysis point |

**Time of concentration.**
- Kirpich is computed and reported but not used. It was fitted on 1–45 ha Tennessee farm basins and gives about half the Tc of Giandotti and Témez here.
- Giandotti and Témez are both widely used for Moroccan and Mediterranean mountain basins.

## Grounding: three independent observational checks

### 1. Our outlet is a gauged catchment

The DRPE gauge **Agouillal** on the oued Ouarzazate drains **740 km²**. Our DEM-delineated catchment above Aït Ben Haddou is 731 km², within 1.2%. Saidi et al. (2006) map the same basin ("Marghène at Aguillal", 750 km², 1220–3610 m).

Published statistics for 1976/77–1997/98 (Agoussine et al. 2004, from DRPE data):
- Mean flow **1.3 m³/s**, i.e. **55 mm/yr** of runoff.
- The flow exceeded 10 days a year is 7 m³/s.
- The river is dry at least one day every year.
- About 2 floods per year.

### 2. Water balance: this fixes the rainfall level

Every ERA5-Land liquid storm from 1976–98 was run through the CN loss model (2,676 events, antecedent moisture from the 5-day rain before each). The monthly regime at Agouillal suggests storms produce about 35–65% of total runoff; the rest is snowmelt (a March–April bump) and spring baseflow. That makes **observed storm runoff about 19–36 mm/yr**.

| Rainfall level | Correction | Rain (mm/yr) | Storm runoff, model (mm/yr) | Verdict |
|---|---|---|---|---|
| Low | ×0.87 | 297 | 4.6 | ❌ far too little |
| **Central** | **×1.43** | **487** | **28.1** | ✅ inside the observed band |
| High | ×2.14 | 728 | 83.0 | ❌ more than the *total* observed runoff |

So the gauge bias × areal reduction decomposition from Phase 1 is supported by measured flows at the outlet, and **the central level is used from here on.**

### 3. Regional flood peaks: this fixes the timing

Saidi et al. (2010) give flood data for the **Ourika at Aghbalou** (503 km², north slope of the High Atlas, ABH Tensift gauge):
- Q2 ≈ 103 m³/s and Q10 ≈ 485 m³/s.
- Recorded floods of 650 (1987), 762 (1999) and **1030 m³/s (17 Aug 1995)**.

The Ourika is wetter (584 vs 133 mm/yr at the gauges), steeper (35% vs 19% mean slope) and mostly crystalline. The Ounila/Marghène is "much more permeable" (Jurassic carbonates, conglomerates), and its floods are attenuated by long concentration times (Saidi et al. 2006). So **Ounila peaks should be lower than the Ourika's for the same frequency and area.**

**Model outlet peaks (central):**

| Return period | Peak (m³/s) | Francou-Rodier K |
|---|---|---|
| T2 | 120 | 2.37 |
| T10 | 425 | **3.44** |
| T100 | 928 | **4.10** |
| T500 | 1320 | 4.39 |

- **T10:** below the Ourika transposed to 731 km² (K 3.74, i.e. 609 m³/s) and above the Rheraya (K 3.0), another High Atlas basin.
- **T100:** K = 4.10, matching the Rheraya's fitted T100 (K ≈ 4.1). Moroccan *record* floods sit at K 4–5.
- **T500:** close to the Ourika's 1995 record (K 4.36). That's plausible, since a record flood is a rare event.

### Sensitivity of the outlet peak (central rainfall)

| Variant | Q2 | Q10 | Q100 |
|---|---|---|---|
| **Adopted:** Tc mean(Giandotti, Témez), R = 1.0 Tc | 120 | 425 | 928 |
| R = 0.5 Tc | 153 | 561 | 1231 |
| R = 1.5 Tc | 99 | 344 | 749 |
| Tc including Kirpich | 133 | 484 | 1064 |
| Tc Giandotti only | 126 | 452 | 990 |
| Tc Témez only | 114 | 401 | 876 |
| Channel width ×2 / ×0.5 | 113 / 124 | 418 / 428 | 922 / 930 |

- **The Clark storage coefficient R is the dominant peak parameter.** R = 1.0 Tc is the conservative (higher-peak) end of the range Russell et al. (1979) give for natural basins (R/Tc 1.5–2.8).
- Channel width hardly matters (±1%).
- Volume, and so the water balance, doesn't depend on these timing parameters. That's why checks 2 and 3 are independent.

## Design floods at the control points

Central rainfall; storms reduced by area to each point's drainage. The peak time is counted from storm start; rain peaks at ~12 h.

| Control point | Drainage (km²) | Own Tc (h) | T2 | T10 | T100 | T500 | T100 peak at (h) |
|---|---|---|---|---|---|---|---|
| Ouzlim | 7 | 1.2 | 1 | 7 | 18 | 27 | 13.3 |
| Akji | 10 | 1.0 | 2 | 9 | 23 | 37 | 13.3 |
| Timjoujte | 15 | 1.8 | 2 | 12 | 30 | 46 | 14.0 |
| Télouet | 16 | 1.5 | 3 | 13 | 33 | 51 | 14.1 |
| Taboughamt | 22 | 2.5 | 4 | 17 | 39 | 60 | 14.7 |
| *Confluence 71 km²* | 71 | 3.0 | 13 | 52 | 118 | 178 | 15.1 |
| Tighza | 99 | 2.5 | 17 | 73 | 166 | 251 | 15.2 |
| Anmiter | 165 | 3.7 | 27 | 111 | 252 | 377 | 15.6 |
| *Confluence 183 km²* | 183 | 4.6 | 20 | 90 | 210 | 317 | 16.3 |
| Tajeguite | 215 | 4.0 | 37 | 145 | 323 | 476 | 16.0 |
| Assaka | 227 | 2.3 | 40 | 154 | 343 | 505 | 16.0 |
| Tizgui N'Barda | 254 | 2.5 | 46 | 176 | 389 | 569 | 16.2 |
| Ait Fars | 277 | 2.7 | 51 | 193 | 425 | 621 | 16.3 |
| Douar Tigert | 278 | 1.0 | 51 | 193 | 426 | 622 | 16.3 |
| *Confluence 288 km²* | 288 | 4.8 | 41 | 156 | 346 | 507 | 16.9 |
| Taifest | 304 | 3.9 | 56 | 210 | 463 | 673 | 16.4 |
| Ankhsa | 311 | 2.9 | 46 | 173 | 380 | 554 | 17.0 |
| *Confluence 372 km²* | 372 | 5.7 | 56 | 203 | 444 | 641 | 17.2 |
| Tazlaft | 393 | 3.7 | 60 | 216 | 471 | 679 | 17.6 |
| Tamdaght (Tamdakhte) | 707 | 2.7 | 116 | 411 | 897 | 1278 | 17.0 |
| Aït Ben Haddou | 731 | 4.2 | 120 | 425 | 928 | 1320 | 17.3 |

**Lead time is the key number for the DSS.** From the burst of a T100 storm, the head villages (Télouet, Akji) peak about 1.5–2 h later; Tighza and Anmiter about 3–3.5 h later; Aït Ben Haddou about 5 h later.

## HEC-HMS cross-check

- `hec/hms/Ounila/` holds the full project, plus parameter CSVs and `expected_results.csv`. Instructions are in `hec/hms/README.md`.
- **Status: waiting for an HEC-HMS run.** HEC-HMS isn't installed on the development machine.

## Still open

- **No observed flood peaks for Agouillal.** DRPE / ABH Drâa-Oued Noun hold the series. With even the annual maxima, the R/Tc choice could be calibrated directly, not just bounded.
- **Transmission losses** in the gravel wadi beds aren't modelled. They would lower peaks further downstream; leaving them out is conservative for a warning system.
- **The JS port of this engine** (for live forecasts in the browser) and **the November 2014 replay** move to Phase 5, where the web app and the forecast pipeline exist.

## Sources

- Saidi M.E.M., Agoussine M., Daoudi L. (2006). Effet de la morphologie et de l'exposition sur les ressources en eau superficielle de part et d'autre du Haut Atlas : exemple des bassins versants de l'Ourika et du Marghène. *Bull. Inst. Sci. Rabat, Sci. Terre* 28, 41–49.
- Agoussine M., Saidi M.E.M., Igmoullan B. (2004). Reconnaissance des ressources en eau du bassin d'Ouarzazate. *Bull. Inst. Sci. Rabat, Sci. Terre* 26, 81–92.
- Saidi M.E.M. et al. (2010). Les crues de l'oued Ourika (Haut Atlas, Maroc) : événements extrêmes en contexte montagnard semi-aride. *Comunicações Geológicas* 97, 113–128.
- Russell S.O., Kenning B.F.I., Sunnell G.J. (1979). Estimating design flows for urban drainage. *J. Hydraulics Div. ASCE* 105(1).
- Ponce V.M., Yevjevich V. (1978). Muskingum-Cunge method with variable parameters. *J. Hydraulics Div. ASCE* 104(12).
- Chow V.T., Maidment D.R., Mays L.W. (1988). *Applied Hydrology*. McGraw-Hill.
