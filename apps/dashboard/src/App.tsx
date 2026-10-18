import { PUBLIC_DASHBOARD } from "./api";
import { PublicQueuePage } from "./pages/PublicQueuePage";
import { OpenAssessmentPage } from "./pages/OpenAssessmentPage";
import { VerifyReportPage } from "./pages/VerifyReportPage";
import { useHashRoute } from "./useHashRoute";
import { DashboardShell } from "./components/DashboardShell";
import { AssessorSessionProvider } from "./components/AssessorSession";
import { lazy, Suspense, useCallback, useState } from 'react';
import { DecisionComplete, type CompletedDecision } from './components/DecisionComplete';
const PrivateApp = lazy(() => import('./PrivateApp'));
const LandingPage = lazy(() => import('./pages/LandingPage'));

export default function App() {
  if (!PUBLIC_DASHBOARD) return <Suspense fallback={<p role="status">Loading dashboard…</p>}><PrivateApp /></Suspense>;
  return <AssessorSessionProvider><PublicApp /></AssessorSessionProvider>;
}

function PublicApp() {
  const hash = useHashRoute();
  const [completed, setCompleted] = useState<CompletedDecision>();
  const closeCompletion = useCallback(() => setCompleted(undefined), []);
  if (!hash || hash === '#/' || hash === '#') return <Suspense fallback={<div className="centered-page" role="status">Opening Parakh…</div>}><LandingPage /></Suspense>;
  const verify = hash.match(/^#\/verify(?:\/([^/]+))?$/);
  if (verify) return <VerifyReportPage key={verify[1] ?? "search"} reportId={verify[1] ? decodeURIComponent(verify[1]) : undefined} />;
  const assessment = hash.match(/^#\/assessments\/(\d+)$/);
  const publicView = hash === '#/public';
  return <><DashboardShell>
    {assessment ? <OpenAssessmentPage key={assessment[1]} id={Number(assessment[1])} onCompleted={setCompleted} /> : <PublicQueuePage publicView={publicView} />}
  </DashboardShell>{completed && <DecisionComplete decision={completed} onDone={closeCompletion} />}</>;
}
