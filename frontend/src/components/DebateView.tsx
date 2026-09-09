import type { AgentMessage, AgentName, SessionStatus } from '../types';
import { AGENT_EMOJI, AGENT_LABELS, STATUS_LABELS } from '../types';
import type { LiveState } from '../useLiveSession';

interface Props {
  state: LiveState;
  sessionId: string;
  onRetry: () => void;
  onStartAgain: () => void;
}

const ROUND_NAMES = ['第 1 轮 · 亮立场', '第 2 轮 · 互驳', '第 3 轮 · 决胜'];

function badgeClass(status: SessionStatus): string {
  switch (status) {
    case 'SUCCESS':
      return 'status-badge success';
    case 'FAILED':
      return 'status-badge failed';
    case 'RUNNING':
    case 'VALIDATING':
      return 'status-badge running';
    default:
      return 'status-badge';
  }
}

export function DebateView({ state, sessionId, onRetry, onStartAgain }: Props) {
  const { status, currentRound, messages, report } = state;

  if (status === 'FAILED') {
    return (
      <div className="card error-card">
        <h2>😵 辩论出错了</h2>
        <p className="muted">
          {state.failureReason ?? '未知错误'}。你可以稍后重试本场辩论。
        </p>
        <div className="row gap">
          <button className="btn btn-primary" onClick={onRetry}>
            重试
          </button>
          <button className="btn btn-ghost" onClick={onStartAgain}>
            重新开始
          </button>
        </div>
      </div>
    );
  }

  const grouped: Record<number, AgentMessage[]> = {};
  for (const message of messages) {
    (grouped[message.round] ??= []).push(message);
  }

  return (
    <div className="debate-wrap">
      <header className="row space-between wrap">
        <div>
          <h2>辩论进行中</h2>
          <p className="muted mono">会话 {sessionId.slice(0, 8)}…</p>
        </div>
        <span className={badgeClass(status)}>
          {STATUS_LABELS[status]}
          {(status === 'RUNNING' || status === 'VALIDATING') && '…'}
        </span>
      </header>

      {status === 'PENDING' && (
        <div className="card centered empty-state">
          <div className="spinner" />
          <p>正在召唤两位大厨入场…</p>
        </div>
      )}

      <div className="rounds">
        {[1, 2, 3].map((roundNumber) => {
          const roundMessages = grouped[roundNumber] ?? [];
          return (
            <section key={roundNumber} className="round-block">
              <div className="round-heading">
                <span>{ROUND_NAMES[roundNumber - 1]}</span>
                {currentRound === roundNumber &&
                  status !== 'SUCCESS' &&
                  roundMessages.length < 2 && <span className="pulse-dot" />}
              </div>
              {roundMessages.length === 0 ? (
                <p className="muted placeholder">两位大厨还在思考…</p>
              ) : (
                roundMessages.map((message) => (
                  <SpeechCard key={`${message.agent}-${message.round}`} message={message} />
                ))
              )}
            </section>
          );
        })}
      </div>

      {status === 'SUCCESS' && report && (
        <div className="card report-card">
          <h2>🏆 干饭战报</h2>
          <p className="dish">{AGENT_EMOJI[report.cuisine === 'sichuan' ? 'sichuan_spicy' : 'cantonese_wellness']} {report.dish}</p>
          <p className="reason">{report.reason}</p>
          <button
            className="btn btn-primary"
            onClick={() => {
              window.location.hash = `#/report/${sessionId}`;
            }}
          >
            查看完整战报
          </button>
        </div>
      )}
    </div>
  );
}

function SpeechCard({ message }: { message: AgentMessage }) {
  const agent = message.agent;
  const sideClass = agentSide(agent);
  return (
    <article className={`speech ${sideClass}`}>
      <div className="speech-avatar">{AGENT_EMOJI[agent]}</div>
      <div className="speech-body">
        <div className="speech-meta">
          <strong>{AGENT_LABELS[agent]}</strong>
          <span className="tag">第 {message.round} 轮</span>
        </div>
        <p className="speech-argument">{message.argument}</p>
        <p className="speech-evidence">📎 {message.evidence}</p>
      </div>
    </article>
  );
}

function agentSide(agent: AgentName): string {
  return agent === 'sichuan_spicy' ? 'speech-sichuan' : 'speech-cantonese';
}
