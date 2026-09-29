"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { count, money, percent } from "../lib/contracts.mjs";
const readable = (s) => (s || "not assessed").replaceAll("_", " ");
const titles = {
  payment_stage_hypothesis: "Investigate the payment stage",
  measurement_issue: "Resolve measurement before acting",
  insufficient_measurement: "More evidence is needed",
  no_signal: "No conversion signal detected",
};
async function read(view, dataset, signal) {
  const r = await fetch(
    "/api/nemo?" +
      new URLSearchParams({ view, ...(dataset ? { dataset } : {}) }),
    { signal },
  );
  const v = await r.json();
  if (!r.ok)
    throw new Error(
      v.error + (v.request_id ? " · Reference " + v.request_id : ""),
    );
  return v;
}
function JsonDetail({ title, value }) {
  return (
    <details>
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
export default function Home() {
  const [catalog, setCatalog] = useState([]),
    [selected, setSelected] = useState(""),
    [view, setView] = useState("decision-case");
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(true),
    [reload, setReload] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    read("datasets", null, c.signal)
      .then((v) => {
        setCatalog(v.datasets);
        setSelected((old) =>
          v.datasets.some((s) => s.id === old) ? old : v.datasets[0]?.id || "",
        );
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setBusy(false);
        }
      });
    return () => c.abort();
  }, [reload]);
  useEffect(() => {
    if (!selected) return;
    const c = new AbortController();
    read(view, selected, c.signal)
      .then((v) => {
        setData(v);
        setError("");
        setBusy(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setData(null);
          setError(e.message);
          setBusy(false);
        }
      });
    return () => c.abort();
  }, [selected, view, reload]);
  const source = catalog.find((x) => x.id === selected),
    change = (v) => {
      if (v === view) return;
      setData(null);
      setBusy(true);
      setError("");
      setView(v);
    };
  const caseData = view === "decision-case" ? data : null;
  const current = caseData?.observations?.current?.metrics,
    baseline = caseData?.observations?.baseline?.metrics;
  return (
    <div className="shell">
      <aside>
        <Link className="brand" href="/">
          <span className="mark">N</span>NEMO<span className="beta">LAB</span>
        </Link>
        <p className="tagline">Evidence to decisions.</p>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Workspace">
          {[
            ["decision-case", "◎", "Decision Case"],
            ["opportunities", "↗", "Opportunities"],
            ["analyst", "◇", "Evidence Analyst"],
            ["measurement-health", "◈", "Measurement"],
            ["decisions", "▤", "Decision ledger"],
          ].map(([id, icon, label]) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              onClick={() => change(id)}
            >
              <span>{icon}</span>
              {label}
            </button>
          ))}
        </nav>
        <div className="side-note">
          <span className="dot" /> LOCAL WORKSPACE
          <p>
            Read-only evidence review.
            <br />
            No actions are executed.
          </p>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumb">
            Workspace <span>/</span>{" "}
            {view === "decision-case" ? "Decision Case" : readable(view)}
          </div>
          <div className="source-select">
            <label htmlFor="dataset">Source</label>
            <select
              id="dataset"
              value={selected}
              onChange={(e) => {
                setData(null);
                setBusy(true);
                setSelected(e.target.value);
              }}
            >
              {catalog.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </header>
        <div className="page-heading">
          <div>
            <div className="eyebrow">GROWTH INTELLIGENCE</div>
            <h1>
              {view === "decision-case"
                ? "Follow the evidence."
                : readable(view)}
            </h1>
            <p>Understand what changed. Know what the evidence supports.</p>
          </div>
          <button
            className="refresh"
            onClick={() => {
              setBusy(true);
              setData(null);
              setReload((x) => x + 1);
            }}
          >
            ↻ Refresh
          </button>
        </div>
        <div className="source-line">
          <span className="pill">{readable(source?.origin)}</span>
          <span>
            {source?.delivery === "public_lab_export"
              ? "Read-only public lab export · No live API connection"
              : "Source labels are declared, not independently verified."}
          </span>
        </div>
        {busy && !error && (
          <div className="empty" role="status">
            Reading canonical evidence…
          </div>
        )}
        {error && (
          <div className="empty error" role="alert">
            <h2>Evidence unavailable</h2>
            <p>{error}</p>
            <p>
              Check the local API and configured dataset. No substitute figures
              are shown.
            </p>
          </div>
        )}
        {caseData && (
          <>
            <section className="case-hero">
              <div>
                <div className="eyebrow">
                  DECISION CASE{" "}
                  <span className="case-id">{caseData.case_id}</span>
                </div>
                <h2>
                  {titles[caseData.finding] || readable(caseData.finding)}
                </h2>
                <p>{caseData.question}</p>
                <div className="hero-tags">
                  <span className="pill amber">
                    {readable(caseData.claim_type)}
                  </span>
                  <span className="pill">
                    {readable(caseData.evidence_strength)}
                  </span>
                </div>
              </div>
              <div className="hero-status">
                <span>MEASUREMENT CONFIDENCE</span>
                <strong>
                  {readable(caseData.measurement?.measurement_confidence)}
                </strong>
                <small>Check outcome, not a probability</small>
              </div>
            </section>
            <div className="periods">
              Baseline {caseData.scope.baseline_start} →{" "}
              {caseData.scope.current_start} <span>vs.</span> Current{" "}
              {caseData.scope.current_start} → {caseData.scope.end_exclusive}{" "}
              <small>End dates exclusive</small>
            </div>
            {current && (
              <section className="metrics" aria-label="Observed metrics">
                {[
                  ["Session conversion", "cvr", percent],
                  ["Observed sessions", "sessions", (m) => count(m?.value)],
                  ["Paid orders", "orders", (m) => count(m?.value)],
                  ["Merchandise receipts", "revenue", (m) => money(m?.value)],
                ].map(([label, key, format]) => (
                  <article key={key}>
                    <span>{label}</span>
                    <strong>{format(current[key])}</strong>
                    <small>
                      Baseline <b>{format(baseline?.[key])}</b>
                    </small>
                  </article>
                ))}
              </section>
            )}
            <div className="case-grid">
              <section className="panel">
                <div className="panel-heading">
                  <h2>Payment evidence by device</h2>
                  <span className="pill">Observed</span>
                </div>
                <p>
                  Payment success among attempting sessions. Rates do not
                  identify a cause.
                </p>
                {caseData.device_payment_comparisons?.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Device</th>
                          <th>Baseline</th>
                          <th>Current</th>
                          <th>Assessment</th>
                        </tr>
                      </thead>
                      <tbody>
                        {caseData.device_payment_comparisons.map((r) => (
                          <tr key={r.device}>
                            <th>{readable(r.device)}</th>
                            <td>
                              {percent(r.baseline_success_rate)}
                              <small>
                                {count(r.baseline_attempts)} attempts
                              </small>
                            </td>
                            <td>
                              <strong>{percent(r.current_success_rate)}</strong>
                              <small>
                                {count(r.current_attempts)} attempts
                              </small>
                            </td>
                            <td>
                              <span
                                className={
                                  "pill " +
                                  (r.supports_deterioration ? "amber" : "")
                                }
                              >
                                {r.supports_deterioration
                                  ? "Supports review"
                                  : "No supporting signal"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="quiet">
                    Device payment comparison is not supported by this snapshot.
                  </div>
                )}
                <JsonDetail
                  title="Inspect exact observation evidence"
                  value={caseData.observations}
                />
              </section>
              <section className="panel next">
                <div className="eyebrow">NEXT INVESTIGATION</div>
                <h2>
                  A question to resolve,
                  <br />
                  before an action to take.
                </h2>
                <p>{caseData.next_investigation}</p>
                <div className="boundary">
                  <strong>Economic action is withheld</strong>
                  <p>{caseData.economic_action}</p>
                  <small>Incremental profit: unknown</small>
                </div>
              </section>
            </div>
            <div className="case-grid">
              <section className="panel">
                <h2>Competing explanations</h2>
                <ul className="evidence-list">
                  {caseData.alternatives?.map((x, i) => (
                    <li key={i}>
                      <span>{String(i + 1).padStart(2, "0")}</span>
                      {x}
                    </li>
                  ))}
                </ul>
                <JsonDetail
                  title="Contradictions and recommendation gates"
                  value={{
                    contradictions: caseData.contradictions,
                    recommendations: caseData.recommendations,
                  }}
                />
              </section>
              <section className="panel">
                <h2>Evidence boundaries</h2>
                <ul>
                  {caseData.limitations?.map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>
                <JsonDetail
                  title="Provenance and revision"
                  value={{
                    revision_id: caseData.revision_id,
                    provenance: caseData.provenance,
                  }}
                />
              </section>
            </div>
          </>
        )}
        {data && view === "opportunities" && (
          <section className="panel">
            <h2>Review opportunities</h2>
            <p>
              Evidence-gated investigations. Ordering does not imply causal
              return.
            </p>
            {data.opportunities?.length ? (
              data.opportunities.map((o, i) => (
                <article className="opportunity" key={o.opportunity_id || i}>
                  <div className="eyebrow">REVIEW {i + 1}</div>
                  <h3>{readable(o.title || o.kind || o.opportunity_id)}</h3>
                  <JsonDetail
                    title="Evidence and action boundaries"
                    value={o}
                  />
                </article>
              ))
            ) : (
              <div className="quiet">
                No supported opportunities in this snapshot.
              </div>
            )}
            <JsonDetail
              title="Complete board and withheld candidates"
              value={data}
            />
          </section>
        )}
        {data && view === "measurement-health" && (
          <section className="panel">
            <h2>Measurement before decisions</h2>
            <p className="large-status">
              {readable(data.measurement_confidence)}
            </p>
            <p>
              Deterministic checks express data trust, not causal certainty.
            </p>
            <div className="dependency-grid">
              {Object.entries(data.dependencies || {}).map(([k, v]) => (
                <article key={k}>
                  <span>{readable(k)}</span>
                  <strong>{readable(v)}</strong>
                </article>
              ))}
            </div>
            <JsonDetail
              title="Checks, limitations and readiness gates"
              value={data}
            />
          </section>
        )}
        {data && view === "decisions" && (
          <section className="panel">
            <h2>Decision ledger</h2>
            <p>
              Recorded human assertions and evidence revisions. Read-only in
              this workspace.
            </p>
            {data.decisions?.length ? (
              data.decisions.map((d) => (
                <article className="opportunity" key={d.decision_id}>
                  <h3>{d.decision_id}</h3>
                  <span className="pill">{readable(d.status)}</span>
                  <JsonDetail title="Decision history" value={d} />
                </article>
              ))
            ) : (
              <div className="quiet">
                No decisions recorded for this dataset.
              </div>
            )}
            <JsonDetail title="Auditable ledger events" value={data.events} />
          </section>
        )}
        {data && view === "analyst" && (
          <section className="panel">
            <div className="panel-heading">
              <h2>Grounded evidence explanation</h2>
              <span className="pill">Deterministic · no model call</span>
            </div>
            <p>
              Statements come from the validated Decision Case. This view
              performs no new analysis.
            </p>
            <ul className="evidence-list">
              {data.statements.map((s) => (
                <li key={s.evidence_id}>
                  <div>
                    <strong>{s.text}</strong>
                    <br />
                    <small>
                      Evidence: {s.evidence_id} · {s.source_pointer}
                    </small>
                  </div>
                </li>
              ))}
            </ul>
            <JsonDetail
              title="Case revision, citations and limitations"
              value={data}
            />
          </section>
        )}
        <footer>
          NEMO{" "}
          <span>
            Canonical evidence → measurement → diagnosis → human review
          </span>
          <span>Merchandise receipts ≠ profit</span>
        </footer>
      </main>
    </div>
  );
}
