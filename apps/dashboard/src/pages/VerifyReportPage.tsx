import { humanize, qualificationName } from "../presentation";
import { useEffect, useState } from "react";
import { publicVerify } from "../api";
import { ApiError, type PublicVerifyOut } from "../types";
import { DashboardShell } from "../components/DashboardShell";

export function VerifyReportPage({ reportId }: { reportId?: string }) {
  const [result, setResult] = useState<PublicVerifyOut | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState(reportId ?? '');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!reportId) return;
    let active = true;
    setLoading(true); setResult(null); setError('');
    publicVerify(reportId).then(value => { if (active) setResult(value); }).catch(err => {
      if (active) setError(err instanceof ApiError && err.status === 404 ? 'No signed report exists for this report ID.' : 'Could not reach the verification server. Please try again.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reportId, retry]);
  return <DashboardShell><div className="verify-shell"><div className="breadcrumb"><a href="#/public">Public queue</a> / Verify report</div><p className="mono">{reportId}</p><h1>Verify assessment report</h1>
    {!reportId && <section className="card" style={{marginTop: 24}}><h2>Find a signed report</h2><form className="verify-search" onSubmit={e => { e.preventDefault(); if (query.trim()) window.location.hash = `#/verify/${encodeURIComponent(query.trim())}`; }}><label>Report ID<input required value={query} onChange={e => setQuery(e.target.value)} placeholder="Enter the report ID from your assessment" /></label><button type="submit">Verify report</button></form></section>}
    {loading && <p role="status">Checking report signature…</p>}
    {error && <div className="notice error" role="alert">{error}<div className="panel-actions"><button onClick={() => setRetry(v => v + 1)}>Retry</button><a href="#/verify">Try another report</a></div></div>}
    {result && <><div className={`verify-banner ${result.valid ? '' : 'error'}`}><span className="verify-icon" aria-hidden="true">{result.valid ? '✓' : '×'}</span><div><strong className={result.valid ? '' : 'error'}>{result.valid ? 'Signature verified' : 'Verification failed'}</strong><p>{result.valid ? 'The stored report has not been altered since it was signed.' : 'The report signature could not be verified. Do not rely on this report.'}</p></div></div><section className="card"><h2>Report details</h2><dl><dt>Report ID</dt><dd className="mono">{result.report_id}</dd><dt>Qualification pack</dt><dd>{qualificationName(result.qp)} <small className="pack-reference">{result.qp}</small></dd><dt>Outcome</dt><dd>{humanize(result.recommendation)}</dd><dt>Issued</dt><dd>{new Date(result.signed_at).toLocaleString()}</dd><dt>Revision</dt><dd>v{result.revision_number}</dd></dl></section><section className="card"><h2>Signature details</h2><dl><dt>Algorithm</dt><dd>Ed25519</dd><dt>Signing key</dt><dd className="mono">{result.key_id}</dd><dt>PDF SHA-256</dt><dd className="mono">{result.sha256}</dd><dt>Status</dt><dd>{result.status}</dd></dl></section><p className="disclaimer">Assessor recommendation — not an official certificate. This verifies the server’s stored report. Compare its SHA-256 with your PDF to confirm the file matches. Private PDFs are available to authorized reviewers from the assessment.</p><a href="#/verify" className="openlink">Verify another report →</a></>}
  </div></DashboardShell>;
}
