import { Map as MapLibreMap, NavigationControl, Popup, ScaleControl, type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { FC, LayerId, Stops, boundsOf, buildLayers, fillColorExpression, selectedFilter, tooltipText } from "./mapLogic";

export type MapHotspot = { id: string; lat: number; lon: number; name: string };
type Props = {
  data: FC; layer: LayerId; stops: Stops | null; selectedId: string | null; onSelect: (id: string | null) => void;
  markMode: boolean; onMark: (lat: number, lon: number) => void; hotspots: MapHotspot[];
};

// Basemap: OpenStreetMap raster tiles, dimmed to suit the dark UI. Fine for local use; review OSM's tile usage policy before deploying.
const STYLE = {
  version: 8,
  sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors" } },
  layers: [{ id: "osm", type: "raster", source: "osm", paint: { "raster-brightness-max": 0.6, "raster-saturation": -0.6, "raster-contrast": 0.1 } }],
} as unknown as StyleSpecification;

const points = (h: MapHotspot[]) => ({
  type: "FeatureCollection", features: h.map((p) => ({ type: "Feature", properties: { id: p.id, name: p.name }, geometry: { type: "Point", coordinates: [p.lon, p.lat] } })),
});

export default function MapView(props: Props) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const [ready, setReady] = useState(false);
  const [fatal, setFatal] = useState<string | null>(null);

  useEffect(() => {
    if (!box.current) return;
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({ container: box.current, style: STYLE, center: [78.43, 17.42], zoom: 10.5, attributionControl: { compact: true } });
    } catch {
      setFatal("The map could not start. It needs WebGL, which this browser or device did not provide. Try another browser or enable hardware acceleration.");
      return;
    }
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    map.on("error", (e) => console.warn("map warning:", e?.error?.message));   // e.g. a tile failed; never crash the page
    map.on("load", () => {
      const p = latest.current;
      map.addSource("cells", { type: "geojson", data: p.data as never, promoteId: "cell_id" });
      const layers = buildLayers(p.layer, p.stops, p.selectedId);
      for (const l of layers.slice(0, 3)) map.addLayer(l as never);
      map.addSource("hotspots", { type: "geojson", data: points(p.hotspots) as never });
      map.addLayer(layers[3] as never);
      const b = boundsOf(p.data);
      if (b) map.fitBounds(b, { padding: 30, duration: 0 });
      setReady(true);
    });
    map.on("click", (e) => {
      const p = latest.current;
      if (p.markMode) { p.onMark(e.lngLat.lat, e.lngLat.lng); return; }
      const f = map.queryRenderedFeatures(e.point, { layers: ["cells-fill"] })[0];
      p.onSelect(f ? String(f.properties?.cell_id) : null);
    });
    map.on("mousemove", "cells-fill", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      map.getCanvas().style.cursor = latest.current.markMode ? "crosshair" : "pointer";
      popup.setLngLat(e.lngLat).setText(tooltipText(f.properties as never, latest.current.layer)).addTo(map);
    });
    map.on("mouseleave", "cells-fill", () => { popup.remove(); map.getCanvas().style.cursor = latest.current.markMode ? "crosshair" : ""; });
    return () => { popup.remove(); map.remove(); mapRef.current = null; setReady(false); };
  }, []);

  useEffect(() => { if (ready) (mapRef.current?.getSource("cells") as GeoJSONSource | undefined)?.setData(props.data as never); }, [ready, props.data]);
  useEffect(() => { if (ready) mapRef.current?.setPaintProperty("cells-fill", "fill-color", fillColorExpression(props.layer, props.stops) as never); }, [ready, props.layer, props.stops]);
  useEffect(() => { if (ready) mapRef.current?.setFilter("cells-selected", selectedFilter(props.selectedId) as never); }, [ready, props.selectedId]);
  useEffect(() => { if (ready) (mapRef.current?.getSource("hotspots") as GeoJSONSource | undefined)?.setData(points(props.hotspots) as never); }, [ready, props.hotspots]);
  useEffect(() => { if (mapRef.current) mapRef.current.getCanvas().style.cursor = props.markMode ? "crosshair" : ""; }, [props.markMode]);

  if (fatal) return <div className="map-fallback" role="alert">{fatal}</div>;
  return <div ref={box} className="mapcanvas" role="region" aria-label="Flood risk map" />;
}
