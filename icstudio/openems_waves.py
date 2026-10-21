"""Resolve a two-port network from both measured incident-wave columns.

Each excitation supplies B = S A. Normalizing each column by its driven
incident wave does not set the other incident wave to zero. Solve the full
system; this is a measurement conversion, not port de-embedding.
"""
import math

BASIS = 'full-incident-matrix-v1'
MAX_CONDITION = 1e8
# This is a roundoff allowance on voltage-wave gain, not a mesh-error budget.
# Both ports have the same real 50-ohm reference, so a passive network must
# satisfy ||S a|| <= ||a|| for every incident vector a.
PASSIVITY_ALLOWANCE = 1e-9
PASSIVITY_CHECK = 'sampled-two-port-power-v1'


def validate_passivity(record, frequency):
    """Require the sampled check when reopening structured solver evidence."""
    if not isinstance(record, dict) or record.get('check') != PASSIVITY_CHECK:
        raise ValueError('Full two-port passivity evidence is missing. Rerun the field solver with the current acceptance checks.')
    for key in ('maximum_scattering_gain', 'frequency_hz', 'reference_ohm', 'roundoff_allowance'):
        if type(record.get(key)) not in (int,float) or not math.isfinite(record[key]):
            raise ValueError('Invalid two-port passivity evidence: '+key+'.')
    if (record.get('passed') is not True or record['reference_ohm'] != 50.
            or record['roundoff_allowance'] != PASSIVITY_ALLOWANCE
            or not 0 <= record['maximum_scattering_gain'] <= 1+PASSIVITY_ALLOWANCE
            or type(record.get('sample_count')) is not int or record['sample_count'] != len(frequency)
            or not any(math.isclose(record['frequency_hz'], f, rel_tol=1e-10) for f in frequency)):
        raise ValueError('Invalid or failed two-port passivity evidence.')


def maximum_gain(matrix):
    """Largest singular value of a 2x2 complex S matrix, without NumPy.

    Use the analytic Hermitian eigenvalues of S^H S. Scaling avoids overflow
    when rejecting extreme invalid responses; no S values are clipped or fit.
    """
    if len(matrix) != 2 or any(len(row) != 2 for row in matrix):
        raise ValueError('The scattering matrix must have two rows and two columns.')
    if any(not math.isfinite(z.real) or not math.isfinite(z.imag) for row in matrix for z in row):
        raise ValueError('Non-finite scattering parameters.')
    scale = max(abs(z) for row in matrix for z in row)
    if not math.isfinite(scale): raise ValueError('Scattering magnitude overflow.')
    if not scale: return 0.
    a, b = [[complex(z)/scale for z in row] for row in matrix]
    h00 = abs(a[0])**2+abs(b[0])**2
    h11 = abs(a[1])**2+abs(b[1])**2
    h01 = a[0].conjugate()*a[1]+b[0].conjugate()*b[1]
    value = scale*math.sqrt((h00+h11+math.hypot(h00-h11, 2*abs(h01)))/2)
    if not math.isfinite(value): raise ValueError('Scattering gain overflow.')
    return value


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
