import type {
  DebateReport,
  PreferenceInput,
  SessionSummary,
  SessionView,
} from './types';

const BASE = import.meta.env.VITE_API_BASE_URL ?? '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    let detail = `请求失败 (HTTP ${response.status})`;
    try {
      const body = await response.json();
      const message =
        body?.detail?.error ??
        (typeof body?.detail === 'string' ? body.detail : undefined);
      if (message) detail = message;
    } catch {
      /* keep default message */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function createSession(
  preferences: PreferenceInput,
): Promise<SessionSummary> {
  return request<SessionSummary>('/api/v1/sessions', {
    method: 'POST',
    body: JSON.stringify(preferences),
  });
}

export async function fetchSession(sessionId: string): Promise<SessionView> {
  return request<SessionView>(`/api/v1/sessions/${sessionId}`);
}

export async function fetchReport(sessionId: string): Promise<DebateReport> {
  return request<DebateReport>(`/api/v1/sessions/${sessionId}/report`);
}

export function eventsUrl(sessionId: string): string {
  return `${BASE}/api/v1/sessions/${sessionId}/events`;
}
