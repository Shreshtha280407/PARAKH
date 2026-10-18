import { useEffect, useState } from "react";
import { logout as apiLogout, me, onSessionExpired } from "./api";
import { LoginPage } from "./pages/LoginPage";
import { QueuePage } from "./pages/QueuePage";
import { AssessmentDetailPage } from "./pages/AssessmentDetailPage";
import { VerifyReportPage } from "./pages/VerifyReportPage";
import { AssessorSessionProvider } from "./components/AssessorSession";
import { useHashRoute } from "./useHashRoute";
import type { MeOut } from "./types";

type AuthState = "checking" | "signed-out" | "signed-in";

function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [user, setUser] = useState<MeOut | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const hash = useHashRoute();

  useEffect(() => {
    onSessionExpired(() => {
      setUser(null);
      setSessionMessage("Your session expired. Please sign in again.");
      setAuthState("signed-out");
    });
    return () => onSessionExpired(null);
  }, []);

  // P7: /verify/:reportId is PUBLIC -- the exact page a signed PDF's QR code
  // points at, meant for an arbitrary third party who scanned it, not a
  // logged-in assessor. Checked BEFORE the auth gate below on purpose, and
  // never touches checkAuth/the login flow at all.
  const verifyMatch = hash.match(/^#\/verify\/([^/]+)$/);

  useEffect(() => {
    if (verifyMatch) return; // public page -- no need to check auth at all
    checkAuth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifyMatch !== null]);

  if (verifyMatch) {
    return <AssessorSessionProvider><VerifyReportPage reportId={decodeURIComponent(verifyMatch[1])} /></AssessorSessionProvider>;
  }

  function checkAuth() {
    // No local token to check first -- the session lives in an HttpOnly
    // cookie the browser attaches automatically; just ask the server.
    setAuthState("checking");
    me()
      .then((result) => {
        setUser(result);
        setAuthState("signed-in");
      })
      .catch(() => {
        // not signed in / cookie missing or expired -- back to login, no error toast needed
        setAuthState("signed-out");
      });
  }

  async function handleLogout() {
    try {
      await apiLogout(); // clears the HttpOnly cookie server-side -- JS can't touch it directly
    } catch {
      // best-effort -- still reset local UI state even if the request failed
    }
    setUser(null);
    setAuthState("signed-out");
    window.location.hash = "#/queue";
  }

  if (authState === "checking") {
    return (
      <div className="centered-page">
        <p>Loading…</p>
      </div>
    );
  }

  if (authState === "signed-out") {
    return (
      <LoginPage
        onLoggedIn={() => {
          setSessionMessage(null);
          checkAuth();
        }}
        sessionMessage={sessionMessage}
      />
    );
  }

  const assessmentMatch = hash.match(/^#\/assessments\/(\d+)$/);

  return (
    <div className="app-shell">
      <header className="top-bar">
        <span className="brand">KaushalPramaan</span>
        <nav>
          <a href="#/queue">Queue</a>
        </nav>
        <div className="spacer" />
        <span className="user-chip">
          {user?.display_name} ({user?.role})
        </span>
        <button onClick={handleLogout}>Log out</button>
      </header>
      <main>
        {assessmentMatch ? (
          <AssessmentDetailPage id={Number(assessmentMatch[1])} />
        ) : (
          <QueuePage />
        )}
      </main>
    </div>
  );
}

export default App;
