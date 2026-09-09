"""Record engine identity for reproducible case replay without guessing versions."""
from .model import file_digest
from .build_info import WORKFLOW_SOURCE_HASH


def stamp(job):
    out={'workflow_hash':WORKFLOW_SOURCE_HASH,'engine':job['engine']}
    if job['engine']=='ngspice':out['executable_sha256']=file_digest(job['executable'])
    return out


def verify(job):
    if job.get('environment') is not None and stamp(job)!=job['environment']:raise ValueError('The simulation implementation or executable changed since this study was planned. Create a new study for the current engine; completed historical results remain available.')
