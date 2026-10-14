import { useEffect, useState } from "react";
import { publicVerify } from "../api";
import { ApiError, type PublicVerifyOut } from "../types";

type LoadState = "loading" | "error" | "ready";

/**
 * Public, unauthenticated report verification -- the exact page the signed
 * PDF's own QR code points at (see server/app/routers/verify.py). No login,
 * no cookie, no credentials sent: this must work for an arbitrary third
 * party who scanned a QR code, not just a logged-in assessor. Rendered
 * directly by App.tsx BEFORE the auth gate -- see the #/verify/:id route
 * check there.
 */
export function VerifyReportPage({ reportId }: { reportId: string }) {
  const [state, setState] = useState<LoadState>("loading");
  const [result, setResult] = useState<PublicVerifyOut | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setState("loading");
    publicVerify(reportId)
      .then((r) => {
        setResult(r);
        setState("ready");
      })
      .catch((err) => {
        setError(err instanceof ApiError && err.status === 404 ? "No signed report exists for this report ID." : "Could not reach the verification server.");
        setState("error");
      });
  }, [reportId]);

  return (
    <div className="centered-page">
      <div className="card" style={{ maxWidth: "32rem" }}>
        <h1>KaushalPramaan — Report verification</h1>
        <p className="disclaimer">Assessor recommendation — not an official certificate.</p>

        {state === "loading" && <p>Checking…</p>}
        {state === "error" && <p className="error">{error}</p>}

        {state === "ready" && result && (
          <>
            <p className={result.valid ? "badge-ok" : "error"} style={{ fontSize: "1.1rem" }}>
              {result.valid ? "✓ Signature verified — this report has not been tampered with." : "✗ VERIFICATION FAILED — do not trust this report."}
            </p>
            <dl>
              <dt>Report ID</dt>
              <dd>
                <code>{result.report_id}</code>
              </dd>
              <dt>Status</dt>
              <dd>{result.status}</dd>
              <dt>Qualification Pack</dt>
              <dd>{result.qp}</dd>
              <dt>Revision</dt>
              <dd>v{result.revision_number}</dd>
              <dt>Recommendation</dt>
              <dd>{result.recommendation}</dd>
              <dt>PDF SHA-256</dt>
              <dd>
                <code>{result.sha256}</code>
              </dd>
              <dt>Signing key</dt>
              <dd>
                <code>{result.key_id}</code>
              </dd>
              <dt>Signed</dt>
              <dd>{new Date(result.signed_at).toLocaleString()}</dd>
            </dl>
            <p className="hint">
              This page confirms the signature on a report with this ID -- it is not proof that any particular PDF
              file you may be holding matches it. To verify an actual PDF file offline, use
              <code> tools/verify_report.py</code> with this report's detached receipt and a trusted public key.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
