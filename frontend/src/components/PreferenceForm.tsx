import { useState } from 'react';
import type { PreferenceInput, Weather } from '../types';
import { WEATHER_LABELS } from '../types';

interface Props {
  onSubmit: (prefs: PreferenceInput) => void;
  submitting: boolean;
}

interface FieldErrors {
  taste?: string;
  budget_yuan?: string;
  companions?: string;
}

const WEATHER_OPTIONS: Weather[] = ['sunny', 'rainy', 'cold', 'hot', 'humid'];

export function PreferenceForm({ onSubmit, submitting }: Props) {
  const [taste, setTaste] = useState('');
  const [budget, setBudget] = useState('15');
  const [weather, setWeather] = useState<Weather>('sunny');
  const [companions, setCompanions] = useState('1');
  const [errors, setErrors] = useState<FieldErrors>({});

  const validate = (): PreferenceInput | null => {
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

    setErrors(next);
    if (Object.keys(next).length > 0) return null;
    return {
      taste: taste.trim(),
      budget_yuan: budgetNum,
      weather,
      companions: compNum,
    };
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const prefs = validate();
    if (prefs) onSubmit(prefs);
  };

  const field = (hasError: boolean) =>
    hasError ? 'input input-error' : 'input';

  return (
    <form className="form-card" onSubmit={handleSubmit} noValidate>
      <h2 className="section-title">今天想吃什么？</h2>
      <p className="muted">
        告诉两位大厨你的偏好，他们会为你进行一场 3 轮选餐辩论并出具战报。
      </p>

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

      <button className="btn btn-primary" type="submit" disabled={submitting}>
        {submitting ? '创建中…' : '开始辩论 🔥'}
      </button>
    </form>
  );
}
