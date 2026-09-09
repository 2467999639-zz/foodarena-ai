import { useState } from 'react';
import type {
  DebateSettings,
  MenuCatalogView,
  PersonaInput,
  PersonaStyle,
  PreferenceInput,
  Weather,
} from '../types';
import { SOURCE_LABELS, STYLE_LABELS, WEATHER_LABELS } from '../types';

export interface FormSubmit {
  preferences: PreferenceInput;
  personas?: PersonaInput[];
  settings?: DebateSettings;
}

interface Props {
  onSubmit: (submit: FormSubmit) => void;
  submitting: boolean;
  menu?: MenuCatalogView | null;
}

interface FieldErrors {
  taste?: string;
  budget_yuan?: string;
  companions?: string;
  label?: string;
  flavour?: string;
}

const WEATHER_OPTIONS: Weather[] = ['sunny', 'rainy', 'cold', 'hot', 'humid'];
const STYLE_OPTIONS = Object.keys(STYLE_LABELS) as PersonaStyle[];

const DEFAULT_PERSONAS: PersonaInput[] = [
  { agent: 'sichuan_spicy', label: '川辣派', style: 'sichuan', flavour: '' },
  {
    agent: 'cantonese_wellness',
    label: '粤式养生派',
    style: 'cantonese',
    flavour: '',
  },
];

export function PreferenceForm({ onSubmit, submitting, menu }: Props) {
  const [taste, setTaste] = useState('');
  const [budget, setBudget] = useState('15');
  const [weather, setWeather] = useState<Weather>('sunny');
  const [companions, setCompanions] = useState('1');
  const [errors, setErrors] = useState<FieldErrors>({});

  // Persona + settings
  const [personas, setPersonas] = useState<PersonaInput[]>(DEFAULT_PERSONAS);
  const [earlyStop, setEarlyStop] = useState(true);
  const [minRounds, setMinRounds] = useState('2');
  const [useCustom, setUseCustom] = useState(false);

  const updatePersona = (
    index: number,
    patch: Partial<PersonaInput>,
  ) => {
    setPersonas((prev) =>
      prev.map((p, i) => (i === index ? { ...p, ...patch } : p)),
    );
  };

  const validate = (): FormSubmit | null => {
    const next: FieldErrors = {};
    if (!taste.trim()) next.taste = '请填写想吃的口味，如「麻辣」「清淡」';
    else if (taste.trim().length > 60) next.taste = '口味描述请控制在 60 字以内';

    const budgetNum = Number(budget);
    if (!Number.isInteger(budgetNum)) next.budget_yuan = '请输入整数预算';
    else if (budgetNum < 1 || budgetNum > 200)
      next.budget_yuan = '预算需在 1–200 元之间';

    const compNum = Number(companions);
    if (!Number.isInteger(compNum)) next.companions = '请输入整数人数';
    else if (compNum < 1 || compNum > 20)
      next.companions = '同行人数需在 1–20 之间';

    personas.forEach((p, i) => {
      if (p.label.trim().length > 20)
        next.label = `第 ${i + 1} 位大厨的名字请控制在 20 字内`;
      if (p.flavour.length > 200)
        next.flavour = `第 ${i + 1} 位大厨的立场描述请控制在 200 字内`;
    });

    setErrors(next);
    if (Object.keys(next).length > 0) return null;

    const preferences: PreferenceInput = {
      taste: taste.trim(),
      budget_yuan: budgetNum,
      weather,
      companions: compNum,
    };

    const settings: DebateSettings = {
      min_rounds: Math.max(1, Math.min(3, Number(minRounds) || 2)),
      max_rounds: 3,
      early_stop: earlyStop,
    };

    const cleanedPersonas: PersonaInput[] = personas.map((p) => ({
      ...p,
      label: p.label.trim(),
      flavour: p.flavour.trim(),
    }));

    return {
      preferences,
      personas: useCustom ? cleanedPersonas : undefined,
      settings: useCustom ? settings : undefined,
    };
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const result = validate();
    if (result) onSubmit(result);
  };

  const field = (hasError: boolean) =>
    hasError ? 'input input-error' : 'input';

  return (
    <form className="form-card" onSubmit={handleSubmit} noValidate>
      <h2 className="section-title">今天想吃什么？</h2>
      <p className="muted">
        告诉两位大厨你的偏好，他们会进行一场选餐辩论并出具战报。
        {menu && (
          <span className="menu-source"> 菜单来源：{menu.source_label}（{menu.items.length} 道）</span>
        )}
      </p>

      {menu && menu.items.length > 0 && (
        <details className="menu-strip">
          <summary>查看当前可用菜单（{menu.items.length} 道）</summary>
          <ul className="menu-list">
            {menu.items.map((item) => (
              <li key={item.name} className="menu-row">
                <span className="menu-name">
                  {item.name}
                  {item.delivery_only && <em className="tag">仅外卖</em>}
                </span>
                <span className="tag">{SOURCE_LABELS[item.source]}</span>
                <span className="menu-price">¥{item.price_yuan}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <label className="field">
        <span>口味</span>
        <input
          className={field(Boolean(errors.taste))}
          placeholder="例如：麻辣 / 清淡 / 酸甜"
          value={taste}
          onChange={(e) => setTaste(e.target.value)}
        />
        {errors.taste && <em className="field-error">{errors.taste}</em>}
      </label>

      <div className="grid-2">
        <label className="field">
          <span>人均预算（元）</span>
          <input
            type="number"
            className={field(Boolean(errors.budget_yuan))}
            min={1}
            max={200}
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
          {errors.budget_yuan && (
            <em className="field-error">{errors.budget_yuan}</em>
          )}
        </label>

        <label className="field">
          <span>同行人数</span>
          <input
            type="number"
            className={field(Boolean(errors.companions))}
            min={1}
            max={20}
            value={companions}
            onChange={(e) => setCompanions(e.target.value)}
          />
          {errors.companions && (
            <em className="field-error">{errors.companions}</em>
          )}
        </label>
      </div>

      <label className="field">
        <span>天气</span>
        <div className="chips">
          {WEATHER_OPTIONS.map((option) => (
            <button
              type="button"
              key={option}
              className={`chip ${weather === option ? 'chip-active' : ''}`}
              onClick={() => setWeather(option)}
            >
              {WEATHER_LABELS[option]}
            </button>
          ))}
        </div>
      </label>

      <label className="switch-row">
        <input
          type="checkbox"
          checked={useCustom}
          onChange={(e) => setUseCustom(e.target.checked)}
        />
        <span>自定义大厨性格与辩论规则</span>
      </label>

      {useCustom && (
        <div className="persona-panel">
          <div className="panel-title">大厨性格</div>
          {personas.map((p, i) => (
            <div key={p.agent} className="persona-card">
              <div className="row space-between">
                <strong>{i === 0 ? '🍜 大厨 A' : '🍲 大厨 B'}</strong>
              </div>
              <div className="grid-2">
                <label className="field">
                  <span>名字</span>
                  <input
                    className={field(Boolean(errors.label))}
                    value={p.label}
                    maxLength={20}
                    onChange={(e) =>
                      updatePersona(i, { label: e.target.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>流派</span>
                  <select
                    className="input"
                    value={p.style}
                    onChange={(e) =>
                      updatePersona(i, { style: e.target.value as PersonaStyle })
                    }
                  >
                    {STYLE_OPTIONS.map((style) => (
                      <option key={style} value={style}>
                        {STYLE_LABELS[style]}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="field">
                <span>人设补充（可选，一句话立场）</span>
                <input
                  className={field(Boolean(errors.flavour))}
                  placeholder="例如：主打爆辣烤鱼和钵钵鸡"
                  value={p.flavour}
                  maxLength={200}
                  onChange={(e) =>
                    updatePersona(i, { flavour: e.target.value })
                  }
                />
              </label>
            </div>
          ))}

          <div className="panel-title">辩论规则</div>
          <label className="field">
            <span>最少辩论轮数（达成一致后可在第 N 轮提前终结）</span>
            <select
              className="input"
              value={minRounds}
              onChange={(e) => setMinRounds(e.target.value)}
            >
              <option value="1">1 轮</option>
              <option value="2">2 轮</option>
              <option value="3">3 轮</option>
            </select>
          </label>
          <label className="switch-row">
            <input
              type="checkbox"
              checked={earlyStop}
              onChange={(e) => setEarlyStop(e.target.checked)}
            />
            <span>双方论点趋同时提前终结辩论（默认开启）</span>
          </label>
        </div>
      )}

      {errors.label && <em className="field-error">{errors.label}</em>}
      {errors.flavour && <em className="field-error">{errors.flavour}</em>}

      <button className="btn btn-primary" type="submit" disabled={submitting}>
        {submitting ? '创建中…' : '开始辩论 🔥'}
      </button>
    </form>
  );
}
