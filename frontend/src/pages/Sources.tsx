import { api } from "../api";
import { useAsync } from "../useAsync";

export default function Sources() {
  const { data, error, loading, retry } = useAsync(api.sources);
  return (
    <section>
      <h1>Data sources &amp; health</h1>
      <p className="muted">Register of every dataset FloodSense relies on, and whether this project has actually verified it.</p>
      {loading && <div className="skeleton" role="status" aria-label="Loading sources" />}
      {error && !loading && (
        <div className="card error" role="alert">{error}<div><button onClick={retry}>Retry</button></div></div>
      )}
      {data && data.length === 0 && <p className="muted">No sources registered. Run <code>python -m app.cli init-db</code>.</p>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Source</th><th>Role</th><th>License</th><th>Type</th><th>Verification</th><th>Limitations</th></tr></thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.key}>
                  <td>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> : s.name}</td>
                  <td>{s.role}</td><td>{s.license}</td>
                  <td><span className={`tag ${s.label}`}>{s.label.replace("_", " ")}</span></td>
                  <td><span className={`tag ${s.verification}`}>{s.verification.replace("_", " ")}</span></td>
                  <td>{s.limitations}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
