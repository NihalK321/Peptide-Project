"""Workflow-specific circuits and decoders for the shared IBM run checkbox.

Existing local solvers stay unchanged. Locally fitted circuits are verified on
hardware; their ideal probabilities never become hardware probabilities.
"""

import numpy as np
from pydantic import Field
from qiskit import qasm2
from scipy.optimize import minimize

from .schema import Model


class HeHHardwareConfig(Model):
    bond_distance_angstrom: float = Field(default=1, ge=.2, le=5)
    maxiter: int = Field(default=60, ge=10, le=200, strict=True)


def build_workload(workflow, settings, shots):
    settings = dict(settings)
    if workflow in ('sequence', 'sequence_multi'):
        from .sequence_design.models import SequenceDesignRequest, MultiChoiceRequest
        from .sequence_design.solver import optimize
        request = (MultiChoiceRequest if workflow == 'sequence_multi' else SequenceDesignRequest)(**settings)
        result = optimize(request)
        rows = {row['bitstring']: {key: value for key, value in row.items()
            if key not in ('probability', 'count', 'observed_frequency')} for row in result['states']}
        return dict(circuits=[qasm2.loads(result['circuit']['qasm'])], primitive='sampler',
            decoding={'kind': 'rows', 'rows': rows}, reference=result['classical_reference'],
            warm_start={'method': 'local ideal-statevector QAOA parameter fitting', 'parameters': result['parameters'],
                        'note': 'Only final circuit measurements run on the QPU; parameter fitting used local simulation.'})
    if workflow == 'blend':
        from .blends.api import get_blend_catalog
        from .blends.models import BlendRequest
        from .blends.solver import optimize_blend
        request = BlendRequest(**settings)
        result = optimize_blend(get_blend_catalog(), request)
        return dict(circuits=[qasm2.loads(result['circuit_qasm'])], primitive='sampler',
            decoding={'kind': 'blend', 'rows': {row['bitstring']: {**row, 'feasible': True}
                for row in result['classical_feasible_selections']}, 'candidates': result['candidates']},
            reference=result['classical_reference'], warm_start={'method': 'local ideal-statevector QAOA parameter fitting',
                'parameters': result['parameters'], 'note': 'Final blend measurements run on hardware; fitting and descriptors stay local.'})
    if workflow == 'sequence_large':
        from .sequence_design.models import LargeSequenceRequest
        from .sequence_design.large_solver import run_large
        request = LargeSequenceRequest(**settings)
        result = run_large(request, export_only=True)
        return dict(circuits=[qasm2.loads(result['circuit']['qasm'])], primitive='sampler',
            decoding={'kind': 'large', 'request': request.model_dump()}, reference=result['classical_baseline'],
            warm_start={'method': 'user-specified initial QAOA angles; no local fitting', 'parameters': result['parameters'],
                        'note': 'Hardware samples the supplied angles. This is not a completed adaptive hardware optimization.'})
    if workflow == 'scalable':
        from .sequence_design.scalable_choices import ScalableChoiceRequest, compile_choices, build_circuit, classical_search
        request = ScalableChoiceRequest(**settings)
        model = compile_choices(request)
        if model['logical_gate_count'] > 15000:
            raise ValueError('Hardware circuit exceeds 15,000 logical gates. Reduce choices or positions; preview/export remains available.')
        return dict(circuits=[build_circuit(model, values) for values in request.parameter_sets], primitive='sampler',
            decoding={'kind': 'scalable', 'request': request.model_dump()}, reference=classical_search(model, request),
            warm_start={'method': 'bounded hardware parameter sweep, no local quantum simulation',
                        'parameters': request.parameter_sets, 'note': 'The lowest sampled mean penalized cost selects an angle set; selection can overfit shot noise.'})
    if workflow == 'torsion':
        from .schema import OptimizationRequest
        from .chemistry import build_problem
        from .quantum import build_qaoa_circuit, qaoa_probabilities, _expand_for_display
        request = OptimizationRequest(**{**settings, 'method': 'qaoa'})
        problem = build_problem(request)
        energies = np.array([row.energy_kcal_mol for row in problem.configurations])
        normalized = (energies-energies.min())/max(float(np.ptp(energies)), 1e-12)
        rng = np.random.default_rng(request.seed)
        fitted = minimize(lambda values: float(qaoa_probabilities(energies, values) @ normalized),
            rng.uniform(.1, np.pi, 2*request.layers), method='COBYLA', options={'maxiter': request.max_iterations})
        rows = {row.bitstring: {**row.model_dump(), 'objective': row.energy_kcal_mol, 'feasible': True}
                for row in problem.configurations}
        return dict(circuits=[_expand_for_display(build_qaoa_circuit(energies, fitted.x))], primitive='sampler',
            decoding={'kind': 'rows', 'rows': rows}, reference=min(rows.values(), key=lambda row: row['objective']),
            warm_start={'method': 'local MMFF94 grid and ideal QAOA parameter fitting', 'parameters': fitted.x.tolist(),
                        'note': 'Hardware chooses among existing torsion-grid configurations. Molecular mechanics and geometry remain classical.'})
    if workflow == 'heh':
        from .quantum_chemistry.heh_plus import HeHPlusConfig, run_heh_plus_vqe, build_heh_plus_system, _decompose_for_metadata
        request = HeHHardwareConfig(**settings)
        config = HeHPlusConfig(**request.model_dump())
        try:
            fitted = run_heh_plus_vqe(config)
            system = build_heh_plus_system(config)
        except (RuntimeError, ImportError):
            raise ValueError('HeH+ hardware requires the optional Qiskit Nature/Algorithms and PySCF chemistry dependencies on the backend. See backend/quantum_chemistry/requirements.txt; PySCF may require Linux/WSL.') from None
        circuit = _decompose_for_metadata(system.ansatz.assign_parameters(fitted.optimal_parameters))
        return dict(circuits=[circuit], primitive='estimator', observable=system.qubit_hamiltonian,
            decoding={'kind': 'heh', 'nuclear_repulsion_hartree': fitted.nuclear_repulsion_hartree,
                'classical_electronic_energy_hartree': fitted.classical_electronic_energy_hartree,
                'classical_total_molecular_energy_hartree': fitted.classical_total_molecular_energy_hartree,
                'bond_distance_angstrom': config.bond_distance_angstrom},
            reference={'total_molecular_energy_hartree': fitted.classical_total_molecular_energy_hartree},
            warm_start={'method': 'local ideal-state VQE/UCCSD parameter fitting, followed by a hardware energy estimate',
                'parameters': list(fitted.optimal_parameters), 'basis': 'sto3g', 'mapping': fitted.mapping,
                'note': 'Estimator measures one optimized ansatz at the selected distance. This is hardware verification, not an adaptive hardware VQE scan.'})
    raise ValueError('Unsupported hardware workflow.')


def decode_measurements(data, counts):
    if data['kind'] in ('rows', 'blend'):
        rows = data['rows']
        observed, infeasible = [], 0
        for bits, count in counts.items():
            row = rows.get(bits)
            if row is None or not row.get('feasible'):
                infeasible += count
                continue
            observed.append({**row, 'count': count, 'observed_frequency': count/sum(counts.values())})
        observed.sort(key=lambda row: (row['objective'], -row['count']))
        return {'best_sampled': observed[0] if observed else None, 'candidate_sequences': observed[:10],
            'shots': sum(counts.values()), 'feasible_shots': sum(counts.values())-infeasible, 'invalid_shots': infeasible}
    if data['kind'] == 'large':
        from .sequence_design.models import LargeSequenceRequest
        from .sequence_design.scalable import compile_quadratic, decode
        from .sequence_design.problem import score_sequence
        request = LargeSequenceRequest(**data['request'])
        model = compile_quadratic(request)
        observed = [{**score_sequence(decode(model['domains'], model['variables'], [int(b) for b in bits[::-1]]), request),
                     'bitstring': bits, 'count': count, 'observed_frequency': count/sum(counts.values())} for bits, count in counts.items()]
        observed.sort(key=lambda row: row['objective'])
        return {'best_sampled': observed[0], 'candidate_sequences': observed[:10], 'shots': sum(counts.values()),
                'feasible_shots': sum(counts.values()), 'invalid_shots': 0}
    from .sequence_design.scalable_choices import ScalableChoiceRequest, compile_choices, summarize_counts
    request = ScalableChoiceRequest(**data['request'])
    return summarize_counts(compile_choices(request), request, counts)
