import type { DebateReport } from '../types';
import { CUISINE_LABELS } from '../types';

interface Props {
  report: DebateReport;
  onStartAgain: () => void;
}

const DIMENSIONS = [
  { key: 'taste', label: '口味' },
  { key: 'budget', label: '预算' },
  { key: 'weather', label: '天气' },
  { key: 'debate', label: '辩论表现' },
] as const;

export function ReportView({ report, onStartAgain }: Props) {
  return (
    <div className="report-wrap">
      <div className="card report-card full">
        <div className="row space-between wrap">
          <h2>🏆 干饭战报</h2>
          <button className="btn btn-ghost" onClick={onStartAgain}>
            再来一场
          </button>
        </div>

        <div className="report-hero">
          <p className="report-cuisine">{CUISINE_LABELS[report.cuisine]}</p>
          <h1 className="report-dish">{report.dish}</h1>
          <div className="confidence">
            <div className="confidence-bar">
              <div
                className="confidence-fill"
                style={{ width: `${Math.round(report.confidence * 100)}%` }}
              />
            </div>
            <span>推荐置信度 {Math.round(report.confidence * 100)}%</span>
          </div>
        </div>

        <p className="reason">{report.reason}</p>

        <h3 className="subsection">四维评分</h3>
        <div className="scores">
          {DIMENSIONS.map(({ key, label }) => {
            const value = report.score_breakdown[key] ?? 0;
            return (
              <div className="score" key={key}>
                <div className="row space-between">
                  <span>{label}</span>
                  <strong>{value.toFixed(1)}</strong>
                </div>
                <div className="score-bar">
                  <div
                    className="score-fill"
                    style={{ width: `${(value / 5) * 100}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
