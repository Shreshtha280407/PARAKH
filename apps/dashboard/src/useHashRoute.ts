import { useEffect, useState } from "react";

// A tiny hand-rolled router: three screens (login, queue, assessment
// detail) don't need react-router -- window.location.hash plus a listener
// is a few lines and keeps the dependency list to exactly what the backend
// stack needs.
export function useHashRoute(): string {
  const [hash, setHash] = useState(window.location.hash || "#/queue");

  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/queue");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return hash;
}

export function navigate(hash: string): void {
  window.location.hash = hash;
}
