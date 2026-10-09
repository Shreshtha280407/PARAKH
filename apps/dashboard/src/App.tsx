import { useEffect, useState } from "react";
import { me } from "./api";
import { clearToken, getToken } from "./auth";
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
    if (!getToken()) {
      setAuthState("signed-out");
      return;
    }
    setAuthState("checking");
    me()
      .then((result) => {
        setUser(result);
        setAuthState("signed-in");
      })
      .catch(() => {
        // token missing/expired/invalid -- back to login, no error toast needed
        clearToken();
        setAuthState("signed-out");
      });
  }

  function handleLogout() {
    clearToken();
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
