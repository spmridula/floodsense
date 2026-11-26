"""Every number the risk engine uses, with its provenance. Nothing here is calibrated against observed floods.

Risk index  R = S x H        (0..1, relative, UNCALIBRATED -- NOT a probability of flooding)
  S  terrain susceptibility  weighted mean of within-city percentile ranks of five terrain proxies
  H  rainfall severity       max(H_intensity, H_accumulation), each a piecewise-linear map of modelled rainfall
Dry weather => H = 0 => R = 0 for every cell: this index describes rain-triggered risk, not chronic hotspots.
"""
from __future__ import annotations

VERSION = "baseline-0.1.0"

SCORE_SEMANTICS = ("Relative risk index from 0 to 1 combining terrain susceptibility and modelled rainfall severity. "
                   "It is NOT a probability of flooding and has not been calibrated against observed flood events.")

# feature -> (weight, direction, label, kind, unit, low/high wording)
# direction "low": smaller values raise susceptibility; "high": larger values raise it.
SUSCEPTIBILITY = {
    "rel_elev_m_mean":        dict(weight=0.25, direction="low",  label="Height relative to ~1 km surroundings", unit="m", kind="proxy"),
    "elevation_m_mean":       dict(weight=0.15, direction="low",  label="Absolute elevation", unit="m", kind="derived_from_dem"),
    "depression_depth_m_max": dict(weight=0.20, direction="high", label="Depth of closed depression (after filling)", unit="m", kind="proxy"),
    "flow_acc_log10_m2_max":  dict(weight=0.25, direction="high", label="Upslope contributing area", unit="log10(m2)", kind="proxy"),
    "slope_deg_mean":         dict(weight=0.15, direction="low",  label="Surface slope (flatter holds water)", unit="deg", kind="derived_from_dem"),
}
assert abs(sum(v["weight"] for v in SUSCEPTIBILITY.values()) - 1.0) < 1e-9

# Hourly rainfall intensity (mm/h, modelled) -> severity 0..1.
# Anchors: 12 and 20 mm/h = range of Hyderabad storm-drain capacity quoted in news reports (sources DISAGREE; unverified against
# engineering documents); 50 mm/h ~ peak hourly rates reported in past Hyderabad events (52-60 mm/h, news reports); 80 mm/h = saturation.
INTENSITY_ANCHORS = [(0.0, 0.0), (12.0, 0.4), (20.0, 0.6), (50.0, 0.9), (80.0, 1.0)]

# 24 h accumulated rainfall (mm) -> severity 0..1. Anchors are the lower bounds of the India Meteorological Department's
# 24-hour classes (verified against IMD publications): moderate 15.6, heavy 64.5, very heavy 115.6, extremely heavy 204.5 mm.
ACCUMULATION_ANCHORS = [(0.0, 0.0), (15.6, 0.25), (64.5, 0.5), (115.6, 0.75), (204.5, 1.0)]
ACCUMULATION_WINDOW_HOURS = 24

# Category boundaries on R (upper bound exclusive). Chosen so that rain at the quoted drain-capacity limit (H=0.4) gives at most
# "moderate" even on the most susceptible terrain, and extreme rain on susceptible terrain gives "critical".
CATEGORY_BOUNDS = [(0.20, "low"), (0.40, "moderate"), (0.65, "high"), (float("inf"), "critical")]
CATEGORIES = [c for _, c in CATEGORY_BOUNDS]

HORIZON_NOTE = {
    0: "Latest available hourly estimate (modelled, not a gauge reading).",
    "forecast": "EXPERIMENTAL: uses the provider's hourly rainfall FORECAST. Not validated; hourly resolution cannot resolve 30-60 minute changes.",
}

LIMITATIONS = [
    "Terrain features come from a 30 m digital SURFACE model: buildings and trees distort elevation, slope and depressions.",
    "Real drains, culverts, underpasses and pumping are not represented, so the index cannot tell where drainage works or fails.",
    "Rainfall is a ~10 km-scale model estimate interpolated between sample points; local cloudbursts can be missed or smeared.",
    "Weights, anchors and category cut-offs are judgement-based and not calibrated against observed floods (no geocoded flood-event data was found).",
    "Terrain susceptibility is a within-city percentile rank, so categories are RELATIVE: at a given rainfall a roughly fixed share of "
    "cells lands in each upper category regardless of how flood-prone Hyderabad is overall. They are not absolute flood predictions.",
    "A 'low' cell can still flood and a 'critical' cell may not.",
    "Advisory only: never override official instructions from GHMC, HYDRAA, police or emergency services.",
]

REFERENCES = [
    dict(topic="24-hour rainfall classes", source="India Meteorological Department rainfall classification (e.g. IMD regional bulletin PDF; PIB release)",
         how_used="Anchors of the accumulation curve", checked="Read the class limits in IMD/PIB documents"),
    dict(topic="Drain capacity and peak hourly rates", source="Press reports quoting GHMC (Telangana Today, Deccan Chronicle, The News Minute)",
         how_used="Anchors of the intensity curve", checked="NOT verified against an engineering document; reports give 12 and 20 mm/h"),
    dict(topic="Weighted-overlay flood susceptibility", source="Multi-criteria / AHP flood-susceptibility literature, incl. Faizan et al. 2023 (Hyderabad District, "
         "Int. J. Hydrology Science and Technology 16(2))", how_used="Choice of criteria (elevation, slope, flow accumulation, depressions)",
         checked="Abstracts only; the specific weights in those papers were NOT read or copied. Our weights are a judgement."),
    dict(topic="Depression filling", source="Barnes, Lehman & Mulla (2014) Priority-Flood", how_used="Fill sinks", checked="Algorithm reimplemented and unit-tested"),
    dict(topic="Flow routing", source="O'Callaghan & Mark (1984) D8", how_used="Flow accumulation", checked="Algorithm reimplemented and unit-tested"),
]

# A cell with at least this fraction covered by mapped water (lake, reservoir, riverbank polygon) is a water body: shown as water,
# excluded from percentile ranking, and never given a risk score (a lake surface is flat and low, which would otherwise look "susceptible").
WATER_THRESHOLD = 0.5
