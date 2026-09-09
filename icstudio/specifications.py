"""Portable output requirements, evaluated against immutable run snapshots."""
from .model import scalar, digest
from .wavecalc import parse, evaluate, UNITS, unit_name


def validate_rows(rows):
    if not isinstance(rows,list) or len(rows)>100:raise ValueError('Use at most 100 specifications per cell or testbench.')
    names=set()
    for row in rows:
        name=row.get('name','').strip()
        if not name or len(name)>120 or name.casefold() in names:raise ValueError('Specification names must be unique and contain 1–120 characters.')
        names.add(name.casefold());parse(row.get('expression',''))
        if row.get('unit','') not in UNITS:raise ValueError('Choose a supported base unit for '+name+'.')
        limits={k:scalar(row[k]) for k in ('min','max') if row.get(k) not in (None,'')}
        if len(limits)==2 and limits['min']>limits['max']:raise ValueError(name+': lower limit exceeds upper limit.')
        if not limits:raise ValueError(name+': enter a lower or upper requirement.')
    return rows


def evaluate_rows(rows,result):
    validate_rows(rows);out=[]
    for spec in rows:
        row={**spec,'status':'ERROR','value':None,'margin':None,'error':''}
        try:
            signal=evaluate(spec['expression'],result)
            if signal.x is not None:raise ValueError('Reduce the expression to a scalar: final(), min(), max(), rms(), at(), crossing() or settling().')
            if signal.unit!=UNITS[spec.get('unit','')]:raise ValueError('Expression unit '+(unit_name(signal.unit) or '1')+' differs from declared '+(spec.get('unit') or '1')+'.')
            value=signal.real_values()[0];margins=[]
            if spec.get('min') not in (None,''):margins.append(value-scalar(spec['min']))
            if spec.get('max') not in (None,''):margins.append(scalar(spec['max'])-value)
            row.update(value=value,margin=min(margins),status='PASS' if min(margins)>=0 else 'FAIL')
        except (ValueError,ArithmeticError) as exc:row['error']=str(exc)
        out.append(row)
    return out


def for_job(job):
    p=job['project'];key=job.get('testbench_id') or job.get('settings',{}).get('testbench')
    bench=next((t for t in p.get('testbenches',[]) if t['id']==key),None)
    cell=next(c for c in p['cells'] if c['id']==job['cell'])
    return bench.get('specifications',[]) if bench and 'specifications' in bench else cell.get('specifications',[])


def attach(job,result):
    rows=for_job(job)
    if rows and result.get('x') and result.get('traces'):
        result['specifications']=evaluate_rows(rows,result);result['specification_hash']=digest(rows)
    if job.get('case'):result['case']=job['case']
    return result


def validate_project(p):
    for owner in p['cells']+p.get('testbenches',[]):
        validate_rows(owner.get('specifications',[]))
        layouts=owner.get('plot_layouts',[])
        if not isinstance(layouts,list) or len(layouts)>12:raise ValueError('Use at most 12 saved plot panels.')
        for item in layouts:
            if not isinstance(item.get('name'),str) or not 1<=len(item['name'])<=120:raise ValueError('A plot panel needs a name.')
            parse(item.get('expression',''))
