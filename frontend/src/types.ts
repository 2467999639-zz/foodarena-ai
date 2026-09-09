// Shared domain types mirroring the backend Pydantic contracts.

export type SessionStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'VALIDATING'
  | 'SUCCESS'
  | 'FAILED';

export type AgentName = 'sichuan_spicy' | 'cantonese_wellness';
export type Cuisine = 'sichuan' | 'cantonese';
export type Weather = 'sunny' | 'rainy' | 'cold' | 'hot' | 'humid';

export interface AgentMessage {
  round: number;
  agent: AgentName;
  argument: string;
  evidence: string;
}

export interface ScoreBreakdown {
  taste: number;
  budget: number;
  weather: number;
  debate: number;
}

export interface DebateReport {
  dish: string;
  cuisine: Cuisine;
  reason: string;
  confidence: number;
  score_breakdown: ScoreBreakdown;
}

export interface SessionSummary {
  session_id: string;
  status: SessionStatus;
}

export interface SessionView {
  session_id: string;
  status: SessionStatus;
  messages: AgentMessage[];
  report: DebateReport | null;
  failure_reason: string | null;
}

export interface PreferenceInput {
  taste: string;
  budget_yuan: number;
  weather: Weather;
  companions: number;
}

// UI-presentation labels
export const WEATHER_LABELS: Record<Weather, string> = {
  sunny: '晴',
  rainy: '雨',
  cold: '冷',
  hot: '热',
  humid: '潮湿',
};

export const AGENT_LABELS: Record<AgentName, string> = {
  sichuan_spicy: '川辣派',
  cantonese_wellness: '粤式养生派',
};

export const AGENT_EMOJI: Record<AgentName, string> = {
  sichuan_spicy: '🌶️',
  cantonese_wellness: '🍲',
};

export const CUISINE_LABELS: Record<Cuisine, string> = {
  sichuan: '川味',
  cantonese: '粤式',
};

export const STATUS_LABELS: Record<SessionStatus, string> = {
  PENDING: '待开始',
  RUNNING: '辩论进行中',
  VALIDATING: '裁决中',
  SUCCESS: '已完成',
  FAILED: '失败',
};
