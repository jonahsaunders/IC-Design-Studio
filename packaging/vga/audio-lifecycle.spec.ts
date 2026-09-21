// SPDX-License-Identifier: GPL-3.0-or-later
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AudioPlayer } from './AudioPlayer';

// Keep worklet loading pending so the hide/show race does not depend on the
// machine's asset-loading speed or availability of a physical audio device.
let finishLoading: () => void;
let context: {
  state: string;
  sampleRate: number;
  destination: object;
  audioWorklet: { addModule: ReturnType<typeof vi.fn> };
  addEventListener: ReturnType<typeof vi.fn>;
  resume: ReturnType<typeof vi.fn>;
  suspend: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  const loaded = new Promise<void>(resolve => { finishLoading = resolve; });
  context = {
    state: 'suspended', sampleRate: 192000, destination: {},
    audioWorklet: { addModule: vi.fn(() => loaded) },
    addEventListener: vi.fn(),
    resume: vi.fn(async () => { context.state = 'running'; }),
    suspend: vi.fn(async () => { context.state = 'suspended'; }),
  };
  vi.stubGlobal('AudioContext', class { constructor() { return context; } });
  vi.stubGlobal('AudioWorkletNode', class {
    connect = vi.fn();
    port = { onmessage: null, postMessage: vi.fn() };
  });
});

afterEach(() => { vi.unstubAllGlobals(); });

async function workletReady() {
  finishLoading();
  await Promise.resolve();
  await Promise.resolve();
}

test('a late worklet must not undo an explicit audio suspension', async () => {
  const player = new AudioPlayer(192000);
  player.resume();
  expect(player.needsFeeding()).toBe(true);
  // Hiding the preview cancels audio; showing it resumes rendering only.
  player.suspend();
  await workletReady();
  expect(context.resume).not.toHaveBeenCalled();
  expect(player.isRunning()).toBe(false);
  expect(player.needsFeeding()).toBe(false);
});

test('loading a worklet without a playback request leaves audio suspended', async () => {
  const player = new AudioPlayer(192000);
  await workletReady();
  expect(context.resume).not.toHaveBeenCalled();
  expect(player.isRunning()).toBe(false);
});

test('an outstanding user request can start audio when the worklet is ready', async () => {
  const player = new AudioPlayer(192000);
  player.resume();
  await workletReady();
  expect(context.resume).toHaveBeenCalledOnce();
  expect(player.isRunning()).toBe(true);
});

test('stale buffer messages cannot restart stopped audio; a new request can', async () => {
  const player = new AudioPlayer(192000);
  player.resume();
  await workletReady();
  context.resume.mockClear();
  player.suspend();
  const filled = { data: [200, 0.5] } as MessageEvent;
  player.handleMessage(filled);
  expect(context.resume).not.toHaveBeenCalled();
  expect(player.isRunning()).toBe(false);
  player.resume();
  player.handleMessage(filled);
  expect(context.resume).toHaveBeenCalledOnce();
  expect(player.isRunning()).toBe(true);
});
