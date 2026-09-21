// SPDX-License-Identifier: GPL-3.0-or-later
import { readFileSync } from 'node:fs';
import { afterAll, beforeAll, expect, test, vi } from 'vitest';
import { compileVerilator } from './verilator/compile';
import { HDLModuleWASM } from './sim/hdlwasm';
import { detectTopModule } from './verilog';
import { examples } from './examples';
import { detectSyncPolarity, renderVGAFrame, resetModule, VGA_HEIGHT, VGA_WIDTH } from './sim/vga';

const wasmBinary = readFileSync(new URL('./verilator/verilator_bin.wasm', import.meta.url));
const exit = process.exit;
beforeAll(() => {
  process.setMaxListeners(100);
  process.exit = vi.fn(() => { throw new Error('Verilator exited'); }) as typeof process.exit;
});
afterAll(() => { process.exit = exit; });

test('Studio include directories, nested paths, explicit top and defines reach the compiler', async () => {
  const result = await compileVerilator({topModule: 'custom_top', wasmBinary,
    includeDirs: ['include'], defines: { VALUE: '23' }, sources: {
      'rtl/top.sv': '`include "defs.svh"\nmodule custom_top(output wire [7:0] value); assign value = `VALUE + `OFFSET; endmodule',
      'include/defs.svh': '`define OFFSET 4\n',
    }});
  expect(result.output, JSON.stringify(result.errors)).toBeDefined();
  const mod = new HDLModuleWASM(result.output!.modules.TOP, result.output!.modules['@CONST-POOL@']);
  try { await mod.init(); mod.powercycle(); mod.eval(); expect(mod.state.value).toBe(27); }
  finally { mod.dispose(); }
});

test.each(examples)('Studio can compile and render the $name preset', async example => {
  const result = await compileVerilator({topModule: detectTopModule(example.sources), sources: example.sources, wasmBinary});
  expect(result.output, JSON.stringify(result.errors)).toBeDefined();
  const mod = new HDLModuleWASM(result.output!.modules.TOP, result.output!.modules['@CONST-POOL@']);
  try {
    mod.getFileData = path => example.dataFiles?.[path];
    await mod.init(); resetModule(mod); const polarity = detectSyncPolarity(mod); resetModule(mod);
    const pixels = new Uint8Array(VGA_WIDTH * VGA_HEIGHT * 4);
    renderVGAFrame(mod, pixels, {polarity});
    expect(pixels.some((value, i) => i % 4 === 3 && value === 255)).toBe(true);
  } finally { mod.dispose(); }
}, 20000);
