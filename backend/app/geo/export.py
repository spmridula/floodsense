"""GeoJSON of the cell grid (static geometry + static features) for the map. Dynamic risk is joined client-side."""
from __future__ import annotations

import json
import math

from app.risk.engine import CellTable

PROPS = ["elevation_m_mean", "slope_deg_mean", "rel_elev_m_mean", "depression_depth_m_max", "flow_acc_log10_m2_max"]


def _clean(x, nd=3):
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(xf) else round(xf, nd)


def cells_geojson_bytes(table: CellTable) -> bytes:
    import h3

    feats = []
    for cid in table.df.index:
        row = table.df.loc[cid]
        ring = [[round(lon, 6), round(lat, 6)] for lat, lon in h3.cell_to_boundary(cid)]
        ring.append(ring[0])
        props = {"cell_id": cid, "susceptibility": _clean(table.susceptibility[cid], 4), "is_water": bool(table.is_water[cid]),
                 "water_fraction": _clean(row["water_fraction"], 3) if "water_fraction" in table.df.columns else None,
                 "low_coverage": bool(row["low_coverage"])}
        props.update({k: _clean(row[k], 2) for k in PROPS})
        feats.append({"type": "Feature", "id": cid, "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return json.dumps({"type": "FeatureCollection", "water_masked": table.water_masked, "features": feats}, separators=(",", ":")).encode()
