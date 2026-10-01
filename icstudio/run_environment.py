"""Record engine identity for reproducible case replay without guessing versions."""
from .model import file_digest
from .build_info import WORKFLOW_SOURCE_HASH


def stamp(job):
    if job.get('engine')=='mixed_signal':
        from .mixed_signal import environment
        return environment(job)
    if job.get('engine')=='digital':
        from .digital_flow import environment
        return environment(job)
    out={'workflow_hash':WORKFLOW_SOURCE_HASH,'engine':job['engine']}
    if job['engine']=='ngspice':
        if job['settings'].get('managed_osdi'):
            from . import digital_runtime
            from .osdi import managed_models
            from .model import digest
            runtime=job['settings']['physical_runtime']
            digital_runtime.identity(runtime)
            out.update(runtime_sha256=runtime['sha256'],osdi=digest(managed_models(job['project']['pdk'],digital_runtime.manifest())))
        else:out['executable_sha256']=file_digest(job['executable'])
    return out


def verify(job):
    if job.get('environment') is not None and stamp(job)!=job['environment']:raise ValueError('The simulation implementation or executable changed since this study was planned. Create a new study for the current engine; completed historical results remain available.')
