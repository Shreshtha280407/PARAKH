import { useEffect, useState } from "react";
import { getQueue } from "../api";
import { navigate } from "../useHashRoute";
import { ApiError, type QueueItemOut } from "../types";

type LoadState = "loading" | "error" | "empty" | "ready";

export function QueuePage() {
  const [items, setItems] = useState<QueueItemOut[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string>("");

  function load() {
    let cancelled = false;
    setState("loading");
    getQueue()
      .then((result) => {
        if (cancelled) return;
        setItems(result);
        setState(result.length === 0 ? "empty" : "ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Could not reach the server.");
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }

  useEffect(load, []);

  return (
    <div className="page">
      <h1>Assessor Queue</h1>
      {state === "loading" && <p>Loading…</p>}
      {state === "error" && (
        <p className="error">
          Failed to load the queue: {error} <button onClick={load}>Retry</button>
        </p>
      )}
      {state === "empty" && <p>No assessments are waiting for review right now.</p>}
      {state === "ready" && (
        <table>
          <thead>
            <tr>
              <th>Worker</th>
              <th>Pack</th>
              <th>Status</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.worker_name}</td>
                <td>{item.pack_code}</td>
                <td>
                  <span className={`status status-${item.status}`}>{item.status}</span>
                </td>
                <td>{new Date(item.created_at).toLocaleString()}</td>
                <td>
                  <button onClick={() => navigate(`#/assessments/${item.id}`)}>Open</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
