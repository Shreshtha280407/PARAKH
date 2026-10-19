import { finalOutcomeLabel, humanize } from '../presentation';
import { reportDownloadUrl } from '../api';
import type { SignedReportOut } from '../types';

export function SignedReportPanel({assessmentId, report, publicationConsent}: {
  assessmentId: number; report: SignedReportOut; publicationConsent?: boolean;
}) {
  return <section className="card signed-report-panel" aria-label="Signed assessment report">
    <div className="signed-report-heading"><h2>Signed report</h2><span className="report-signed-indicator">Signed PDF issued</span></div>
    <dl><dt>Report ID</dt><dd className="mono">{report.report_uid}</dd>
      <dt>Final outcome</dt><dd><span className={`status status-${report.final_recommendation.toLowerCase()}`}>{finalOutcomeLabel(report.final_recommendation)}</span><span className="hint"> · {humanize(report.final_recommendation)}</span></dd>
      <dt>Issued</dt><dd>{new Date(report.signed_at).toLocaleString()} · v{report.revision_number}</dd></dl>
    <div className="panel-actions"><a className="button" href={reportDownloadUrl(assessmentId,'pdf')} target="_blank" rel="noreferrer">Download Signed PDF</a><a className="openlink" href={`#/verify/${encodeURIComponent(report.report_uid)}`}>Verify Report →</a></div>
    <p className="hint">A signature proves report integrity; the outcome records the assessor’s decision. Open verification to check the stored document.</p>
    {publicationConsent === false && <p className="hint">Not listed publicly: separate candidate consent to publish the final outcome has not been recorded. Name consent alone does not permit publication.</p>}
  </section>;
}
