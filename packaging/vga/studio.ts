// SPDX-License-Identifier: GPL-3.0-or-later
// IC Design Studio adapter for the pinned Tiny Tapeout VGA Playground.
// The native editor owns all source edits, saving and undo.
import { AudioEngine } from './AudioEngine';
import { FPSCounter } from './FPSCounter';
import { InputController } from './InputController';
import { examples } from './examples';
import apacheLicense from './examples/stripes/LICENSE.txt?raw';
import commonLicense from './examples/common/LICENSE.txt?raw';
import { HDLModuleWASM } from './sim/hdlwasm';
import { decodeVGAOutput, detectSyncPolarity, renderVGAFrame, resetModule, VGA_HEIGHT, VGA_WIDTH } from './sim/vga';
import { initErrorOverlay } from './ui/ErrorOverlay';
import { compileVerilator } from './verilator/compile';
import { detectTopModule } from './verilog';

interface Inputs {
  topModule: string;
  sources: Record<string, string>;
  dataFiles: Record<string, string>;
  includeDirs: string[];
  defines: Record<string, string>;
}

let mod: HDLModuleWASM | null = null;
let polarity = { hsyncActiveLow: true, vsyncActiveLow: true };
let active = false;
let sequence = 0;
let pending: Inputs | null = null;
let compiling = false;
let audio: AudioEngine | null = null;
const status = { state: 'ready', message: 'Choose a VGA preset or preview a Tiny Tapeout VGA cell.', revision: 0, frames: 0 };
const overlay = initErrorOverlay(document.getElementById('error-overlay')!);
const canvas = document.querySelector<HTMLCanvasElement>('#vga-canvas')!;
const ctx = canvas.getContext('2d')!;
const frame = ctx.createImageData(VGA_WIDTH, VGA_HEIGHT);
const pixels = new Uint8Array(frame.data.buffer);
const fps = new FPSCounter();

function suspendAudio() { audio?.suspend(); }
function reset() {
  if (!mod) return;
  resetModule(mod);
  polarity = detectSyncPolarity(mod);
  resetModule(mod);
}

const inputs = new InputController({
  inputButtons: Array.from(document.querySelectorAll<HTMLButtonElement>('#input-values button')),
  gamepadPmodButtons: Array.from(document.querySelectorAll<HTMLButtonElement>('#gamepad-pmod-inputs button')),
  gamepadPmodDiv: document.getElementById('gamepad-pmod-inputs')!,
  isAudioRunning: () => audio?.isRunning() ?? false,
  resumeAudio: () => {
    if (!mod || !active) return;
    // Audio is optional and only initialized after a user gesture.
    try {
      audio ??= new AudioEngine(192000, 25175000,
        () => mod ? (mod.state.uio_out & mod.state.uio_oe) >> 7 : 0,
        () => fps.getFPS(), () => {
          if (!active || !mod) audio?.suspend();
          inputs.updateAudioButton();
        });
      audio.resume();
    } catch (error) { overlay.show('Audio unavailable', String(error)); }
  },
  suspendAudio,
  getUiIn: () => mod?.state.ui_in ?? 0,
  setUiIn: value => { if (mod) mod.state.ui_in = value; },
  onReset: reset,
});

function clear() {
  suspendAudio();
  mod?.dispose(); mod = null;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

async function compilePending() {
  if (compiling) return;
  compiling = true;
  try {
    while (pending) {
      const project = pending; pending = null;
      const revision = sequence;
      clear(); status.state = 'compiling'; status.message = 'Compiling working copy…';
      overlay.show('Compiling', project.topModule);
      let candidate: HDLModuleWASM | null = null;
      try {
        const result = await compileVerilator(project);
        if (revision !== sequence) continue;
        if (!result.output) throw new Error(result.errors.map(e => `${e.file}:${e.line}: ${e.message}`).join('\n'));
        candidate = new HDLModuleWASM(result.output.modules['TOP'], result.output.modules['@CONST-POOL@']);
        candidate.getFileData = path => project.dataFiles[path];
        await candidate.init();
        if (revision !== sequence) { candidate.dispose(); candidate = null; continue; }
        for (const name of ['clk', 'rst_n', 'ena', 'ui_in', 'uo_out', 'uio_in', 'uio_out', 'uio_oe']) {
          if (!candidate.globals.lookup(name)) throw new Error(`Missing Tiny Tapeout port: ${name}`);
        }
        mod = candidate; candidate = null;
        reset(); inputs.resetButtonStates(); fps.reset();
        status.state = 'running'; status.message = project.topModule; status.revision = revision;
        overlay.hide();
      } catch (error) {
        candidate?.dispose();
        if (revision !== sequence) continue;
        clear(); status.state = 'error'; status.message = String(error); status.revision = revision;
        overlay.show('VGA preview error', status.message);
      }
    }
  } finally { compiling = false; }
}

function animate(now: number) {
  requestAnimationFrame(animate);
  if (!active || document.hidden || !mod || compiling) return;
  try {
    fps.update(now);
    if (audio) audio.enablePerTickUpdate = audio.needsFeeding;
    pixels.fill(0);
    renderVGAFrame(mod, pixels, { polarity, onTick: () => audio?.update(), onLine: () => inputs.updateGamepadPmod() });
    ctx.putImageData(frame, 0, 0);
    // Bound synchronization even when user RTL does not produce a valid signal.
    for (const high of [true, false]) {
      let ticks = 0;
      while (decodeVGAOutput(mod.state.uo_out, polarity).vsync !== high && ticks++ < 10000) {
        mod.tick2(1); audio?.update();
      }
    }
    status.frames++;
    document.getElementById('fps-count')!.textContent = fps.getFPS().toFixed(0);
    document.getElementById('audio-latency-display')!.style.display = audio?.isRunning() ? '' : 'none';
    document.getElementById('audio-latency-ms')!.textContent = (audio?.latencyMs ?? 0).toFixed(0);
  } catch (error) {
    clear(); status.state = 'error'; status.message = String(error);
    overlay.show('Simulation error', status.message);
  }
}

const bridge = {
  presets: examples.map(example => ({ ...example, topModule: detectTopModule(example.sources), licenses: {
    'VGA-PRESET-LICENSE.txt': apacheLicense, 'VGA-COMMON-LICENSE.txt': commonLicense,
  }})),
  status,
  setProject(project: Inputs) { sequence++; pending = project; void compilePending(); },
  setActive(value: boolean) { active = value; if (!value) suspendAudio(); },
  invalidate(message: string) {
    sequence++; pending = null; clear(); status.state = 'error'; status.message = message;
    overlay.show('VGA preview', message);
  },
};
(window as unknown as { icstudioVga: typeof bridge }).icstudioVga = bridge;
overlay.show('VGA Playground', status.message);
document.addEventListener('visibilitychange', () => { if (document.hidden) suspendAudio(); });
requestAnimationFrame(animate);
