"""Plot measured pass-1/pass-2 results; requires matplotlib.

python scripts/plot_gf180_banba_pass2.py /path/to/verification/results /path/to/performance.png
"""
import argparse
import json
from pathlib import Path


def plot(results, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    results = Path(results)
    report = json.loads((results/'validation.json').read_text())
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11, 'axes.spines.top':False,
                         'axes.spines.right':False, 'axes.titleweight':'bold'})
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    colors = ['#64748b', '#007f78']
    for key, label, color in zip(['first_pass','second_pass'], ['First pass','Second pass'], colors):
        data = report['comparison'][key]
        transient = json.loads((results/key/'startup/result.json').read_text())
        axes[0,0].semilogx([t*1e6 for t in transient['x']], transient['traces']['vref'], color=color, label=label, lw=2)
        temperatures = data['temperature']
        axes[0,1].plot([v['temperature'] for v in temperatures], [v['vref']*1e3 for v in temperatures],
                        'o-', color=color, lw=2, ms=4, label=label)
        axes[1,0].plot([v['temperature'] for v in temperatures], [v['supply_current']*1e6 for v in temperatures],
                        'o-', color=color, lw=2, ms=4, label=label)
        axes[1,1].semilogx(data['psrr']['frequency'], data['psrr']['rejection_db'], color=color, lw=2, label=label)
    axes[0,0].axhline(.75, color='#b45309', lw=1, ls='--', label='Startup ceiling: 0.75 V')
    axes[0,0].set(xlim=(.5,500), ylim=(0,2.9), xlabel='Time from simulation start (µs)', ylabel='VREF (V)',
                  title='Power-on overshoot falls; settling slows')
    axes[0,0].legend(frameon=False, fontsize=9, loc='upper right')
    axes[0,1].axhline(600, color='#b45309', lw=1, ls='--')
    axes[0,1].set(xlabel='Temperature (°C)', ylabel='VREF (mV)', title='Reference retuned toward 600 mV')
    axes[1,0].set(xlabel='Temperature (°C)', ylabel='Supply current (µA)', ylim=(0,None), title='Lower amplifier and startup bias')
    axes[1,1].set(xlabel='Frequency (Hz)', ylabel='Supply rejection (dB)', title='Small-signal supply rejection')
    for ax in axes.flat:
        ax.grid(True, color='#e2e8f0', linewidth=.7)
        ax.set_axisbelow(True)
    fig.suptitle('GF180MCU Banba bandgap · second schematic pass', x=.07, ha='left', y=.98, fontsize=20, weight='bold')
    fig.text(.07,.932,'ngspice 42 · nominal process · 3.3 V · 5 pF external load · startup: 100 ns edge after 1 µs', color='#475569')
    fig.text(.07,.025,'Simulated schematic data. No mismatch, extracted-layout or formal loop-gain qualification.', color='#475569', fontsize=10)
    fig.tight_layout(rect=(.025,.045,.99,.915), h_pad=2.8, w_pad=3)
    fig.savefig(destination, dpi=160, facecolor='white')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results')
    parser.add_argument('destination')
    args = parser.parse_args()
    plot(args.results, args.destination)
