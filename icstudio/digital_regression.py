"""Saved digital regression cases and Verilator coverage instrumentation."""
from __future__ import annotations

from .model import clone


def validate_tests(tests):
    from .digital import IDENT
    if not isinstance(tests,list) or not 1<=len(tests)<=100:raise ValueError('Save 1–100 digital regression cases.')
    names=set()
    for case in tests:
        if not isinstance(case,dict):raise ValueError('Each regression case must be an object.')
        name=case.get('name','')
        if not isinstance(name,str) or not 1<=len(name)<=100 or name.casefold() in names:raise ValueError('Regression case names must be unique.')
        names.add(name.casefold())
        if not IDENT.fullmatch(case.get('testbench','')):raise ValueError('Each case needs a testbench top.')
        if case.get('simulator','icarus') not in ('icarus','verilator'):raise ValueError('Choose Icarus or Verilator for each case.')
        if not isinstance(case.get('defines',{}),dict):raise ValueError('Case preprocessor definitions must be a dictionary.')
        if type(case.get('coverage',False)) is not bool:raise ValueError('Case coverage must be boolean.')
        if case.get('coverage') and case.get('simulator','icarus')!='verilator':raise ValueError('Instrumented coverage requires Verilator.')


def required_tools(config):
    tests=config.get('tests',[]);validate_tests(tests);names=set()
    for case in tests:
        names.update(('iverilog','vvp') if case.get('simulator','icarus')=='icarus' else ('verilator',))
        if case.get('coverage'):names.add('verilator_coverage')
    return sorted(names)


def cases(project,cid):
    from .digital_design import config,set_config
    from .digital import validate_config
    original=config(project,cid);validate_tests(original.get('tests',[]));result=[]
    for case in original['tests']:
        p=clone(project);value=clone(original);value.pop('tests',None)
        value.update(testbench=case['testbench'],defines={**value.get('defines',{}),**case.get('defines',{})},coverage=case.get('coverage',False))
        validate_config(value);set_config(p,cid,value)
        result.append((case,p))
    return result


def coverage_main():
    return '''#include "verilated.h"
#include "verilated_cov.h"
#include "Vstudio.h"
#include <memory>
int main(int argc, char** argv) {
  const std::unique_ptr<VerilatedContext> context{new VerilatedContext};
  context->traceEverOn(true);
  context->commandArgs(argc, argv);
  const std::unique_ptr<Vstudio> top{new Vstudio{context.get()}};
  while (!context->gotFinish()) {
    top->eval();
    if (!top->eventsPending()) break;
    context->time(top->nextTimeSlot());
  }
  top->final();
  context->coveragep()->write("coverage.dat");
  return context->gotFinish() ? 0 : 2;
}
'''


def execute(runner):
    import json
    from . import digital_flow
    from .model import atomic_write
    results=[]; definitions=cases(runner.job['project'],runner.job['cell'])
    for index,(case,project) in enumerate(definitions):
        folder=runner.root/'cases'/str(index+1);folder.mkdir(parents=True)
        item={'name':case['name'],'simulator':case.get('simulator','icarus'),'directory':folder.relative_to(runner.root).as_posix()}
        try:
            job=digital_flow.prepare(project,'simulate',item['simulator'],runner.tools,cell_id=runner.job['cell'])
            atomic_write(folder/'input.json',json.dumps(job))
            result=digital_flow.run(job,folder,lambda fraction,message:runner.progress((index+fraction)/len(definitions),case['name']+': '+message))
            atomic_write(folder/'result.json',json.dumps(result))
            from .job_store import state
            state(folder,'complete')
            item.update(status='PASS',source_hash=result['digital_result']['source_hash'],coverage=result['digital_result'].get('coverage'))
        except InterruptedError:raise
        except Exception as exc:
            item.update(status='FAIL',error=str(exc))
            from .job_store import state
            state(folder,'failed',error=str(exc))
        # A failed test stays in the regression matrix, and other tests still run.
        results.append(item)
    status='PASS' if all(c['status']=='PASS' for c in results) else 'FAIL'
    report={'status':status,'cases':results,'passed':sum(c['status']=='PASS' for c in results),'total':len(results),
            'scope':'Captured testbench assertions and process outcomes; no claim of exhaustive verification.'}
    runner.save_json('regression',report,'regression.json')
    for index,item in enumerate(results,1):
        for name in ('engine.log','result.json','waveform.json','coverage.info'):
            path=runner.root/item['directory']/name
            if path.is_file():runner.add_artifact('case_'+str(index)+'_'+name.replace('.','_'),path)
    return {'regression':report,'verdict':status,'statistics':{'passed':report['passed'],'total':report['total']},
            'summary':f"Regression {status} · {report['passed']}/{report['total']} cases passed"}
