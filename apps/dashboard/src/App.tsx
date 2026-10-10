import { useEffect, useState } from "react";
import { logout as apiLogout, me } from "./api";
import { LoginPage } from "./pages/LoginPage";
import { QueuePage } from "./pages/QueuePage";
import { AssessmentDetailPage } from "./pages/AssessmentDetailPage";
import { useHashRoute } from "./useHashRoute";
import type { MeOut } from "./types";

type AuthState = "checking" | "signed-out" | "signed-in";

function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [user, setUser] = useState<MeOut | null>(null);
  const hash = useHashRoute();

  useEffect(() => {
    checkAuth();
  }, []);

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
    return <LoginPage onLoggedIn={checkAuth} />;
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
