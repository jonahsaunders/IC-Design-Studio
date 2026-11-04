"""Re-read saved native graphs, masks, raw responses and integrity bindings.

This audit does not import the generator, qualification runner or raw parser.
"""
import argparse,hashlib,json,math,re,struct,xml.etree.ElementTree as ET
from pathlib import Path
import klayout.db as db

sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())

def regions(path):
    ly=db.Layout();ly.read(str(path));assert ly.dbu==.001
    c=ly.top_cell();assert c is not None and not any(c.each_inst())
    return {(ly.get_info(i).layer,ly.get_info(i).datatype):db.Region([s.polygon for s in c.shapes(i).each() if not s.is_text()]).merged() for i in ly.layer_indexes()}

def raw(path):
    data=path.read_bytes();marker=b'Values:\n' if b'Values:\n' in data else b'Binary:\n'
    header,values=data.split(marker,1);text=header.decode()
    assert re.search(r'No\. Points:\s+1\s*$',text,re.M)
    assert re.search(r'Flags:\s+complex\s*$',text,re.M)
    names=[line.split()[1].lower() for line in text.split('Variables:\n',1)[1].splitlines() if line.strip()]
    assert len(names)==int(re.search(r'No\. Variables:\s+(\d+)',text)[1]) and len(set(names))==len(names)
    if marker==b'Values:\n':
        tokens=[line.split() for line in values.decode().splitlines() if line.strip()]
        assert len(tokens)==len(names) and tokens[0][0]=='0'
        numbers=[complex(*map(float,t[-1].split(','))) for t in tokens]
    else:
        assert len(values)==16*len(names)
        numbers=[complex(*struct.unpack_from('<dd',values,16*i)) for i in range(len(names))]
    assert all(math.isfinite(abs(v)) for v in numbers)
    return dict(zip(names,numbers))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();record=load(a.root/'record.json');assert record['status']=='PASS' and record['source_unchanged']
    expected=((2,2,1),(5,5,1),(10,10,1),(3.005,3.005,1),(30,30,1),(2,2,3),(2,2,16))
    assert len(record['cases'])==7 and {tuple(c['size']) for c in record['cases']}==set(expected)
    counts=dict(layouts=0,capacitors=0,faults=0,streams=0,integrity_bindings=0,early_interface_rejections=0,raw_responses=0)
    def verify(folder,status):
        report=load(folder/'report.json');assert report['status']==status
        stages={s['name']:s for s in report['stages']}
        if stages['integrity']['status']!='passed':
            # Lost ports abort before the later integrity stage. Do not claim
            # that unrun stage passed; re-read the native short explicitly below.
            assert status=='failed' and stages['integrity']['status']=='not_run'
            assert stages['lvs_extraction']['status']=='failed' and 'Extracted port order differs' in stages['lvs_extraction']['error']
            assert stages['lvs']['status']=='not_run';counts['early_interface_rejections']+=1
        for name,digest in stages['integrity'].get('evidence',{}).get('files',{}).items():
            path=(folder/name).resolve();assert path.is_relative_to(folder.resolve()) and sha(path)==digest
            counts['integrity_bindings']+=1
        return report,stages
    for i,size in enumerate(expected):
        folder=a.root/str(i);case=load(folder/'record.json');assert case in record['cases'] and case['status']=='PASS' and tuple(case['size'])==size
        w,l,count=size;assert {v['angle'] for v in case['layouts']}=={0,90,180,270}
        for row in case['layouts']:
            angle=row['angle'];dest=folder/f'valid-{angle}';assert sha(dest/'report.json')==row['report_sha256']
            report,stages=verify(dest,'passed');assert report['drc_count']==0 and all(v['status']=='passed' for v in report['stages'])
            assert not ET.parse(dest/'public-drc/report.lyrdb').findall('.//items/item')
            netlist=(dest/'lvs-extraction/extracted.spice').read_text();lines=[v.split() for v in netlist.splitlines() if v.strip() and not v.lstrip().startswith('*')]
            assert lines[0]==['.subckt','device_coupon','P','N'] and lines[-1]==['.ends']
            copies=0
            for fields in lines[1:-1]:
                assert fields[0].startswith('X') and fields[1:4]==['P','N','sky130_fd_pr__cap_mim_m3_2']
                params=dict(t.split('=',1) for t in fields[4:]);assert set(params)<= {'w','l','m'}
                assert math.isclose(float(params['w']),w,abs_tol=1e-8) and math.isclose(float(params['l']),l,abs_tol=1e-8)
                copies+=float(params.get('m',1))
            assert copies==count
            masks=regions(folder/f'input-{angle}.gds');caps=masks[(97,44)]
            assert caps.count()==count
            for cap in caps.each():
                b=cap.bbox();assert cap.is_box() and b.width()==round(w*1000) and b.height()==round(l*1000)
            assert (caps.sized(140)-masks[(71,20)]).is_empty()
            for cut in masks[(71,44)].each():
                b=cut.bbox();assert cut.is_box() and (b.width(),b.height())==(800,800)
            for suffix in ('gds','oas'):
                other=regions(folder/f'roundtrip-{angle}.{suffix}')
                assert all((masks.get(k,db.Region())^other.get(k,db.Region())).is_empty() for k in masks.keys()|other.keys());counts['streams']+=1
            counts['capacitors']+=count;counts['layouts']+=1
        assert {(v['corner'],v['temperature']) for v in case['measurements']}=={('nominal',27),('ss',0),('ff',85)}
        for row in case['measurements']:
            d=raw(folder/f'electrical-{row["corner"]}-{row["temperature"]}/probe.raw')
            # Frequency is a real axis. ngspice's complex raw format carries an
            # unused imaginary slot (the retained run contains subnormal data).
            assert d['frequency'].real==1000
            values={k:-d['i(vp_'+k+')'].imag/(2*math.pi*1000) for k in ('schematic','extracted','independent')}
            assert all(v>0 and math.isclose(v,row['capacitance_F'][k],rel_tol=1e-12) for k,v in values.items())
            assert all(abs(v/values['independent']-1)<=1e-6 for v in values.values());counts['raw_responses']+=1
        assert {v['name'] for v in case['faults']}=={'dielectric-missing','top-open','bottom-open','reference-width','reference-count'}
        for row in case['faults']:
            dest=folder/row['name'];assert sha(dest/'report.json')==row['report_sha256'];report,stages=verify(dest,'failed')
            assert stages['preflight']['status']=='passed' and stages['layout_export']['status']=='passed'
            assert (dest/'lvs-extraction/extracted.spice').is_file()
            if stages['lvs_extraction']['status']=='passed':
                assert stages['lvs']['status']=='failed' and re.search(r'netlists do not match|circuits do not match|property errors|failed pin matching',(dest/'lvs/lvs.log').read_text(),re.I)
            else:assert re.search('terminal|port|interface',stages['lvs_extraction'].get('error',''),re.I)
            if row['name']=='dielectric-missing':
                assert regions(dest/'layout.gds').get((97,44),db.Region()).is_empty()
                text=(dest/'lvs-extraction/extracted.spice').read_text()
                assert '.subckt device_coupon P\n' in text and 'sky130_fd_pr__cap_mim_m3_2' not in text
            counts['faults']+=1
    assert counts['layouts']==28 and counts['faults']==35 and counts['raw_responses']==21
    result=dict(status='PASS',counts=counts,record_sha256=sha(a.root/'record.json'),audit_sha256=sha(__file__),scope=__doc__)
    a.output.write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result,indent=2))

if __name__=='__main__':main()
