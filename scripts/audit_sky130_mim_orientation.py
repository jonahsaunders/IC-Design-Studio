"""Independent re-read of rectangular MiM masks, native records and AC data.

No application, generator, normalizer, qualifier or application raw parser is
imported. Bottom-metal extension independently establishes the expected axis.
"""
import argparse,hashlib,json,math,re,shlex,struct,xml.etree.ElementTree as ET
from pathlib import Path
import klayout.db as db

sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
MODEL='sky130_fd_pr__cap_mim_m3_2'


def regions(path):
    ly=db.Layout();ly.read(str(path));assert ly.dbu==.001
    c=ly.top_cell();assert c is not None and not any(c.each_inst())
    return {(ly.get_info(i).layer,ly.get_info(i).datatype):db.Region([s.polygon for s in c.shapes(i).each() if not s.is_text()]).merged() for i in ly.layer_indexes()}


def raw(path):
    data=path.read_bytes().replace(b'\r\n',b'\n') if b'Values:' in path.read_bytes() else path.read_bytes()
    marker=b'Values:\n' if b'Values:\n' in data else b'Binary:\n'
    header,values=data.split(marker,1);text=header.decode()
    points=int(re.search(r'No\. Points:\s+(\d+)',text)[1]);assert points==8
    assert re.search(r'Flags:\s+complex\s*$',text,re.M)
    names=[line.split()[1].lower() for line in text.split('Variables:\n',1)[1].splitlines() if line.strip()]
    n=len(names);assert n==int(re.search(r'No\. Variables:\s+(\d+)',text)[1]) and len(set(names))==n
    if marker==b'Values:\n':
        tokens=[line.split() for line in values.decode().splitlines() if line.strip()]
        assert len(tokens)==n*points
        for i in range(points):assert tokens[i*n][0]==str(i)
        numbers=[complex(*map(float,t[-1].split(','))) for t in tokens]
    else:
        assert len(values)==16*n*points
        numbers=[complex(*struct.unpack_from('<dd',values,16*i)) for i in range(n*points)]
    result=[dict(zip(names,numbers[i*n:(i+1)*n])) for i in range(points)]
    for i,row in enumerate(result):
        assert math.isclose(row['frequency'].real,1000*10**i,rel_tol=1e-12)
        # The frequency's imaginary slot is unused by ngspice.
        assert all(math.isfinite(abs(v)) for k,v in row.items() if k!='frequency')
    return result


def normalization(folder,size):
    w,l,count=size;masks=regions(folder/'layout.gds');caps=list(masks[(97,44)].each())
    assert len(caps)==count
    axes=[]
    for cap in caps:
        b=cap.bbox();assert cap.is_box()
        bottoms=[p for p in masks[(71,20)].each() if (db.Region(cap)-db.Region(p)).is_empty()]
        assert len(bottoms)==1;bottom=bottoms[0].bbox()
        extra=(bottom.width()-b.width(),bottom.height()-b.height())
        assert sorted(extra)==[1000,4500]
        axis=0 if extra[0]>extra[1] else 1
        dimensions=[b.width()/1000,b.height()/1000]
        if axis==1:dimensions.reverse()
        assert dimensions==[w,l];axes.append((b,axis))
    extraction=folder/'lvs-extraction'
    if w==l:
        assert not (extraction/'mim-orientation.json').exists();return count
    proof=load(extraction/'mim-orientation.json');before=extraction/'native-original.ext';after=extraction/'device_coupon.ext'
    assert proof['native_sha256']==sha(before) and proof['corrected_sha256']==sha(after) and proof['gds_sha256']==sha(folder/'layout.gds')
    scale=proof['native_coordinate_nm'];assert scale in (5,10)
    seen=set();expected=[]
    for line in before.read_text().splitlines(keepends=True):
        if line.startswith('device csubckt '+MODEL+' '):
            t=shlex.split(line);site=db.Box(*(int(v)*scale for v in t[3:7]))
            matches=[(i,b,axis) for i,(b,axis) in enumerate(axes) if b.contains(site.p1) and b.contains(site.p2)]
            assert len(matches)==1;i,b,axis=matches[0];assert i not in seen;seen.add(i)
            assert [float(t[7][2:])*scale,float(t[8][2:])*scale]==[b.width(),b.height()]
            if axis:line=re.sub(r'\bw=(\S+)(\s+)l=(\S+)',lambda m:'w='+m[3]+m[2]+'l='+m[1],line)
        expected.append(line)
    assert len(seen)==count and ''.join(expected)==after.read_text()
    return count


def audit(root):
    record=load(root/'record.json');assert record['status']=='PASS' and record['source_unchanged']
    expected=((2,10,1),(10,2,1),(3.005,5.005,1),(2,30,1),(30,2,1),(2,10,3),(2,10,16),(2,2,1))
    assert len(record['cases'])==8 and {tuple(c['size']) for c in record['cases']}==set(expected)
    counts=dict(layouts=0,capacitors=0,faults=0,streams=0,integrity_bindings=0,raw_responses=0,ac_samples=0,swapped_resistance_faults=0)
    def verify(folder,status):
        report=load(folder/'report.json');assert report['status']==status
        stages={s['name']:s for s in report['stages']}
        for name,digest in stages['integrity'].get('evidence',{}).get('files',{}).items():
            path=(folder/name).resolve();assert path.is_relative_to(folder.resolve()) and sha(path)==digest;counts['integrity_bindings']+=1
        return report,stages
    for i,size in enumerate(expected):
        folder=root/str(i);case=load(folder/'record.json');assert case in record['cases'] and case['status']=='PASS' and tuple(case['size'])==size
        w,l,count=size;assert {v['name'] for v in case['layouts']}=={f'{a}-{m}' for a in (0,90,180,270) for m in ('plain','mirror')}
        for row in case['layouts']:
            name=row['name'];dest=folder/f'valid-{name}';assert sha(dest/'report.json')==row['report_sha256']
            report,stages=verify(dest,'passed');assert report['drc_count']==0 and all(v['status']=='passed' for v in report['stages'])
            assert not ET.parse(dest/'public-drc/report.lyrdb').findall('.//items/item')
            counts['capacitors']+=normalization(dest,size)
            text=re.sub(r'\n\s*\+\s*',' ',(dest/'lvs-extraction/extracted.spice').read_text())
            lines=[v.split() for v in text.splitlines() if v.strip() and not v.lstrip().startswith('*')]
            assert lines[0]==['.subckt','device_coupon','P','N'] and lines[-1]==['.ends']
            copies=0
            for fields in lines[1:-1]:
                assert fields[0].startswith('X') and fields[1:4]==['P','N',MODEL]
                params=dict(t.split('=',1) for t in fields[4:]);assert set(params)<={'w','l','m'}
                assert float(params['w'])==w and float(params['l'])==l;copies+=float(params.get('m',1))
            assert copies==count
            masks=regions(folder/f'input-{name}.gds')
            for suffix in ('gds','oas'):
                other=regions(folder/f'roundtrip-{name}.{suffix}')
                assert all((masks.get(k,db.Region())^other.get(k,db.Region())).is_empty() for k in masks.keys()|other.keys());counts['streams']+=1
            counts['layouts']+=1
        assert {(v['corner'],v['temperature_C']) for v in case['measurements']}=={('nominal',27),('ss',0),('ff',85)}
        for row in case['measurements']:
            path=folder/f'electrical-{row["corner"]}-{row["temperature_C"]}/probe.raw';assert sha(path)==row['raw_sha256']
            samples=raw(path);assert len(row['samples'])==len(samples)
            for d,saved in zip(samples,row['samples']):
                phases=('schematic','extracted','independent','swapped') if w!=l else ('schematic','extracted','independent')
                values={k:-d['i(vp_'+k+')'] for k in phases};resistance={k:(1/v).real for k,v in values.items()}
                for k,v in values.items():
                    assert v.imag>0 and resistance[k]>0
                    assert abs(complex(*saved['admittance_S'][k])/v-1)<1e-12
                    assert math.isclose(saved['series_resistance_ohm'][k],resistance[k],rel_tol=1e-12)
                assert all(abs(values[k]/values['independent']-1)<=1e-6 and abs(resistance[k]/resistance['independent']-1)<=1e-6 for k in ('schematic','extracted'))
                counts['ac_samples']+=1
            if w!=l:
                assert abs(resistance['swapped']/resistance['independent']-1)>=.05;counts['swapped_resistance_faults']+=1
            counts['raw_responses']+=1
        faults={'dielectric-missing','top-open','bottom-open','reference-width','reference-count'}|({'reference-swapped'} if w!=l else set())
        assert {v['name'] for v in case['faults']}==faults
        for row in case['faults']:
            dest=folder/row['name'];assert sha(dest/'report.json')==row['report_sha256'];report,stages=verify(dest,'failed')
            assert stages['preflight']['status']=='passed' and stages['layout_export']['status']=='passed'
            masks=regions(dest/'layout.gds');extraction=dest/'lvs-extraction'
            if row['name']=='bottom-open' and w!=l:
                assert (masks[(71,44)]-masks[(97,44)]).is_empty()
                assert stages['lvs_extraction']['status']=='failed' and 'bottom contacts on exactly one axis' in report['error']
                assert not (extraction/'extracted.spice').exists() and not (extraction/'native-original.ext').exists()
                assert 'STUDIO_MAGIC_COMPLETE' in (extraction/'native-extraction.log').read_text()
            elif stages['lvs_extraction']['status']=='passed':
                assert stages['lvs']['status']=='failed' and re.search(r'netlists do not match|circuits do not match|property errors|failed pin matching',(dest/'lvs/lvs.log').read_text(),re.I)
            else:
                assert row['name']=='dielectric-missing' and masks.get((97,44),db.Region()).is_empty()
                assert 'sky130_fd_pr__cap_mim_m3_2' not in (extraction/'extracted.spice').read_text()
                assert 'Extracted port order differs' in report['error']
            counts['faults']+=1
    assert counts['layouts']==64 and counts['capacitors']==200 and counts['faults']==47 and counts['raw_responses']==24
    return dict(status='PASS',counts=counts,record_sha256=sha(root/'record.json'),audit_sha256=sha(__file__),scope=__doc__)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();result=audit(a.root)
    a.output.write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result,indent=2))


if __name__=='__main__':main()
