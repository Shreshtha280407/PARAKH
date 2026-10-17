import { PUBLIC_DASHBOARD } from "./api";
import PrivateApp from "./PrivateApp";
import { PublicQueuePage } from "./pages/PublicQueuePage";
import { OpenAssessmentPage } from "./pages/OpenAssessmentPage";
import { VerifyReportPage } from "./pages/VerifyReportPage";
import { useHashRoute } from "./useHashRoute";

export default function App() {
  const hash = useHashRoute();
  if (!PUBLIC_DASHBOARD) return <PrivateApp />;
  const verify = hash.match(/^#\/verify\/([^/]+)$/);
  if (verify) return <VerifyReportPage reportId={decodeURIComponent(verify[1])} />;
  const assessment = hash.match(/^#\/assessments\/(\d+)$/);
  return <div className="app-shell">
    <header className="top-bar"><span className="brand">PARAKH</span><nav><a href="#/queue">Submitted assessments</a></nav></header>
    <main>{assessment ? <OpenAssessmentPage key={assessment[1]} id={Number(assessment[1])} /> : <PublicQueuePage />}</main>
  </div>;
}
