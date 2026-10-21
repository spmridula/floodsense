import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Overview from "./pages/Overview";
import Sources from "./pages/Sources";

const PLANNED = [
  ["Risk map", "Phase 4"], ["Route planner", "Phase 5"], ["Trends", "Phase 6"],
  ["Model performance", "Phase 6"], ["Settings", "Phase 6"], ["About & limitations", "Phase 6"],
] as const;

export default function App() {
  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Primary">
        <div className="brand"><span className="logo" aria-hidden>◈</span> FloodSense</div>
        <nav>
          <NavLink to="/" end>Overview</NavLink>
          <NavLink to="/sources">Data sources &amp; health</NavLink>
          {PLANNED.map(([label, phase]) => (
            <span key={label} className="nav-disabled" aria-disabled="true" title={`Not built yet — planned for ${phase}`}>
              {label} <em>{phase}</em>
            </span>
          ))}
        </nav>
      </aside>
      <main>
        <div className="banner" role="note">
          Advisory tool for a student project. Not an official warning system — follow instructions from
          authorities (GHMC, HYDRAA, police, emergency services).
        </div>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
