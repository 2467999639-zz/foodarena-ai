import type {
  DebateReport,
  DebateSettings,
  MenuCatalogView,
  PersonaInput,
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

export interface SessionOptions {
  personas?: PersonaInput[];
  settings?: DebateSettings;
}

export async function createSession(
  preferences: PreferenceInput,
  options?: SessionOptions,
): Promise<SessionSummary> {
  const personas = options?.personas?.filter((p) => p.label.trim().length > 0);
  const hasCustom =
    (personas && personas.length > 0) ||
    options?.settings?.min_rounds !== 2 ||
    options?.settings?.early_stop === false;
  const payload = hasCustom
    ? { preferences, personas, settings: options?.settings }
    : { preferences };
  return request<SessionSummary>('/api/v1/sessions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchSession(sessionId: string): Promise<SessionView> {
  return request<SessionView>(`/api/v1/sessions/${sessionId}`);
}

export async function fetchReport(sessionId: string): Promise<DebateReport> {
  return request<DebateReport>(`/api/v1/sessions/${sessionId}/report`);
}

export async function fetchMenu(): Promise<MenuCatalogView> {
  return request<MenuCatalogView>('/api/v1/menu');
}

export function eventsUrl(sessionId: string): string {
  return `${BASE}/api/v1/sessions/${sessionId}/events`;
}

