"""Independent numerical reader for retained MiM v1 qualification outputs."""
from pathlib import Path
import argparse,hashlib,json,math,sys
PORTS=('p1','n1','p2','n2');TAGS=('app','reference','native','cross','missing','width');PROFILES={'e1':(1.25,.25,-.5,-.5),'e2':(.25,.25,.5,-.5)}
def require(test,message):
 if not test:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def finite_float(value):
 result=float(value);require(math.isfinite(result),'nonfinite JSON number');return result
def strict(data):
 def pairs(items):
  out={}
  for k,v in items:
   require(k not in out,'duplicate JSON key');out[k]=v
  return out
 return json.loads(data,object_pairs_hook=pairs,parse_constant=lambda v:require(False,'nonfinite JSON'),parse_float=finite_float)
def validation_errors(fn):
 def call(*args,**kwargs):
  try:return fn(*args,**kwargs)
  except (KeyError,TypeError,IndexError,OverflowError,ZeroDivisionError,UnicodeDecodeError) as exc:raise ValueError('malformed qualification evidence') from exc
 return call
@validation_errors
def raw_data(data):
 lines=data.decode('ascii').splitlines();require(lines.count('Variables:')==1 and lines.count('Values:')==1,'raw plot count');a=lines.index('Variables:');b=lines.index('Values:');header=lines[:a]
 require(len(header) in (6,7),'raw header count');require(header[0].startswith('Title: * icstudio-mim-hierarchy-electrical-v1 ') and len(header[0].split()[-1])==64,'raw title');require(header[1].startswith('Date: ') and bool(header[1][6:].strip()),'raw date')
 offset=2
 if len(header)==7:require(header[2].startswith('Command: ngspice-46,'),'raw command');offset=3
 require(header[offset]=='Plotname: AC Analysis' and header[offset+1]=='Flags: complex' and header[offset+2].strip()=='No. Variables: 61' and header[offset+3].strip()=='No. Points: 8','raw plot metadata')
 names=['frequency'];types=['frequency']
 for tag in TAGS:
  for port in PORTS:names.extend((f'v({tag}_{port})',f'i(v_{tag}_{port})'));types.extend(('voltage','current'))
 for name in ('rm3','rm4','rcvia3','rcvia4','tol_m3','tol_m4','camimc','cpmimc','m3_dw','m4_dw','mc_mm_switch','mc_pr_switch'):names.append('v(par_'+name+')');types.append('voltage')
 records=lines[a+1:b];require(len(records)==61,'raw variable count')
 for i,line in enumerate(records):
  fields=line.split();expected=[str(i),names[i],types[i]]+(['grid=3'] if i==0 else []);require([x.lower() for x in fields]==expected,'raw variable index/name/type differs')
 values=lines[b+1:];require(len(values)==61*8,'raw value row count');rows=[]
 for point in range(8):
  row=[]
  for i in range(61):
   fields=values[point*61+i].split();require(len(fields)==(2 if i==0 else 1),'raw value tokens differ')
   if i==0:require(fields[0]==str(point),'raw point index differs')
   pair=fields[-1].split(',');require(len(pair)==2,'raw complex value');z=complex(float(pair[0]),float(pair[1]));require(math.isfinite(z.real) and math.isfinite(z.imag),'raw nonfinite');row.append(z)
  rows.append(dict(zip(names,row)))
 return rows
@validation_errors
def scientific(data,plate,section,profile,coeff):
 require(plate in (1,2) and profile in PROFILES,'case unsupported');samples=raw_data(data);max_error=0;detected={k:False for k in ('cross','missing','width')};metal=plate+2
 def adm(width,f):
  dw=1e6*(coeff[f'm{metal}_dw']+coeff[f'tol_m{metal}']);w=width+dw;l=10+dw;R=coeff[f'rm{metal}']*l/w+coeff[f'rcvia{metal}']*(.56 if plate==1 else .73)**2/(w*l);C=coeff['camimc']*w*l+2*coeff['cpmimc']*(w+l);require(min(w,l,R,C)>0,'nonpositive RC');z=2j*math.pi*f*C;value=z/(1+R*z);require(math.isfinite(value.real) and math.isfinite(value.imag) and abs(value)>0,'invalid admittance');return value
 for i,row in enumerate(samples):
  f=10**(i+3);require(abs(row['frequency']-f)<f*1e-10,'frequency differs')
  for name,z in row.items():require(math.isfinite(z.real) and math.isfinite(z.imag),'nonfinite raw')
  for name in ('rm3','rm4','rcvia3','rcvia4','tol_m3','tol_m4','camimc','cpmimc','m3_dw','m4_dw','mc_mm_switch','mc_pr_switch'):
   expected=0 if name.startswith('mc_') else coeff[name];require(abs(row['v(par_'+name+')']-expected)<=1e-24+abs(expected)*1e-10,'coefficient differs: '+name)
  for tag in TAGS:
   V=[row[f'v({tag}_{p})'] for p in PORTS];I=[-row[f'i(v_{tag}_{p})'] for p in PORTS];require(all(abs(v-e)<=1e-12 for v,e in zip(V,PROFILES[profile])),'stimulus differs');edges=[(0,1,2)]
   if tag!='missing':edges.append((0 if tag=='cross' else 2,3,3 if tag=='width' else 2))
   expected=[0j]*4
   for a,b,w in edges:
    current=adm(w,f)*(V[a]-V[b]);expected[a]+=current;expected[b]-=current
   base=adm(2,f);bound=abs(base)*1e-6;error=max(abs(x-y) for x,y in zip(I,expected))/bound;max_error=max(max_error,error);require(error<=1,'terminal current differs');require(abs(sum(I))<=bound,'global KCL differs')
   if tag in ('app','reference','native'):
    for a,b in ((0,1),(2,3)):
     require(abs(I[a]+I[b])<=bound,'pair KCL differs');dv=V[a]-V[b]
     if dv:
      y=I[a]/dv;require(math.isfinite(y.real) and math.isfinite(y.imag) and abs(y)>0,'invalid measured admittance');require(abs(y-base)<=abs(base)*1e-6,'admittance differs');z=1/y;ez=1/base;require(math.isfinite(z.real) and math.isfinite(z.imag) and z.imag!=0,'invalid measured impedance');require(abs(z.real-ez.real)<=ez.real*1e-6,'resistance differs');cap=-1/(2*math.pi*f*z.imag);ec=-1/(2*math.pi*f*ez.imag);require(math.isfinite(cap) and math.isfinite(ec) and ec>0,'invalid capacitance');require(abs(cap-ec)<=ec*1e-6,'capacitance differs')
     else:require(abs(I[a])<=bound,'inactive current differs')
   if tag in detected:
    reference=[-row[f'i(v_native_{p})'] for p in PORTS];detected[tag]|=max(abs(x-y) for x,y in zip(I,reference))>bound
 return {'maximum_normalized_error':max_error,'detections':detected}
@validation_errors
def load_contract(path,pin):
 data=Path(path).read_bytes();require(sha(data)==pin,'electrical contract identity differs');return strict(data)['passive_sections']
@validation_errors
def read_v4(root,contract,contract_sha):
 root=Path(root);sections=load_contract(contract,contract_sha);records=strict((root/'summary.json').read_bytes());require(isinstance(records,list) and len(records)==40,'full v1 matrix required');keys=set();maximum=0;faults=0
 for rec in records:
  case=rec['case'];profile=rec['profile'];name=case['name'];expected_name=f"p{case['plate']}-r{case['rotation']}-{case['section']}";require(name==expected_name,'case metadata differs');key=(name,profile);require(key not in keys and rec['status']=='PASS','duplicate or failed record');keys.add(key);data=(root/name/profile/'result.raw').read_bytes();require(sha(data)==rec['raw_sha256'],'raw identity differs');r=scientific(data,case['plate'],case['section'],profile,sections[case['section']]['coefficients']);maximum=max(maximum,r['maximum_normalized_error'])
  if profile=='e2':require(all(r['detections'].values()),'native fault not detected');faults+=3
 expected={(f'p{p}-r{r}-{s}',e) for p in (1,2) for r in (0,90) for s in ('tt','ll','hh','hl','lh') for e in PROFILES};require(keys==expected,'selection differs');return {'status':'PASS','scope':'scientific readback only; provenance separately audited','runs':40,'network_frequency_samples':1920,'detected_faults':faults,'maximum_normalized_error':maximum}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--v4-root',required=True);p.add_argument('--contract',required=True);p.add_argument('--contract-sha',required=True);a=p.parse_args(argv);print(json.dumps(read_v4(a.v4_root,a.contract,a.contract_sha),allow_nan=False))
if __name__=='__main__':main()

