import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchSession } from './api';
import { useLiveSession } from './useLiveSession';

vi.mock('./api', () => ({
  eventsUrl: (sessionId: string) => `/api/v1/sessions/${sessionId}/events`,
  fetchSession: vi.fn(),
}));

type Listener = (event: MessageEvent) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  listeners = new Map<string, Listener[]>();
  onerror: (() => void) | null = null;
  close = vi.fn();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const callback = listener as Listener;
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), callback]);
  }

  emit(type: string, data: unknown) {
    const event = new MessageEvent(type, {
      data: typeof data === 'string' ? data : JSON.stringify(data),
    });
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

describe('useLiveSession', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    vi.mocked(fetchSession).mockResolvedValue({
      session_id: 'session-1',
      status: 'PENDING',
      messages: [],
      report: null,
      failure_reason: null,
    });
  });

  it('renders each alternating message as soon as its SSE frame arrives', async () => {
    const { result, unmount } = renderHook(() =>
      useLiveSession('session-1', true),
    );
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];

    act(() => {
      source.emit('status', { status: 'RUNNING' });
      source.emit('round_started', { round: 1, agent: 'sichuan_spicy' });
    });
    expect(result.current.state.activeAgent).toBe('sichuan_spicy');

    act(() => {
      source.emit('message', {
        round: 1,
        agent: 'sichuan_spicy',
        argument: '川辣派第一轮',
        evidence: '证据 A',
      });
    });
    expect(result.current.state.messages.map((message) => message.agent)).toEqual([
      'sichuan_spicy',
    ]);

    act(() => {
      source.emit('round_started', {
        round: 1,
        agent: 'cantonese_wellness',
      });
      source.emit('message', {
        round: 1,
        agent: 'cantonese_wellness',
        argument: '粤式养生派第一轮',
        evidence: '证据 B',
      });
      source.emit('done', 'SUCCESS');
    });

    expect(result.current.state.messages.map((message) => message.agent)).toEqual([
      'sichuan_spicy',
      'cantonese_wellness',
    ]);
    expect(source.close).toHaveBeenCalled();
    unmount();
  });
});
