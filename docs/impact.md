# Impacts, actions and mitigation (Phase 4)

## Reproduce

```bash
python -m pipeline.data.exposure_data     # buildings (Google/VIDA), OSM roads + facilities, population totals
python -m pipeline.impact.prep            # exposure layers
python -m pipeline.impact.engine          # per-scenario impacts -> data/runs/impact/
python -m pipeline.impact.actions         # early-action lists from pipeline/impact/playbook.yaml
python -m pipeline.impact.mitigation      # what-if measures
```

## Exposure

| Layer | Source | Notes |
|---|---|---|
| Buildings | **Google Open Buildings** footprints via the VIDA combined dataset (Earth Engine community catalogue), confidence ≥ 0.65 | 16,653 footprints (13,588 in the catchment); OSM maps 495. Google v3 is not served for Morocco in Earth Engine |
| Residents | Catchment total **15,571** = mean of GHS-POP 2020 (15,979) and WorldPop 2020 (15,163), spread over residential footprints by area | Neither 100 m product places people in these hamlets: GHS-POP lumps them into ~240 cells, unconstrained WorldPop spreads them over empty slopes |
| Building type | OSM schools, mosques, health, public and tourism facilities within 30 m | Non-residential buildings carry no residents; they are flagged by type |
| Roads | 1,916 OSM ways (tracks and paths included), split at junctions into 3,356 segments (1,040 km vehicle, 612 km foot) | 114 segments at **fords**, 77 bridges |
| Villages | 51 named OSM places | Display names in Latin script; Tifinagh/Arabic kept |

## Impact rules

- **Building hazard:** HR = d (v + 0.5) + DF, after DEFRA/EA FD2320 (2006). The urban debris factor (DF) is 0 at depths up to 0.25 m and 1 above.
  - Classes: low < 0.75, moderate < 1.25, significant < 2.0, extreme ≥ 2.0.
- **Structural risk of earthen houses** (indicative):
  - damage likely if d > 1 m or d·v > 1 m²/s;
  - collapse possible if d > 2 m or d·v > 3 m²/s;
  - after Clausen & Clark (1990), made stricter for adobe and pisé.
- **Roads:** Australian Rainfall & Runoff (2019) vehicle stability limits.
  - Cars are unsafe above 0.3 m or 0.3 m²/s.
  - 4WD and emergency vehicles are unsafe above 0.5 m or 0.6 m²/s.
  - These are evaluated every 30 minutes from the 2D depth snapshots.
  - Bridge decks are assumed to stay above the water unless it exceeds 2.5 m under them.
- **Isolation:** every 30 minutes, the road graph without its 4WD-unsafe segments shows which villages have no route to the **RN9**, the regional artery. That gives when each village is cut off and for how long. Five places have no mapped road link to the RN9 even when dry; they are excluded as a road-data gap.
- **Shelters:** schools, mosques and public buildings that stay dry in the largest library storm. Evacuation routes are computed in the browser and avoid segments unsafe at the chosen time.

## Results (central rainfall)

| Storm | Buildings reached | Extreme hazard | Residents | Collapse possible | Road closed (km) | Fords impassable | Villages cut off |
|---|---|---|---|---|---|---|---|
| P20 | 40 | 0 | 37 | 0 | 3.9 | 1 | 0 |
| T2 | 66 | 21 | 52 | 0 | 34.8 | 9 | 2 |
| T5 | 108 | 43 | 102 | 4 | 43.8 | 12 | 12 |
| T10 | 135 | 48 | 135 | 20 | 62.2 | 16 | 19 |
| T25 | 167 | 52 | 178 | 37 | 71.4 | 17 | 19 |
| T100 | 230 | 64 | 249 | 46 | 96.3 | 18 | 19 |
| T500 | 323 | 80 | 358 | 52 | 110.6 | 19 | 19 |
| P160 | 445 | 131 | 477 | 68 | 162.0 | 23 | 19 |

**The dominant impact is isolation, not flooded houses.**
- From a 5–10-year flood upward, 19 villages lose 4WD access to the RN9: the tracks and the RP1506 run in or across the wadi.
- Most ksour sit on terraces above the flood. The houses that do flood are the ones built in or next to the wadi bed, many of them in extreme hazard even in a 2-year flood.

## Early-action playbook

`pipeline/impact/playbook.yaml` holds 10 actions in the style of IFRC/Red Cross Early Action Protocols, each with an owner, a trigger, a lead time and a priority.
- **Owners:** Province / caïdat, communes and moqaddems, Protection Civile, Gendarmerie Royale, the provincial roads directorate (DPETL), the education and health delegations, and tourism operators.
- **Generation:** the action list is generated for every scenario, with deadlines tied to the modelled impact times (first water at each village, ford and road closures, start of isolation). For example, the T100 storm gives 128 actions (36 critical), the first due 5.5 h after storm start.
- **Clock times:** in forecast and replay mode, the app turns these into clock times.
- **Editing:** edit the YAML, then rerun `pipeline.impact.actions` and `pipeline.export.web`.

## Mitigation, evaluated with the models

| Measure | 10-year flood | 100-year flood |
|---|---|---|
| **Flood-proof the 10 most critical road links** (raised crossings / protected embankments, +1 m) | isolation 402 → **144** village-hours; **10 of 19** villages keep access | 435 → 282 village-hours; 6 of 19 keep access |
| Headwater rangeland restoration / reforestation (CN −6 on the 4 headwater sub-basins, 116 km²) | outlet peak −7.3%, 10 fewer buildings reached | peak −4.9%, 15 fewer |
| Check-dam series (25 × 1,500 m³ per headwater sub-basin) | peak −0.0% | −0.0% |

**How the critical links are found:** each road segment on an isolated village's normal route to the RN9 is charged that village's hours of isolation.
- The top links are all on the **RP1506**: the Télouet section (−7.25, 31.27), and the section between Tamdaght and Aït Ben Haddou (−7.14, 31.07–31.11).
- Single fords rank low. Villages are cut off by several flooded sections at once, so fixing one ford rarely reconnects anyone.

**Check dams** are worth building against erosion and sediment, not to lower flood peaks: their storage is tiny next to the multi-million-m³ flood volumes.

**Costs:** no costs are assumed. The Plan panel takes local unit costs and reports cost per village-hour or per building avoided.

## Limitations

- Residents per building are estimates. Tourists in the 525 buildings near hotels and guest houses, and pupils in schools, are flagged, not counted.
- The thresholds are international guidance (DEFRA, ARR, Clausen & Clark), not calibrated on Moroccan adobe buildings.
- OSM road completeness limits the isolation analysis. Five villages have no mapped link to the RN9.
