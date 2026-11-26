import numpy as np
import pandas as pd
import pytest

for m in ("shapely", "h3", "geopandas", "pyogrio", "rasterio", "scipy"):
    pytest.importorskip(m)
from shapely.geometry import box

from app.geo.cells import cells_for_geometry
from app.risk.engine import make_table

FEATS = ["rel_elev_m_mean", "elevation_m_mean", "depression_depth_m_max", "flow_acc_log10_m2_max", "slope_deg_mean"]


def synthetic_df(seed: int = 0, geom=None, nan_cells: int = 0) -> pd.DataFrame:
    """Real H3 ids over a small Hyderabad box with random-but-correlated terrain features."""
    ids = cells_for_geometry(geom or box(78.40, 17.40, 78.46, 17.46), 9)
    import h3
    rng = np.random.default_rng(seed)
    n = len(ids)
    latent = rng.normal(size=n)                               # a shared "low-lying" factor so features correlate
    df = pd.DataFrame({
        "cell_id": ids,
        "lat": [h3.cell_to_latlng(c)[0] for c in ids], "lon": [h3.cell_to_latlng(c)[1] for c in ids],
        "rel_elev_m_mean": -2 * latent + rng.normal(0, 1, n), "elevation_m_mean": 540 - 15 * latent + rng.normal(0, 5, n),
        "depression_depth_m_max": np.abs(latent + rng.normal(0, 1, n)), "flow_acc_log10_m2_max": 4 + latent + rng.normal(0, .5, n),
        "slope_deg_mean": np.abs(3 - latent + rng.normal(0, 1, n)), "low_coverage": False, "n_samples": 100})
    df.loc[df.index[:nan_cells], FEATS] = np.nan
    df.loc[df.index[:nan_cells], "low_coverage"] = True
    return df


def synthetic_table(seed: int = 0, nan_cells: int = 0):
    return make_table(synthetic_df(seed, nan_cells=nan_cells))
