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
  const {
    status,
    currentRound,
    activeAgent,
    messages,
    report,
    personas,
    notice,
  } = state;

  const labelFor = (agent: AgentName) =>
    personas[agent] || AGENT_LABELS[agent];

  const grouped: Record<number, AgentMessage[]> = {};
  for (const message of messages) {
    (grouped[message.round] ??= []).push(message);
  }

  const busy = status === 'RUNNING' || status === 'VALIDATING';

  return (
    <div className="debate-wrap">
      <header className="row space-between wrap">
        <div>
          <h2>辩论进行中</h2>
          <p className="muted mono">会话 {sessionId.slice(0, 8)}…</p>
        </div>
        <span className={badgeClass(status)}>
          {STATUS_LABELS[status]}
          {busy && '…'}
        </span>
      </header>

      {notice && <p className="banner info">ℹ️ {notice}</p>}

      {status === 'PENDING' && (
        <div className="card centered empty-state">
          <div className="spinner" />
          <p>正在召唤两位大厨入场…</p>
        </div>
      )}

      <div className="rounds">
        {[1, 2, 3].map((roundNumber) => {
          const roundMessages = grouped[roundNumber] ?? [];
          const thinking = busy && currentRound === roundNumber;
          return (
            <section key={roundNumber} className="round-block">
              <div className="round-heading">
                <span>{ROUND_NAMES[roundNumber - 1]}</span>
                {thinking && roundMessages.length < 2 && (
                  <span className="pulse-dot" />
                )}
              </div>
              {roundMessages.length === 0 ? (
                <p className="muted placeholder">
                  {thinking || currentRound === null
                    ? `${activeAgent ? labelFor(activeAgent) : '大厨'}正在思考…`
                    : '尚未进行到本轮'}
                </p>
              ) : (
                roundMessages.map((message) => (
                  <SpeechCard
                    key={`${message.agent}-${message.round}`}
                    message={message}
                    labelFor={labelFor}
                  />
                ))
              )}
              {thinking && roundMessages.length === 1 && (
                <p className="muted placeholder">
                  {activeAgent ? `${labelFor(activeAgent)}正在回应…` : '对方正在回应…'}
                </p>
              )}
            </section>
          );
        })}
      </div>

      {/* Terminal states, always shown under the transcript. */}
      {status === 'FAILED' && (
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
      )}

      {status === 'SUCCESS' && (
        <div className="card report-card">
          {report ? (
            <>
              <h2>🏆 干饭战报已出炉</h2>
              <p className="dish">
                {AGENT_EMOJI[report.cuisine === 'sichuan' ? 'sichuan_spicy' : 'cantonese_wellness']}{' '}
                {report.dish}
              </p>
              <p className="reason">{report.reason}</p>
              <button
                className="btn btn-primary"
                onClick={() => {
                  window.location.hash = `#/report/${sessionId}`;
                }}
              >
                查看完整战报与评分
              </button>
            </>
          ) : (
            <div className="centered inline">
              <div className="spinner" />
              <p className="muted">正在让裁判长打分…</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SpeechCard({
  message,
  labelFor,
}: {
  message: AgentMessage;
  labelFor: (agent: AgentName) => string;
}) {
  const agent = message.agent;
  return (
    <article className={`speech ${agentSide(agent)}`}>
      <div className="speech-avatar">{AGENT_EMOJI[agent]}</div>
      <div className="speech-body">
        <div className="speech-meta">
          <strong>{labelFor(agent)}</strong>
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
