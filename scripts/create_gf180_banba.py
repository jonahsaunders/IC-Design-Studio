"""Build the editable, schematic-first GF180MCU Banba example.

Run from the repository root: python scripts/create_gf180_banba.py
The sizing is a starting point, not a process-qualified reference.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import example, device, clone, uid, digest, validate, save_project, erc
from icstudio.catalog import create_device, link_technology
from icstudio.interchange import pin_positions, spice
from icstudio.wiring import rebuild, graph
from icstudio import analog_optimizer as opt

OUT = ROOT / 'examples/gf180-banba'


def build():
    manifest = json.loads((ROOT / 'icstudio/assets/pdks/gf180mcuD/package.json').read_text())
    tech = clone(manifest['technology'])
    tech['package_root'] = str(ROOT / 'icstudio/assets/pdks/gf180mcuD')
    tech['package_lock'] = dict(id=manifest['id'], revision=manifest['revision'],
                               manifest_hash=digest(manifest), files=manifest['files'])
    p = example('empty'); link_technology(p, tech)
    p['name'] = 'GF180MCU Banba bandgap — schematic starting point'
    p['parameters'] = dict(vdd='3.3', mirror_w='8u', mirror_l='4u', pair_w='24u', pair_l='2u')
    p['cells'] = []
    intended = {}

    def cell(name, ports=()):
        c = dict(id=uid(), name=name, ports=list(ports), devices=[], shapes=[], wires=[], labels=[], annotations=[])
        p['cells'].append(c)
        return c

    def note(c, x, y, text):
        c['annotations'].append(dict(id=uid(), x=x, y=y, text=text))

    def add(c, d, nets):
        d['nets'] = dict(nets)
        intended[d['id']] = dict(nets)
        c['devices'].append(d)
        return d

    def pdk(c, model, name, x, y, nets, **params):
        d = create_device(tech, 'symbols/' + model + '.sym', name, x, y)
        # Native canvas supplies the name/model; retain the actual PDK artwork.
        d['symbol']['primitives'] = [s for s in d['symbol']['primitives'] if s['kind'] != 'text']
        if d['kind'] in ('NMOS', 'PMOS'):
            d['params'].update(w=params.pop('w'), l=params.pop('l'))
        else:
            text = 'm=@m' if model.startswith('pnp') else 'W=@w  L=@l'
            d['symbol']['primitives'].append(dict(kind='text', points=[[37, 5], [57, 15]], text=text, font_size=9))
        d['model_params'].update(params)
        return add(c, d, nets)

    def mos(c, name, pol, x, y, d, g, s, b, w, l):
        return pdk(c, pol + 'fet_03v3', name, x, y, dict(d=d, g=g, s=s, b=b), w=w, l=l)

    def resistor(c, name, x, y, a, b, length):
        return pdk(c, 'ppolyf_u_1k', name, x, y, dict(p=a, m=b, b='VSS'), w='1u', l=length)

    def cap(c, name, x, y, a, b, side):
        return pdk(c, 'cap_mim_analog', name, x, y, dict(g=a, b=b), w=side, l=side)

    def label(c, name, point, offset=(7, -16)):
        c['labels'].append(dict(id=uid(), kind='ground' if name == '0' else 'net_label', name=name,
            anchor=dict(kind='point', point=list(point)), offset=list(offset), rotation=0))

    def wire(c, net, *points, labelled=False):
        pts = [list(pt) for pt in points]
        assert all(a[0] == b[0] or a[1] == b[1] for a, b in zip(pts, pts[1:]))
        c['wires'].append(dict(id=uid(), points=pts, net=net))
        if labelled: label(c, net, pts[0])

    def pin(d, name): return pin_positions(d)[name]

    def tie(c, d, a, e, b, *via):
        net = intended[d['id']][a]
        assert net == intended[e['id']][b]
        wire(c, net, pin(d, a), *via, pin(e, b), labelled=True)

    def finish(c):
        # Explicit labels preserve disconnected sections, with a physical stub
        # for every remaining terminal. Rebuilding must reproduce the design.
        groups = graph(c, p, labels=False)
        seen = set(); unique = []
        for item in c['labels']:
            root = groups[('label', item['id'])]
            if root not in seen: unique.append(item); seen.add(root)
        c['labels'] = unique
        attached = {groups[('label', l['id'])] for l in c['labels']}
        for d in c['devices']:
            for name, xy in pin_positions(d).items():
                root = groups[(d['id'], name)]
                if root in attached: continue
                net = intended[d['id']][name]
                sx, sy = d.get('symbol', {}).get('pins', {}).get(name, (0, 0))
                dx, dy = (-45, 0) if sx < 0 else (0, -40) if sy < 0 else (0, 40) if sy > 0 else (75, 0)
                end = [xy[0]+dx, xy[1]+dy]
                wire(c, net, xy, end)
                label(c, net, end, (-35, -18) if dx < 0 else (5, 12) if dx > 0 else (5, -16))
                attached.add(root)
        rebuild(c, p)
        for d in c['devices']:
            assert d['nets'] == intended[d['id']], (c['name'], d['name'], d['nets'], intended[d['id']])

    def block(c, pins, text, triangle=False):
        c['symbol'] = dict(pins={k:list(v) for k,v in pins.items()}, pin_order=c['ports'],
            pin_meta={n:dict(direction='inout', role='analog', label_visible=True) for n in c['ports']},
            primitives=[dict(kind='polygon', points=[[-60,-60],[-60,60],[60,0]]) if triangle else
                        dict(kind='rect', points=[[-60,-60],[60,60]])])
        for n, (x,y) in pins.items():
            edge = 30 if triangle else 60
            ex, ey = (x, -edge if y < 0 else edge) if x == 0 else (-60 if x < 0 else 60, y)
            c['symbol']['primitives'].append(dict(kind='line', points=[[x,y],[ex,ey]]))
        c['symbol']['primitives'].append(dict(kind='text', points=[[-44,-12],[-24,-2]], text=text, font_size=11))
        if triangle:
            for y,t in [(-32,'−'),(20,'+')]:
                c['symbol']['primitives'].append(dict(kind='text', points=[[-52,y],[-32,y+10]], text=t, font_size=14))

    def instance(c, child, name, x, y, nets):
        return add(c, device('X', name, x, y, cell=child['id'], symbol=clone(child['symbol'])), nets)

    core = cell('banba_core', ['VDD','VSS','VREF'])
    ota = cell('error_amplifier', ['VA','VB','OUT','VDD','VSS'])
    start = cell('startup', ['CTRL','VDD','VSS'])
    block(ota, dict(VA=(-80,-25), VB=(-80,25), OUT=(80,0), VDD=(0,-80), VSS=(0,80)), 'OTA', True)
    block(start, dict(CTRL=(80,0), VDD=(0,-80), VSS=(0,80)), 'START')
    block(core, dict(VREF=(100,0), VDD=(0,-80), VSS=(0,80)), 'BANBA')

    note(core, 40, 0, 'BANBA CURRENT-MODE CORE\nGF180MCU · 3.3 V · target about 0.6 V')
    note(core, 430, 0, 'Equal branch currents, VA = VB.\nQ2 has eight identical PNP units.\nRCA and RCB must stay matched.')
    note(core, 820, 0, 'Starting sizes; not yet PVT qualified.\nMirror W/L = 8/4 µm; poly W = 1 µm.\nAll bodies/substrates explicitly tied.')
    m1=mos(core,'MP1','p',180,200,'VA','CTRL','VDD','VDD','{mirror_w}','{mirror_l}')
    m2=mos(core,'MP2','p',540,200,'VB','CTRL','VDD','VDD','{mirror_w}','{mirror_l}')
    m3=mos(core,'MP3','p',900,200,'VREF','CTRL','VDD','VDD','{mirror_w}','{mirror_l}')
    for m in (m1,m2,m3):
        x=pin(m,'s')[0]; wire(core,'VDD',pin(m,'s'),(x,110))
        wire(core,'VDD',pin(m,'b'),(x+25,200),(x+25,110))
    wire(core,'VDD',(200,110),(945,110),labelled=True)
    ra=resistor(core,'RCA',100,480,'VA','VSS','100u')
    rb=resistor(core,'RCB',440,480,'VB','VSS','100u')
    rp=resistor(core,'RPTAT',580,430,'VB','VE2','11u')
    ro=resistor(core,'ROUT',920,530,'VREF','VSS','50u')
    q1=pdk(core,'pnp_05p00x05p00','Q1',220,620,dict(c='VSS',b='VSS',e='VA'),m='1')
    q2=pdk(core,'pnp_05p00x05p00','Q2',560,620,dict(c='VSS',b='VSS',e='VE2'),m='8')
    tie(core,m1,'d',q1,'e',(200,310),(240,310))
    tie(core,m1,'d',ra,'p',(200,310),(100,310))
    tie(core,m2,'d',rp,'p',(560,310),(580,310))
    tie(core,m2,'d',rb,'p',(560,310),(440,310))
    tie(core,rp,'m',q2,'e')
    tie(core,m3,'d',ro,'p')
    for q in (q1,q2):
        x,y=pin(q,'b');tie(core,q,'b',q,'c',(x-20,y),(x-20,y+60),(x+40,y+60))
        core['labels'][-1]['anchor']['point']=[x-20,y+60]
        core['labels'][-1]['offset']=[-38,12]
    instance(core,ota,'XAMP',710,790,dict(VA='VA',VB='VB',OUT='CTRL',VDD='VDD',VSS='VSS'))
    instance(core,start,'XSTART',300,800,dict(CTRL='CTRL',VDD='VDD',VSS='VSS'))
    note(core,920,735,'Ibranch ≈ VBE/RCA + ΔVBE/RPTAT\nVREF ≈ ROUT × Ibranch\nΔVBE ≈ VT × ln(8)\n\nScreened sizes: 100k / 11k / 50k.\nUse model results for actual values.')
    finish(core)

    note(ota,40,0,'TWO-STAGE ERROR AMPLIFIER\nPMOS input pair for low common mode.\nVA rising relative to VB lowers OUT.')
    note(ota,430,0,'Independent resistor bias starts at VDD.\nPBIAS: 4/4 µm; tail: 8/4 µm.\nInput pair: 24/2 µm, matched.')
    note(ota,830,0,'Second stage reaches the PMOS gates.\nMIM Miller capacitor ≈ 2 pF.\nLoop stability still requires verification.')
    mb=mos(ota,'MPBIAS','p',120,180,'PBIAS','PBIAS','VDD','VDD','4u','4u')
    rbi=resistor(ota,'RBIAS',140,430,'PBIAS','VSS','250u')
    mt=mos(ota,'MPTAIL','p',470,180,'TAIL','PBIAS','VDD','VDD','8u','4u')
    mi1=mos(ota,'MPA','p',310,370,'NMIR','VA','TAIL','VDD','{pair_w}','{pair_l}')
    mi2=mos(ota,'MPB','p',610,370,'GAIN','VB','TAIL','VDD','{pair_w}','{pair_l}')
    mn1=mos(ota,'MNA','n',310,560,'NMIR','NMIR','VSS','VSS','4u','2u')
    mn2=mos(ota,'MNB','n',610,560,'GAIN','NMIR','VSS','VSS','4u','2u')
    ml=mos(ota,'MPLOAD','p',960,180,'OUT','PBIAS','VDD','VDD','4u','8u')
    mo=mos(ota,'MNOUT','n',960,560,'OUT','GAIN','VSS','VSS','4u','2u')
    cm=cap(ota,'CMILLER',815,420,'GAIN','OUT','31.62u')
    tie(ota,mb,'d',rbi,'p')
    tie(ota,mb,'g',mb,'d',(80,180),(80,260),(140,260))
    tie(ota,mt,'d',mi1,'s',(490,290),(330,290))
    tie(ota,mt,'d',mi2,'s',(490,290),(630,290))
    tie(ota,mi1,'d',mn1,'d')
    tie(ota,mi2,'d',mn2,'d')
    tie(ota,mn1,'g',mn1,'d',(270,560),(270,480),(330,480))
    tie(ota,ml,'d',mo,'d')
    finish(ota)

    note(start,40,0,'CURRENT-SENSE STARTUP\nNo core current → KICK rises.\nMNKICK pulls CTRL down to start MP1–3.')
    note(start,430,0,'Core current → DET rises → KICK falls.\nMSENSE is a 1:1 copy of a core PMOS.\nCheck release and slow-ramp behavior.')
    ms=mos(start,'MSENSE','p',140,190,'DET','CTRL','VDD','VDD','{mirror_w}','{mirror_l}')
    rd=resistor(start,'RDET',160,400,'DET','VSS','100u')
    ru=resistor(start,'RPULL',460,190,'VDD','KICK','500u')
    ns=mos(start,'MNSENSE','n',440,470,'KICK','DET','VSS','VSS','8u','1u')
    nk=mos(start,'MNKICK','n',760,470,'CTRL','KICK','VSS','VSS','2u','2u')
    tie(start,ms,'d',rd,'p')
    tie(start,ru,'m',ns,'d')
    finish(start)

    benches=[]
    for name,pulse in [('tb_dc',False),('tb_startup',True)]:
        c=cell(name);benches.append(c)
        note(c,50,0,'BANBA BANDGAP TESTBENCH\nGF180MCU · 3.3 V nominal · 27 °C\nOpen banba_core to edit the circuit.')
        note(c,470,0,('Startup from an unpowered state.\n0 → 3.3 V after 1 µs; 100 ns edge.\nRun 500 µs and inspect CTRL / VREF.' if pulse else
                           'Saved OP and supply-sweep analyses.\nTemperature plan: −40 / 27 / 125 °C.\n5 pF output load; no output buffer.'))
        v=add(c,device('V','VDD',130,300,value='{vdd}'),dict(p='VDD',n='0'))
        v['source']['ac']='0'
        if pulse:v['source'].update(type='pulse',low='0',high='{vdd}',delay='1u',period='10m',duty='0.5')
        dut=instance(c,core,'XDUT',450,300,dict(VDD='VDD',VSS='0',VREF='VREF'))
        cl=add(c,device('C','CLOAD',720,300,value='5p'),dict(p='VREF',n='0'))
        tie(c,v,'p',dut,'VDD',(130,170),(450,170))
        tie(c,dut,'VREF',cl,'p',(600,300),(600,200),(720,200))
        tie(c,v,'n',dut,'VSS',(130,440),(450,440))
        tie(c,dut,'VSS',cl,'n',(450,440),(720,440))
        finish(c)
        c['specifications']=[dict(name='Reference initial window',expression='final(V("VREF"))',unit='V',min='.5',max='.7')]
        if pulse:
            c['specifications'].append(dict(name='Startup overshoot limit', expression='max(V("VREF"))', unit='V', max='.75'))
    dc,tran=benches;p['top']=dc['id']
    p['analysis'].update(type='op',engine='ngspice',corner='nominal',temperature=27)
    op=clone(p['analysis']); ts={**op,'type':'tran','step':'100n','stop':'500u'}
    supply={**op,'type':'dc','source':'VDD','dc_start':'2.7','dc_stop':'3.6','dc_step':'.05'}
    p['simulation_setups']=[dict(name='Banba operating point',cell=dc['id'],engine='ngspice',settings=op),
        dict(name='Banba power-on startup',cell=tran['id'],engine='ngspice',settings=ts),
        dict(name='Banba supply sweep',cell=dc['id'],engine='ngspice',settings=supply)]
    entry=dict(id='setup:0',name='Banba operating point',cell=dc['id'],engine='ngspice',settings=op,supply='VDD.value')
    plan=dict(id='banba_temperature',name='Banba temperature screening',entries=[entry],corners=['nominal'],temperatures=[-40,27,125],voltages=[])
    p['test_plans']=[plan]
    p['design_notes']={'stage':'Initial transistor-level schematic. Requires analog validation and optimization.',
        'topology_reference':'https://doi.org/10.1109/4.760378',
        'assumptions':'3.3 V nominal, about 0.6 V unloaded output, 1:8 PNP ratio, 5 pF bench load.',
        'known_issue':'Fast power-on overshoot exceeds 0.75 V; startup is not qualified.'}
    validate(p)
    issues=erc(p,dc['id'])+erc(p,tran['id'])
    assert not issues, issues
    spec=dict(kind='analog_optimizer',name='Banba resistor-ratio screening',strategy='grid',budget=81,
        axes=[dict(target='RPTAT.model_params.l',lower='9u',upper='11u',count=3),
              dict(target='ROUT.model_params.l',lower='46u',upper='50u',count=3)],
        objective=dict(entry_id='setup:0',expression='final(V("VREF"))',unit='V',goal='target',target='.6'))
    opt.grid(p,core['id'],spec['axes'])
    return p,core['id'],spec


if __name__ == '__main__':
    p,cid,spec=build();OUT.mkdir(parents=True,exist_ok=True)
    # Relative root is resolved by load_project(), so a checkout can move.
    p['pdk']['package_root']='../../icstudio/assets/pdks/gf180mcuD'
    save_project(p,OUT/'banba.icproj')
    (OUT/'optimizer.json').write_text(json.dumps(dict(cell='banba_core',plan='banba_temperature',spec=spec),indent=2)+'\n')
    print('Created',OUT/'banba.icproj')
