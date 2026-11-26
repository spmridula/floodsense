# FloodSense baseline risk engine — methodology (model `baseline-0.1.0`)

**One-sentence summary:** a transparent, rule-based index that multiplies how *susceptible* a 0.1 km² cell's terrain is by how *severe*
the modelled rainfall is. It is **not** a trained model, **not** a probability, and **not** validated against observed floods.

## Formula
```
R = S x H                    R in [0,1]  (risk index, relative, uncalibrated)
S = sum_i w_i * rank_i       weighted mean of within-Hyderabad percentile ranks of five terrain proxies
H = max(H_intensity, H_accumulation)     piecewise-linear maps of modelled rainfall
category: low R<0.20 | moderate <0.40 | high <0.65 | critical >=0.65
```
No rain => H = 0 => R = 0 everywhere. The index describes *rain-triggered* risk, not chronic hotspots.
If any terrain feature or the target-hour rainfall is missing, the cell gets **no score** (never a default or partial value).

## Terrain susceptibility S (weights are a judgement, see Sensitivity)
| Feature | Weight | Higher susceptibility when | Nature |
|---|---|---|---|
| Height relative to ~1 km surroundings | 0.25 | lower | proxy (surface model) |
| Upslope contributing area (D8 flow accumulation) | 0.25 | larger | proxy |
| Depth of closed depression after sink-filling | 0.20 | deeper | proxy |
| Absolute elevation | 0.15 | lower | derived from DEM |
| Surface slope | 0.15 | flatter | derived from DEM |

Because ranks are percentiles *within Hyderabad*, categories are **relative**: at a given rainfall a roughly fixed share of cells lands
in each upper category. The index says "which places are more exposed than others", not "how likely is flooding".

## Rainfall severity H
- **Intensity** (mm/h, modelled hour) anchors: 0→0, 12→0.4, 20→0.6, 50→0.9, 80→1.0. The 12 and 20 mm/h anchors are the drain-capacity range quoted
  in news reports citing GHMC (the reports disagree and I did not find an engineering document); 50 mm/h reflects peak hourly rates reported for past
  Hyderabad events (52–60 mm/h, press reports).
- **24-hour accumulation** (mm) anchors: 0→0, 15.6→0.25, 64.5→0.5, 115.6→0.75, 204.5→1.0 = lower bounds of IMD's moderate / heavy / very heavy /
  extremely heavy classes (read in IMD and PIB documents).
- Point rainfall (Open-Meteo, ~10 km model, 20 sample points) is interpolated to cells by inverse-distance weighting over the 4 nearest points.

## Output (per cell)
cell id; category; risk index with its definition; prediction time; observation time (rainfall hour used); target time; data freshness;
horizon (0 = current estimate, 1–3 h = **experimental** provider forecast); model version; `uncertainty: unavailable` with the reason
(an uncalibrated index has no meaningful confidence interval); ordered contributing factors with their kind (proxy / derived) and a plain-language
summary assembled from the computed numbers (no language model is involved).

## Verification status of the sources
| Item | Status |
|---|---|
| IMD 24-h classes | Read in IMD/PIB documents |
| GHMC drain capacity / peak hourly rates | Press reports only; sources disagree |
| AHP/weighted-overlay flood literature (incl. Faizan et al. 2023, Hyderabad) | Abstracts only; their weights were **not** read or copied |
| Priority-Flood (Barnes et al. 2014), D8 (O'Callaghan & Mark 1984) | Algorithms reimplemented; unit-tested on analytic cases |

## What has and has not been evaluated
Done (automated): arithmetic of every component; monotonicity (more rain never lowers any score); interpolation correctness; hydrology
mass conservation; behaviour with missing/stale/short-history data; API contracts.
Available on your machine: `risk-sensitivity` (how much the ranking changes if weights change) and `risk-backtest` (presence-only agreement with a
list of known waterlogging points, if you obtain one).
**Not possible with current data:** any precision/recall/F1 for flood prediction. No geocoded, timestamped flood-event data was found, so no
such metric is reported. Obtaining GHMC/HYDRAA waterlogging-point locations (e.g. via RTI or the department) is the single most valuable next step.

## Known limitations
See `LIMITATIONS` in `backend/app/risk/methodology.py` (also served at `/api/risk/methodology`): surface-model artefacts, no drainage
network, coarse rainfall, judgement-based weights, relative categories, advisory only.
