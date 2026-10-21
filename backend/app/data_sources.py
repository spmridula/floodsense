"""Seed registry of data sources from the Phase 0 investigation.

verification stays NOT_VERIFIED until Phase 2 code actually downloads/queries the source.
"""
from app.schemas import DataLabel, VerificationStatus as V

SOURCES: list[dict] = [
    dict(key="open_meteo", name="Open-Meteo Forecast API", url="https://open-meteo.com/en/terms",
         coverage="Global (model grid, not point gauges)", license="Free for non-commercial use; attribution required (see terms page)",
         role="Current and forecast precipitation", limitations="Modelled estimates; <10,000 calls/day, 5,000/h, 600/min free tier",
         label=DataLabel.LIVE_FORECAST, verification=V.NOT_VERIFIED),
    dict(key="tgdps_daily", name="TGDPS daily weather data 2018-2025 (via AIKosh)", url="https://aikosh.indiaai.gov.in/home/datasets/details/telangana_weather_data_2023_2025.html",
         coverage="~589 stations, Telangana", license="Open Government License, India",
         role="Historical rainfall context", limitations="Daily totals only; unsuitable for 30-60 min prediction",
         label=DataLabel.HISTORICAL, verification=V.NOT_VERIFIED),
    dict(key="copernicus_dem", name="Copernicus DEM GLO-30", url="https://registry.opendata.aws/copernicus-dem/",
         coverage="Global, ~30 m", license="Free for general public under Copernicus DEM licence; attribute",
         role="Elevation, slope, flow-accumulation proxy", limitations="Surface model (includes buildings/trees); India tile access not yet checked",
         label=DataLabel.HISTORICAL, verification=V.NOT_VERIFIED),
    dict(key="osm_roads", name="OpenStreetMap road network (OSMnx)", url="https://www.openstreetmap.org/copyright",
         coverage="Global", license="ODbL",
         role="Road graph and routing", limitations="Community-maintained; completeness varies; whole-city graph is large",
         label=DataLabel.HISTORICAL, verification=V.NOT_VERIFIED),
    dict(key="ghmc_hotspots", name="GHMC/HYDRAA waterlogging points (news-reported counts)", url="https://www.siasat.com/officials-to-tackle-523-waterlogging-points-within-ghmc-ahead-of-monsoon-3479402/",
         coverage="Greater Hyderabad", license="Unknown",
         role="Would be a static hotspot overlay / sanity check", limitations="No geocoded, timestamped open dataset found; cannot be used as training labels",
         label=DataLabel.UNAVAILABLE, verification=V.UNAVAILABLE),
    dict(key="drainage", name="Stormwater drainage network", url="",
         coverage="n/a", license="n/a", role="Would improve drainage features",
         limitations="No open geodata found for Hyderabad; features will be proxies",
         label=DataLabel.UNAVAILABLE, verification=V.UNAVAILABLE),
]
