import { useEffect, useRef, useState } from 'react';
import { eventsUrl, fetchSession } from './api';
import type {
  AgentMessage,
  AgentName,
  DebateReport,
  SessionStatus,
  SessionView,
} from './types';

export interface LiveState {
  status: SessionStatus;
  currentRound: number | null;
  activeAgent: AgentName | null;
  messages: AgentMessage[];
  report: DebateReport | null;
  failureReason: string | null;
  personas: Record<string, string>;
  notice: string | null;
}

const initial: LiveState = {
  status: 'PENDING',
  currentRound: null,
  activeAgent: null,
  messages: [],
  report: null,
  failureReason: null,
  personas: {},
  notice: null,
};

function terminal(status: SessionStatus): boolean {
  return status === 'SUCCESS' || status === 'FAILED';
}

function fromView(view: SessionView): LiveState {
  const lastMessage = view.messages[view.messages.length - 1];
  const activeAgent =
    view.status === 'RUNNING'
      ? lastMessage?.agent === 'sichuan_spicy'
        ? 'cantonese_wellness'
        : 'sichuan_spicy'
      : null;
  const currentRound = lastMessage
    ? lastMessage.agent === 'cantonese_wellness' && view.status === 'RUNNING'
      ? Math.min(lastMessage.round + 1, 3)
      : lastMessage.round
    : view.status === 'RUNNING'
      ? 1
      : null;
  return {
    status: view.status,
    currentRound,
    activeAgent,
    messages: view.messages,
    report: view.report,
    failureReason: view.failure_reason,
    personas: view.personas ?? {},
    notice: null,
  };
}

export function isTerminal(status: SessionStatus): boolean {
  return terminal(status);
}

/**
 * Live-drive a debate session through its SSE event stream.
 *
 * If the session is still PENDING the first event from the backend starts the
 * debate; every chef message, status change and final report arrives as an SSE
 * frame. On a connection drop the hook restores state from the stored session
 * (events are replayed by the backend) so nothing is duplicated.
 */
export function useLiveSession(sessionId: string | null, enabled: boolean) {
  const [state, setState] = useState<LiveState>(initial);
  const [error, setError] = useState<string | null>(null);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  useEffect(() => {
    if (!sessionId || !enabled) return undefined;

    let cancelled = false;
    let source: EventSource | null = null;
    let done = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const restore = async () => {
      try {
        const view = await fetchSession(sessionId);
        if (cancelled) return;
        done = terminal(view.status);
        setState(fromView(view));
        setError(null);
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    };

    const scheduleReconnect = () => {
      if (cancelled || done || reconnectTimer !== null) return;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        void restore().then(() => {
          if (!cancelled && !done) startStream();
        });
      }, 500);
    };

    const startStream = () => {
      if (cancelled || done) return;
      source = new EventSource(eventsUrl(sessionId));

      source.addEventListener('status', (raw: MessageEvent) => {
        if (cancelled) return;
        try {
          const { status } = JSON.parse(raw.data) as { status: SessionStatus };
          setState((prev) => ({
            ...prev,
            status,
            activeAgent: terminal(status) ? null : prev.activeAgent,
          }));
          if (terminal(status)) done = true;
        } catch {
          /* malformed frame */
        }
      });

      source.addEventListener('round_started', (raw: MessageEvent) => {
        if (cancelled) return;
        try {
          const { round, agent } = JSON.parse(raw.data) as {
            round: number;
            agent: AgentName;
          };
          setState((prev) => ({ ...prev, currentRound: round, activeAgent: agent }));
        } catch {
          /* ignore */
        }
      });

      source.addEventListener('message', (raw: MessageEvent) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(raw.data) as AgentMessage;
          setState((prev) => {
            const exists = prev.messages.some(
              (m) =>
                m.round === msg.round &&
                m.agent === msg.agent &&
                m.argument === msg.argument,
            );
            if (exists) return prev;
            return {
              ...prev,
              messages: [...prev.messages, msg],
              currentRound: msg.round,
              activeAgent: null,
            };
          });
        } catch {
          /* malformed frame */
        }
      });

      source.addEventListener('report', (raw: MessageEvent) => {
        if (cancelled) return;
        try {
          const { report } = JSON.parse(raw.data) as { report: DebateReport };
          setState((prev) => ({ ...prev, report }));
        } catch {
          /* ignore */
        }
      });

      source.addEventListener('info', (raw: MessageEvent) => {
        if (cancelled) return;
        try {
          const { message } = JSON.parse(raw.data) as { message: string };
          setState((prev) => ({ ...prev, notice: message }));
        } catch {
          /* ignore */
        }
      });

      source.addEventListener('done', (raw: MessageEvent) => {
        source?.close();
        const finalStatus = raw.data as SessionStatus;
        if (terminal(finalStatus)) {
          done = true;
        } else {
          // Another connection owns a debate that is still RUNNING.  Replay
          // what is persisted, then reconnect until the terminal event exists.
          scheduleReconnect();
        }
      });

      source.onerror = () => {
        source?.close();
        scheduleReconnect();
      };
    };

    void restore().then(() => {
      if (!cancelled && !done) startStream();
    });

    return () => {
      cancelled = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      source?.close();
    };
  }, [sessionId, enabled]);

  return { state, error };
}
