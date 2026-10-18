import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { getAssessorAccount, logoutAssessor, type AssessorAccount } from '../api';
import { ApiError } from '../types';

interface SessionState {
  account: AssessorAccount | null;
  loaded: boolean;
  setAccount: (account: AssessorAccount | null) => void;
  signOut: () => Promise<void>;
}
const AssessorContext = createContext<SessionState | null>(null);

export function AssessorSessionProvider({children}: {children: ReactNode}) {
  const [account, setAccount] = useState<AssessorAccount | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    getAssessorAccount().then(value => { if (active) setAccount(value); })
      .catch(() => { /* Anonymous browsing remains available. */ })
      .finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!account) return;
    const expire = () => { if (Date.now() >= Date.parse(account.expires_at)) setAccount(null); };
    const timer = window.setTimeout(expire, Math.max(0, Date.parse(account.expires_at) - Date.now()));
    document.addEventListener('visibilitychange', expire);
    return () => { window.clearTimeout(timer); document.removeEventListener('visibilitychange', expire); };
  }, [account]);
  const signOut = useCallback(async () => {
    try { await logoutAssessor(); }
    catch (error) { if (!(error instanceof ApiError && error.status === 401)) throw error; }
    setAccount(null);
  }, []);
  return <AssessorContext value={{account, loaded, setAccount, signOut}}>{children}</AssessorContext>;
}

export function useAssessorSession() {
  const value = useContext(AssessorContext);
  if (!value) throw new Error('Assessor session provider is required');
  return value;
}
