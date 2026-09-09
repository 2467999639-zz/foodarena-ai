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
  personas?: Record<string, string>;
}

export type PersonaStyle =
  | 'sichuan'
  | 'cantonese'
  | 'northwestern'
  | 'japanese'
  | 'light_food'
  | 'heavy_food';

export interface PersonaInput {
  agent: AgentName;
  label: string;
  style: PersonaStyle;
  flavour: string;
}

export interface DebateSettings {
  min_rounds: number;
  max_rounds: number;
  early_stop: boolean;
}

export interface DebateStartRequest {
  provider?: 'mock' | 'real';
  personas?: PersonaInput[];
  settings?: DebateSettings;
}

export interface MenuItemView {
  name: string;
  cuisine: Cuisine;
  price_yuan: number;
  spice_level: number;
  rich_level: number;
  heat_rating: number;
  prep_minutes: number;
  vegetarian: boolean;
  tags: string[];
  source: 'canteen' | 'takeaway' | 'sample';
  delivery_only: boolean;
}

export interface MenuCatalogView {
  source_label: string;
  items: MenuItemView[];
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

export const STYLE_LABELS: Record<PersonaStyle, string> = {
  sichuan: '川味 · 麻辣鲜香',
  cantonese: '粤式 · 汤水清淡',
  northwestern: '西北 · 豪迈碳水',
  japanese: '日式 · 营养均衡',
  light_food: '轻食 · 低卡清爽',
  heavy_food: '硬核 · 重油重味',
};

export const SOURCE_LABELS = {
  canteen: '食堂',
  takeaway: '外卖',
  sample: '样例',
} as const;
