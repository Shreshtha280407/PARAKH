import { useState, type FormEvent } from "react";
import { login } from "../api";
import { ApiError } from "../types";

export function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // The server sets the session as an HttpOnly cookie on this response
      // -- nothing for the client to store itself.
      await login(email, password);
      onLoggedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="centered-page">
      <form onSubmit={handleSubmit} className="card">
        <h1>KaushalPramaan — Assessor Login</h1>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
        <p className="hint">Workers do not log in here — this is assessor/admin only.</p>
      </form>
    </div>
  );
}
