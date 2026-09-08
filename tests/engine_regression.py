"""Optional real-engine regression. Requires NGSPICE or ngspice on PATH."""
import bisect,json,os,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import example
from icstudio.simulation import run
from icstudio.engines import run_ngspice
exe=os.environ.get('NGSPICE') or shutil.which('ngspice')
if not exe:raise SystemExit('Install ngspice or set NGSPICE to its executable.')
report=[]
with tempfile.TemporaryDirectory(prefix='icstudio-ngspice-') as td:
 for kind,typ in [('rc','tran'),('rc','ac'),('rc','op'),('inverter','dc')]:
  p=example(kind);s={**p['analysis'],'type':typ};out=Path(td)/(kind+'-'+typ);out.mkdir();ext=run_ngspice(p,p['top'],s,exe,out);builtin=run(p,p['top'],s)
  def interp(x):
   xs=ext['x'];ys=ext['traces']['vout'];k=bisect.bisect_left(xs,x)
   if k==0:return ys[0]
   if k>=len(xs):return ys[-1]
   return ys[k-1]+(x-xs[k-1])/(xs[k]-xs[k-1])*(ys[k]-ys[k-1])
  err=max(abs(v-interp(x)) for x,v in zip(builtin['x'],builtin['traces']['vout']));tol=.04 if typ=='tran' else .015 if kind=='inverter' else .001
  assert err<tol,(kind,typ,err,tol);report.append({'fixture':kind,'analysis':typ,'max_error':err,'tolerance':tol,'passed':True})
print(json.dumps(report,indent=2))
