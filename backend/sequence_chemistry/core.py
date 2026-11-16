"""Small peptide sequence-design CHEMISTRY model; does not execute QAOA.

Eight positions with either L or K, exactly three K positions.
Hydrophobic moment is an assumed 100-degree-per-residue alpha-helical proxy,
using Kyte-Doolittle hydropathy. It is NOT a folding/binding/activity model.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from itertools import product
from math import cos, sin, radians, sqrt
from typing import Sequence

HYDROPATHY = {'L': 3.8, 'K': -3.9}  # Kyte & Doolittle, J Mol Biol 157 (1982)
# Average masses of residues within unmodified polypeptides in g/mol.
RESIDUE_MASS = {'L': 113.159, 'K': 128.174}
WATER_MASS = 18.01528

@dataclass(frozen=True)
class DesignSpec:
    length: int = 8
    zero_residue: str = 'L'
    one_residue: str = 'K'
    required_ones: int = 3
    helix_angle_degrees: float = 100.0
    hydropathy_scale: str = 'Kyte-Doolittle (1982)'

SPEC = DesignSpec()

def bits_to_sequence(bits: Sequence[int], spec: DesignSpec = SPEC) -> str:
    if len(bits) != spec.length or any(b not in (0,1) for b in bits):
        raise ValueError('Expected exactly 8 binary residue-position choices')
    return ''.join(spec.one_residue if b else spec.zero_residue for b in bits)

def sequence_to_bits(sequence: str, spec: DesignSpec = SPEC) -> tuple[int,...]:
    if len(sequence) != spec.length or any(x not in (spec.zero_residue, spec.one_residue) for x in sequence):
        raise ValueError('Expected exactly 8 unmodified K/L residues')
    return tuple(int(x == spec.one_residue) for x in sequence)

def hydrophobic_moment(sequence: str, spec: DesignSpec = SPEC) -> float:
    sequence_to_bits(sequence, spec)
    x = sum(HYDROPATHY[aa]*cos(radians(spec.helix_angle_degrees*i)) for i,aa in enumerate(sequence))/spec.length
    y = sum(HYDROPATHY[aa]*sin(radians(spec.helix_angle_degrees*i)) for i,aa in enumerate(sequence))/spec.length
    return sqrt(x*x+y*y)

def approximate_charge(sequence: str, pH: float = 7.4) -> float:
    """Explicitly simplified free-termini HH model for unmodified K/L peptides.
    Assumes N-term pKa 8.0, C-term 3.1, K side chains 10.5. These assumed
    pKa values are illustrative, environment/sequence dependent, not measured.
    """
    sequence_to_bits(sequence)
    if not 0 <= pH <= 14:
        raise ValueError('pH must be from 0 through 14')
    positive_n = 1/(1+10**(pH-8.0))
    positive_k = sequence.count('K')/(1+10**(pH-10.5))
    negative_c = 1/(1+10**(3.1-pH))
    return positive_n + positive_k - negative_c

def sequence_properties(sequence: str, pH: float = 7.4, spec: DesignSpec = SPEC) -> dict:
    bits = sequence_to_bits(sequence, spec)
    mu = hydrophobic_moment(sequence, spec)
    return {
        'sequence': sequence, 'position_bits': list(bits),
        'feasible': sum(bits)==spec.required_ones,
        'length': spec.length, 'lysine_count': sum(bits),
        'leucine_count': spec.length-sum(bits),
        'hydrophobic_moment': mu, 'hydrophobic_moment_squared': mu*mu,
        'mean_hydropathy_kd': sum(HYDROPATHY[aa] for aa in sequence)/spec.length,
        'approximate_net_charge': approximate_charge(sequence, pH), 'charge_pH': pH,
        'approximate_mass_g_per_mol': WATER_MASS + sum(RESIDUE_MASS[aa] for aa in sequence),
        'hydropathy_method': f'{spec.hydropathy_scale}; {spec.helix_angle_degrees} degree ideal alpha helix',
        'charge_method': 'simplified Henderson-Hasselbalch; free termini; assumed pKas N=8.0, C=3.1, K=10.5',
        'limitations': 'Sequence-derived research proxy; no predicted structure, binding, efficacy or laboratory activity'
    }

def chemistry_quadratic(spec: DesignSpec = SPEC, weight: float = 1.0) -> dict:
    """QUBO-ready chemistry coefficients for -weight * hydrophobic_moment^2.

    Encoding: f(bits)=constant + sum(linear[i]*bits[i])
                         + sum_{i<j}(pairwise[i][j]*bits[i]*bits[j]).
    Does not include any selection-count constraint or penalty; that belongs
    to the separate quantum-optimization team.
    """
    if spec.length != 8 or spec.zero_residue!='L' or spec.one_residue!='K':
        raise ValueError('Only verified 8-position K/L demonstration supported')
    if weight < 0:
        raise ValueError('weight must be nonnegative')
    n = spec.length
    delta = HYDROPATHY['K']-HYDROPATHY['L']
    c = [cos(radians(spec.helix_angle_degrees*i)) for i in range(n)]
    s = [sin(radians(spec.helix_angle_degrees*i)) for i in range(n)]
    c0 = HYDROPATHY['L']*sum(c)/n
    s0 = HYDROPATHY['L']*sum(s)/n
    ai = [delta*v/n for v in c]
    bi = [delta*v/n for v in s]
    const = -weight*(c0*c0+s0*s0)
    linear = [-weight*(2*c0*ai[i]+2*s0*bi[i]+ai[i]*ai[i]+bi[i]*bi[i]) for i in range(n)]
    pairwise = [[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1,n):
            pairwise[i][j] = -weight*2*(ai[i]*ai[j]+bi[i]*bi[j])
    return {'constant':const, 'linear':linear, 'pairwise_upper_triangle':pairwise,
            'convention':'constant + sum_i linear[i]*x_i + sum_i<j pairwise[i][j]*x_i*x_j',
            'objective':'minimize -weight*hydrophobic_moment_squared',
            'weight':weight, 'position_indexing':'0-based N-terminal to C-terminal'}

def evaluate_quadratic(bits: Sequence[int], quadratic: dict) -> float:
    if len(bits)!=len(quadratic['linear']) or any(x not in (0,1) for x in bits):
        raise ValueError('Invalid bit vector')
    return (quadratic['constant'] + sum(a*x for a,x in zip(quadratic['linear'],bits)) +
            sum(quadratic['pairwise_upper_triangle'][i][j]*bits[i]*bits[j]
                for i in range(len(bits)) for j in range(i+1,len(bits))))

def exact_reference(spec: DesignSpec = SPEC) -> dict:
    items=[]
    quadratic=chemistry_quadratic(spec)
    max_error=0.0
    for bits in product((0,1), repeat=spec.length):
        seq=bits_to_sequence(bits,spec)
        value=hydrophobic_moment(seq,spec)**2
        error=abs(evaluate_quadratic(bits,quadratic)+value)
        max_error=max(max_error,error)
        if sum(bits)==spec.required_ones:
            items.append({'sequence':seq,'bits':list(bits),'hydrophobic_moment_squared':value,
                          'chemistry_objective':-value})
    items.sort(key=lambda x:(x['chemistry_objective'],x['sequence']))
    return {'spec':asdict(spec),'all_binary_states':2**spec.length,
            'feasible_sequences':len(items),'best_feasible':items[0],
            'top_five':items[:5], 'max_quadratic_identity_error':max_error,
            'note':'No quantum execution; exact classical benchmark for chemistry-only score'}
