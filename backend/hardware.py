"""One explicit Run action for every supported circuit; no import-time network."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Lock
from time import perf_counter, time
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import Field
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from .schema import Model
from .sequence_design.qpu_sequence import runtime_service, identifier
from .hardware_workflows import build_workload, decode_measurements

router = APIRouter(prefix='/hardware', tags=['IBM hardware execution'])
STORE = Path(__file__).resolve().parent.parent/'.cache'/'pepperq-hardware'
LOCK = Lock()


class HardwareRun(Model):
    workflow: Literal['sequence', 'sequence_multi', 'sequence_large', 'scalable', 'blend', 'torsion', 'heh']
    settings: dict
    backend_name: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    shots: int = Field(default=256, ge=128, le=1024, strict=True)
    max_execution_seconds: int = Field(default=60, ge=10, le=180, strict=True)
    request_id: str
    use_qpu: Literal[True]


def path(key):
    return STORE/f'{identifier(key)}.json'


def save(context):
    STORE.mkdir(parents=True, exist_ok=True)
    target = path(context['request_id'])
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(context, allow_nan=False), encoding='utf-8')
    temporary.replace(target)


def load(key):
    try:
        return json.loads(path(key).read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ValueError('Hardware run not found on this backend.') from None


def public(context):
    return {key: value for key, value in context.items() if key not in ('decoding', 'request_hash', 'submitted_epoch')}


def available_backends():
    """Read-only discovery using the same server account as actual submissions."""
    service = runtime_service()
    try:
        backends = service.backends(operational=True, simulator=False)
        return {'backends': sorted([{'name': backend.name, 'qubits': backend.num_qubits} for backend in backends],
                                  key=lambda row: row['name']),
                'notice': 'Read-only IBM account lookup. No quantum job submitted or QPU runtime consumed.'}
    except Exception:
        raise ValueError('IBM account initialized, but available QPUs could not be listed. Check the account/instance access and region configured in the terminal running the backend. No job submitted.') from None


def start(config):
    identifier(config.request_id)
    fingerprint = hashlib.sha256(config.model_dump_json().encode()).hexdigest()
    with LOCK:
        if path(config.request_id).exists():
            existing = load(config.request_id)
            if existing['request_hash'] != fingerprint:
                raise ValueError('This run ID belongs to different settings. Recover its status instead.')
            return public(existing)  # Idempotent retry: never resubmit.
        service = runtime_service()  # Fail before fitting if account access is disabled.
        try:
            backend = service.backend(config.backend_name)
        except Exception:
            raise ValueError('IBM could not find or grant access to that backend. Click "Load my IBM backends" and select a returned name. If none are returned, check the server account, instance and region. No job submitted.') from None
        try:
            operational = backend.status().operational and not backend.configuration().simulator
        except Exception:
            raise ValueError('IBM found that backend but its status could not be read. Refresh the available backend list or retry later. No job submitted.') from None
        if not operational:
            raise ValueError('Select an operational physical IBM quantum backend.')
        context = {'request_id': config.request_id, 'request_hash': fingerprint, 'workflow': config.workflow,
            'backend_name': config.backend_name, 'settings': config.settings, 'shots_requested': config.shots,
            'max_execution_seconds': config.max_execution_seconds, 'status': 'PREPARING',
            'created_at': datetime.now(timezone.utc).isoformat(), 'job_id': None,
            'notice': 'QPU measurement only; chemistry, classical references and any indicated local parameter fitting run on the CPU.'}
        # A process-local lock is insufficient when multiple API workers run.
        # Keep an atomic claim for this ID even if preparation crashes.
        STORE.mkdir(parents=True, exist_ok=True)
        try:
            with path(config.request_id).with_suffix('.claim').open('x') as stream:
                stream.write(fingerprint)
        except FileExistsError:
            raise ValueError('This run ID is already being prepared or was interrupted. Recover its status; it cannot submit twice.') from None
        save(context)
        submitted = False
        try:
            started = perf_counter()
            workload = build_workload(config.workflow, config.settings, config.shots)
            circuits = workload['circuits']
            if any(circuit.num_qubits > backend.num_qubits for circuit in circuits):
                raise ValueError('The selected IBM backend has too few qubits.')
            if any(len(circuit.data) > 15000 for circuit in circuits) or sum(len(c.data) for c in circuits) > 50000:
                raise ValueError('Circuit exceeds the hardware gate budget. Reduce choices, positions or layers.')
            preparation_seconds = perf_counter()-started
            manager = generate_preset_pass_manager(backend=backend, optimization_level=1, seed_transpiler=42)
            native, metadata = [], []
            for original in circuits:
                circuit = original.copy()
                if workload['primitive'] == 'sampler':
                    circuit.measure_all()
                isa = manager.run(circuit)
                two_qubit = sum(item.operation.num_qubits == 2 for item in isa.data)
                if two_qubit > 20000 or isa.depth() > 20000:
                    raise ValueError('Device routing exceeds the prototype circuit budget. Reduce the design.')
                native.append(isa)
                metadata.append({'logical_qubits': original.num_qubits, 'physical_qubits': isa.num_qubits,
                                 'depth': isa.depth(), 'two_qubit_gates': two_qubit})
            context.update(primitive=workload['primitive'], warm_start=workload['warm_start'],
                classical_reference=workload['reference'], decoding=workload['decoding'], circuits=metadata,
                local_preparation_seconds=preparation_seconds,
                preparation_and_transpilation_seconds=perf_counter()-started,
                requested_circuit_count=len(circuits))
            from qiskit_ibm_runtime import EstimatorV2, SamplerV2
            options = {'max_execution_time': config.max_execution_seconds}
            if workload['primitive'] == 'sampler':
                primitive = SamplerV2(mode=backend, options=options)
                pubs = native
            else:
                primitive = EstimatorV2(mode=backend, options={**options, 'default_shots': config.shots, 'resilience_level': 0})
                # Observable layout must match the ISA circuit's physical layout.
                observable = workload['observable'].apply_layout(native[0].layout)
                pubs = [(native[0], observable)]
            context.update(status='SUBMITTING', submitted_epoch=time(), submitted_at=datetime.now(timezone.utc).isoformat())
            save(context)
            submitted = True  # Once entering SDK submission, receipt may be uncertain.
            job = primitive.run(pubs, shots=config.shots) if workload['primitive'] == 'sampler' else primitive.run(pubs)
            context.update(job_id=job.job_id(), status='SUBMITTED')
            save(context)
            return public(context)
        except Exception as error:
            context['status'] = 'SUBMISSION_UNCERTAIN' if submitted else 'PREPARATION_FAILED'
            save(context)
            if submitted:
                raise ValueError('Submission did not return a confirmed job ID. Check IBM workloads before another run. Recover this run ID; it will not be submitted twice.') from None
            if isinstance(error, ValueError):
                raise
            raise ValueError('Hardware preparation failed; no job submitted. Check optional workflow dependencies and IBM configuration.') from None


def poll(key):
    context = load(key)
    if not context.get('job_id') or context.get('result'):
        return public(context)
    try:
        job = runtime_service().job(context['job_id'])
        status = job.status()
        context['status'] = status.name if hasattr(status, 'name') else str(status)
        if context['status'] == 'DONE':
            results = job.result()
            if context['primitive'] == 'sampler':
                sweeps = []
                for index, item in enumerate(results):
                    counts = {bits.replace(' ', ''): int(n) for bits, n in item.data.meas.get_counts().items()}
                    logical = context['circuits'][index]['logical_qubits']
                    if not counts or any(len(bits) != logical or set(bits)-{'0','1'} or n <= 0 for bits, n in counts.items()):
                        raise ValueError('Unexpected measurement shape.')
                    sweeps.append({'counts': counts, **decode_measurements(context['decoding'], counts)})
                chosen = min(sweeps, key=lambda row: row.get('sampled_expected_penalized_cost',
                    row['best_sampled']['objective'] if row['best_sampled'] else float('inf')))
                result = {'parameter_results': sweeps, 'selected': chosen, 'total_shots': sum(row['shots'] for row in sweeps)}
            else:
                electronic = float(np.asarray(results[0].data.evs).reshape(-1)[0])
                stds = getattr(results[0].data, 'stds', None)
                std = None if stds is None else float(np.asarray(stds).reshape(-1)[0])
                if not np.isfinite(electronic) or (std is not None and not np.isfinite(std)):
                    raise ValueError('Nonfinite hardware estimate.')
                details = context['decoding']
                result = {**details, 'electronic_energy_hartree': electronic,
                    'total_molecular_energy_hartree': electronic+details['nuclear_repulsion_hartree'],
                    'reported_standard_error_hartree': std,
                    'note': 'Hardware expectation at locally optimized VQE parameters; no adaptive hardware VQE or full potential-energy scan. Noise may cause particle-sector leakage.'}
            try:
                result['quantum_usage_seconds'] = job.usage()
            except Exception:
                result['quantum_usage_seconds'] = None
            result.update(provenance='hardware', submission_to_retrieval_seconds=time()-context['submitted_epoch'])
            context['result'] = result
        save(context)
        return public(context)
    except Exception:
        raise ValueError('Unable to retrieve/decode this IBM job. Check IBM workloads and recover status; refresh never submits a job.') from None


def cancel(key):
    context = load(key)
    if not context.get('job_id'):
        raise ValueError('No confirmed job ID; inspect IBM workloads if submission was uncertain.')
    try:
        runtime_service().job(context['job_id']).cancel()
    except Exception:
        raise ValueError('Cancellation not confirmed; inspect IBM workloads. Consumed runtime cannot be refunded.') from None
    return poll(key)


def invoke(function, *args):
    try:
        return function(*args)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ImportError:
        raise HTTPException(status_code=503, detail='Install the optional QPU/workflow dependencies on the backend.') from None


@router.post('/run')
def run(config: HardwareRun):
    return invoke(start, config)


@router.get('/backends')
def backends():
    return invoke(available_backends)


@router.get('/jobs/{key}')
def status(key: str):
    return invoke(poll, key)


@router.post('/jobs/{key}/cancel')
def cancel_job(key: str):
    return invoke(cancel, key)
