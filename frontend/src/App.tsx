import { useCallback, useEffect, useState } from 'react';
import { createSession, fetchMenu, fetchReport } from './api';
import { DebateView } from './components/DebateView';
import { PreferenceForm } from './components/PreferenceForm';
import type { FormSubmit } from './components/PreferenceForm';
import { ReportView } from './components/ReportView';
import type { DebateReport, MenuCatalogView } from './types';
import { useLiveSession } from './useLiveSession';

type Route =
  | { page: 'home' }
  | { page: 'debate'; sessionId: string }
  | { page: 'report'; sessionId: string };

function readRoute(): Route {
  const hash = window.location.hash;
  if (hash.startsWith('#/report/')) {
    return { page: 'report', sessionId: hash.slice('#/report/'.length) };
  }
  if (hash.startsWith('#/debate/')) {
    return { page: 'debate', sessionId: hash.slice('#/debate/'.length) };
  }
  return { page: 'home' };
}

function navigate(route: string) {
  window.location.hash = route;
}

const STORAGE_KEY = 'foodarena_session_id';

function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => readRoute());
  useEffect(() => {
    const onChange = () => setRoute(readRoute());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

export default function App() {
  const route = useHashRoute();
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [menu, setMenu] = useState<MenuCatalogView | null>(null);

  useEffect(() => {
    let alive = true;
    if (route.page === 'home') {
      fetchMenu()
        .then((m) => alive && setMenu(m))
        .catch(() => alive && setMenu(null));
    }
    return () => {
      alive = false;
    };
  }, [route.page]);

  // A pending create means we are about to own a session; once created we jump
  // to the debate route for that id. Survives reload via sessionStorage.
  const [createdId, setCreatedId] = useState<string | null>(null);

  useEffect(() => {
    if (createdId) {
      sessionStorage.setItem(STORAGE_KEY, createdId);
      navigate(`#/debate/${createdId}`);
      setCreatedId(null);
    }
  }, [createdId]);

  const handleSubmit = useCallback(async (submit: FormSubmit) => {
    setCreating(true);
    setCreateError(null);
    try {
      const summary = await createSession(
        submit.preferences,
        submit.personas || submit.settings
          ? { personas: submit.personas, settings: submit.settings }
          : undefined,
      );
      setCreatedId(summary.session_id);
    } catch (err) {
      setCreateError(String(err));
    } finally {
      setCreating(false);
    }
  }, []);

  const startAgain = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEY);
    navigate('#/');
  }, []);

  if (route.page === 'report') {
    return (
      <Shell onHome={startAgain}>
        <ReportRoute sessionId={route.sessionId} onStartAgain={startAgain} />
      </Shell>
    );
  }

  // Debate route: live-stream the debate; the finished report is reached via
  // the "查看完整战报" button instead of an automatic redirect.
  if (route.page === 'debate') {
    return (
      <Shell onHome={startAgain}>
        <DebateRoute
          key={route.sessionId}
          sessionId={route.sessionId}
          onStartAgain={startAgain}
        />
      </Shell>
    );
  }

  return (
    <Shell onHome={startAgain}>
      <div className="hero">
        <PreferenceForm onSubmit={handleSubmit} submitting={creating} menu={menu} />
        {createError && <p className="banner error">⚠️ {createError}</p>}
      </div>
    </Shell>
  );
}

function DebateRoute({
  sessionId,
  onStartAgain,
}: {
  sessionId: string;
  onStartAgain: () => void;
}) {
  const { state } = useLiveSession(sessionId, true);

  return (
    <DebateView
      state={state}
      sessionId={sessionId}
      onRetry={() => window.location.reload()}
      onStartAgain={onStartAgain}
    />
  );
}

function ReportRoute({
  sessionId,
  onStartAgain,
}: {
  sessionId: string;
  onStartAgain: () => void;
}) {
  const [report, setReport] = useState<DebateReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setReport(null);
    setError(null);
    fetchReport(sessionId)
      .then((r) => {
        if (alive) setReport(r);
      })
      .catch((err) => alive && setError(String(err)));
    return () => {
      alive = false;
    };
  }, [sessionId]);

  if (error)
    return (
      <div className="card error-card">
        <h2>无法查看战报</h2>
        <p className="muted">{error}</p>
        <button className="btn btn-primary" onClick={onStartAgain}>
          重新开始
        </button>
      </div>
    );

  if (!report)
    return (
      <div className="card centered">
        <div className="spinner" />
        <p className="muted">正在读取战报…</p>
      </div>
    );

  return <ReportView report={report} onStartAgain={onStartAgain} />;
}

function Shell({
  children,
  onHome,
}: {
  children: React.ReactNode;
  onHome: () => void;
}) {
  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <button className="brand" onClick={onHome}>
            <span className="brand-logo">🍜</span>
            <span className="brand-text">
              <strong>FoodArena</strong>
              <span className="brand-sub">校园干饭辩论赛</span>
            </span>
          </button>
          <button className="btn btn-ghost btn-small" onClick={onHome}>
            重新开始
          </button>
        </div>
      </header>
      <main className="app-main">{children}</main>
      <footer className="app-footer">
        <span>FoodArena AI · 川辣派 vs 粤式养生派 · 菜品数据均为合成内容</span>
      </footer>
    </div>
  );
}
