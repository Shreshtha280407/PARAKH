import { humanize } from "../presentation";
import type { ReactNode } from "react";
import { useHashRoute } from "../useHashRoute";
import { useAssessorSession } from './AssessorSession';
import { useState } from 'react';

export function BrandEmblem({ className }: {className?: string}) {
  return <svg viewBox="235 15 860 860" className={className} role="img" aria-label="PARAKH emblem"><image href="/brand/parakh-logo.png" width="1254" height="1254" /></svg>;
}

export function Brand() {
  return <a className="brandmark" href="#/" aria-label="Parakh home"><BrandEmblem /><span className="brand-wordmark">Parakh</span></a>;
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const hash = useHashRoute();
  const {account, signOut} = useAssessorSession();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  return <div className="app-shell"><a className="skip-link" href="#main-content">Skip to content</a>
    <header className="topbar"><Brand />
      <nav className="nav" aria-label="Main navigation">
        {[['#/queue', 'Queue'], ['#/public', 'Public queue'], ['#/verify', 'Verify report']].map(([href, label]) => {
          const active = hash === href || (href === '#/queue' && hash.startsWith('#/assessments/')) || (href === '#/verify' && hash.startsWith('#/verify/'));
          return <a key={href} href={href} className={`navlink ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined}>{label}</a>;
        })}
      </nav><span className="userchip"><span className="avatar" aria-hidden="true">{account?.name.charAt(0).toUpperCase() ?? 'P'}</span>{account?.name ?? 'Assessor dashboard'}{account && <button className="header-signout" disabled={signingOut} onClick={() => { setSigningOut(true); setSignOutError(''); void signOut().catch(() => setSignOutError('Could not end the server session. Please try signing out again.')).finally(() => setSigningOut(false)); }}>{signingOut ? 'Signing out…' : 'Sign out'}</button>}</span>
    </header><main id="main-content" className="shell">{signOutError && <p className="error" role="alert">{signOutError}</p>}{children}</main>
  </div>;
}

export function StatusBadge({ value }: { value: string }) {
  return <span className={`status status-${value.toLowerCase()}`}>{humanize(value)}</span>;
}

export function LandingPage() {
  return <div className="landing"><div className="brandpane"><Brand /><div><h2>Prior-skill Assessment &amp; Recognition through AI-driven Knowledge</h2><p>Review evidence, score performance criteria, and sign off NSQF-aligned RPL assessments.</p></div><span className="foot">NSQF-ALIGNED · RPL ASSESSMENT PLATFORM</span></div>
    <main className="formpane"><div className="formcard"><BrandEmblem className="landing-logo" /><h1>Assessor dashboard</h1><p className="sub">A clearer view of every worker’s skills.</p><a href="#/queue" className="button enter-button">Enter <span aria-hidden="true">→</span></a></div></main>
  </div>;
}
