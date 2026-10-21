"""Resolve a two-port network from both measured incident-wave columns.

Each excitation supplies B = S A. Normalizing each column by its driven
incident wave does not set the other incident wave to zero. Solve the full
system; this is a measurement conversion, not port de-embedding.
"""
import math

BASIS = 'full-incident-matrix-v1'
MAX_CONDITION = 1e8


def scattering(incident, reflected):
    """Return S = B inv(A) and its infinity-norm conditioning diagnostic."""
    if any(len(m) != 2 or any(len(row) != 2 for row in m) for m in (incident, reflected)):
        raise ValueError('Each wave matrix must have two rows and two columns.')
    if any(not math.isfinite(z.real) or not math.isfinite(z.imag)
           for matrix in (incident, reflected) for row in matrix for z in row):
        raise ValueError('Non-finite measured port waves.')
    scale = max(abs(z) for row in incident for z in row)
    if not scale: raise ValueError('The incident-wave matrix is singular; rerun with independent excitations.')
    a, b = [[z/scale for z in row] for row in incident]
    det = a[0]*b[1]-a[1]*b[0]
    adj = [[b[1], -a[1]], [-b[0], a[0]]]
    norm = max(sum(abs(z) for z in row) for row in (a, b))
    invnorm = max(sum(abs(z) for z in row) for row in adj)
    if not abs(det) or norm*invnorm > MAX_CONDITION*abs(det):
        raise ValueError('The incident-wave matrix is singular or ill-conditioned; rerun with independent excitations.')
    result = [[sum((row[k]/scale)*adj[k][j] for k in range(2))/det for j in range(2)] for row in reflected]
    if any(not math.isfinite(z.real) or not math.isfinite(z.imag) for row in result for z in row):
        raise ValueError('Non-finite scattering parameters after wave conversion.')
    return result, norm*invnorm/abs(det)
