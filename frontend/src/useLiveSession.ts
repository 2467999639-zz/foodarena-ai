import { useEffect, useRef, useState } from 'react';
import { eventsUrl, fetchSession } from './api';
import type {
  AgentMessage,
  DebateReport,
  SessionStatus,
  SessionView,
} from './types';

export interface LiveState {
  status: SessionStatus;
  currentRound: number | null;
  messages: AgentMessage[];
  report: DebateReport | null;
  failureReason: string | null;
}

const initial: LiveState = {
  status: 'PENDING',
  currentRound: null,
  messages: [],
  report: null,
  failureReason: null,
};

function terminal(status: SessionStatus): boolean {
  return status === 'SUCCESS' || status === 'FAILED';
}

function fromView(view: SessionView): LiveState {
  return {
    status: view.status,
    currentRound:
      view.messages.length > 0
        ? Math.max(...view.messages.map((m) => m.round))
        : null,
    messages: view.messages,
    report: view.report,
    failureReason: view.failure_reason,
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
    let restarted = false;

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

    const startStream = () => {
      if (cancelled || done) return;
      source = new EventSource(eventsUrl(sessionId));

      source.addEventListener('status', (raw: MessageEvent) => {
        if (cancelled) return;
        try {
          const { status } = JSON.parse(raw.data) as { status: SessionStatus };
          setState((prev) => ({ ...prev, status }));
          if (terminal(status)) done = true;
        } catch {
          /* malformed frame */
        }
      });

      source.addEventListener('round_started', (raw: MessageEvent) => {
        if (cancelled) return;
        try {
          const { round } = JSON.parse(raw.data) as { round: number };
          setState((prev) => ({ ...prev, currentRound: round }));
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

      source.onerror = () => {
        // EventSource reconnects automatically; once the server ends the
        // stream (done) or the session reached a terminal state we stop.
        source?.close();
        if (cancelled) return;
        if (done) return;
        if (!restarted) {
          restarted = true;
          void restore().then(() => {
            // If storage shows we are already terminal there is nothing to
            // replay; otherwise open a fresh stream.
            if (!cancelled && !done) startStream();
          });
        }
      };
    };

    void restore().then(() => {
      if (!cancelled && !done) startStream();
    });

    return () => {
      cancelled = true;
      source?.close();
    };
  }, [sessionId, enabled]);

  return { state, error };
}
