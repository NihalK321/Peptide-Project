"""Explicit, bounded IBM Runtime jobs. Importing this module never connects.

Prepared ISA circuits and request context survive backend restarts in .cache.
Credentials stay in the server environment or Qiskit's saved account.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from time import perf_counter, time
from uuid import UUID, uuid4

import numpy as np
from pydantic import Field
from qiskit import qpy
from qiskit.circuit import ParameterVector
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from ..schema import Model
from .scalable_choices import (ScalableChoiceRequest, build_circuit, classical_search,
    compile_choices, preview_scalable, summarize_counts, reference_quality)

STORE = Path(__file__).resolve().parents[2]/'.cache'/'pepperq-qpu'
LOCK = Lock()


class PrepareQPU(Model):
    design: ScalableChoiceRequest
    backend_name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    max_execution_seconds: int = Field(default=60, ge=10, le=180, strict=True)


class SubmitQPU(Model):
    prepared_id: str
    confirm_runtime: bool = False


def runtime_service():
    if os.getenv('PEPPERQ_ENABLE_QPU') != '1':
        raise ValueError("QPU access is disabled. Configure the server account and set PEPPERQ_ENABLE_QPU=1, then restart the backend. Local runs and exports remain available.")
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService
        token = os.getenv('QISKIT_IBM_TOKEN')
        if token:
            arguments = dict(channel='ibm_quantum_platform', token=token)
            if os.getenv('QISKIT_IBM_INSTANCE'):
                arguments['instance'] = os.environ['QISKIT_IBM_INSTANCE']
            return QiskitRuntimeService(**arguments)
        return QiskitRuntimeService()
    except Exception as error:
        # SDK exception text can include account or connection details.
        raise ValueError("IBM Runtime connection failed. Check the server's SDK installation, saved account or environment credentials and instance access.") from None


def identifier(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid prepared-job identifier.") from None


def save_context(key, context):
    STORE.mkdir(parents=True, exist_ok=True)
    target = STORE/f'{identifier(key)}.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(context, allow_nan=False), encoding='utf-8')
    temporary.replace(target)


def load_context(key):
    try:
        return json.loads((STORE/f'{identifier(key)}.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ValueError("Prepared job not found on this backend. Prepare the circuit again.") from None


def prepare_qpu(config):
    preparation_started = perf_counter()
    model = compile_choices(config.design)
    # Read-only cloud connection and compilation: no Sampler.run or QPU job.
    if model['logical_gate_count'] > 15000:
        raise ValueError("This circuit exceeds the hardware-preflight budget of 15,000 logical gates. Preview/export remains available; reduce choices/positions before hardware preparation.")
    service = runtime_service()
    try:
        backend = service.backend(config.backend_name)
        if backend.num_qubits < model['qubits']:
            raise ValueError("The selected backend has too few qubits.")
        if backend.configuration().simulator or not backend.status().operational:
            raise ValueError("Select an operational, physical IBM backend.")
    except ValueError:
        raise
    except Exception:
        raise ValueError("Unable to inspect the selected backend; check its name and account access.") from None
    theta = ParameterVector('theta', 2*config.design.layers)
    circuit = build_circuit(model, theta)
    circuit.measure_all()
    started = perf_counter()
    try:
        isa = generate_preset_pass_manager(backend=backend, optimization_level=1,
            seed_transpiler=config.design.seed).run(circuit)
    except Exception:
        raise ValueError("Backend-specific circuit compilation failed. Try a smaller problem or another operational backend.") from None
    transpilation_seconds = perf_counter()-started
    two_qubit = sum(1 for item in isa.data if item.operation.num_qubits == 2)
    if two_qubit > 20000 or isa.depth() > 20000:
        raise ValueError("Routed circuit exceeds the prototype hardware limit (20,000 two-qubit gates or depth). Reduce the design; qubit count alone is insufficient.")
    # Keep bindings in the transpiled circuit's actual parameter order.
    names = [str(parameter) for parameter in isa.parameters]
    expected = {str(parameter): i for i, parameter in enumerate(theta)}
    if any(name not in expected for name in names):
        raise ValueError("Unexpected parameter mapping after compilation.")
    bindings = [[values[expected[name]] for name in names] for values in config.design.parameter_sets]
    key = str(uuid4())
    STORE.mkdir(parents=True, exist_ok=True)
    with (STORE/f'{key}.qpy').open('wb') as stream:
        qpy.dump(isa, stream)
    context = {"prepared_id": key, "created_at": datetime.now(timezone.utc).isoformat(),
        "created_epoch": time(), "status": "PREPARED", "backend_name": config.backend_name,
        "design": config.design.model_dump(), "max_execution_seconds": config.max_execution_seconds,
        "parameter_bindings": bindings, "parameters": config.design.parameter_sets,
        "preview": preview_scalable(config.design, model), "classical": classical_search(model, config.design),
        "circuit": {"logical_qubits": model['qubits'], "physical_qubits": isa.num_qubits,
            "depth": isa.depth(), "two_qubit_gates": two_qubit, "gate_counts": dict(isa.count_ops()),
            "transpilation_seconds": transpilation_seconds},
        "requested_total_shots": len(bindings)*config.design.shots,
        "notice": "Prepared only: no quantum job submitted. The execution cap is not a usage estimate or a guarantee of remaining account allowance."}
    context['preparation_wall_seconds'] = perf_counter()-preparation_started
    save_context(key, context)
    return public_context(context)


def public_context(context):
    return {key: value for key, value in context.items() if key not in ('parameter_bindings', 'created_epoch')}


def submit_qpu(config):
    if not config.confirm_runtime:
        raise ValueError("Explicitly confirm that submitting this job consumes IBM QPU runtime.")
    key = identifier(config.prepared_id)
    # Serialize local submission and mark its intent before calling IBM. An
    # interrupted submission is never retried automatically (avoids double spend).
    with LOCK:
        context = load_context(key)
        if context['status'] != 'PREPARED':
            raise ValueError("This preparation has already been submitted or attempted. Refresh its status; it cannot be submitted twice.")
        if time()-context['created_epoch'] > 3600:
            raise ValueError("Preparation expired after one hour. Prepare again for current backend calibration.")
        service = runtime_service()
        try:
            backend = service.backend(context['backend_name'])
            if not backend.status().operational:
                raise ValueError("Backend is not operational; prepare again later.")
            with (STORE/f'{key}.qpy').open('rb') as stream:
                isa = qpy.load(stream)[0]
        except ValueError:
            raise
        except Exception:
            raise ValueError("Unable to load the prepared circuit or backend. No job was submitted.") from None
        from qiskit_ibm_runtime import SamplerV2
        sampler = SamplerV2(mode=backend, options={"max_execution_time": context['max_execution_seconds']})
        context.update(status='SUBMITTING', submitted_epoch=time(), submitted_at=datetime.now(timezone.utc).isoformat())
        save_context(key, context)
        try:
            # One parameter-broadcast PUB: one ISA circuit, bounded angle sets.
            job = sampler.run([(isa, np.asarray(context['parameter_bindings']), context['design']['shots'])])
            context.update(job_id=job.job_id(), status='SUBMITTED')
        except Exception:
            context['status'] = 'SUBMISSION_UNCERTAIN'
            save_context(key, context)
            raise ValueError("Submission did not return a job ID. Check IBM's workload dashboard before trying another preparation; the service may have received the job.") from None
        save_context(key, context)
        return public_context(context)


def poll_qpu(key):
    context = load_context(key)
    if 'job_id' not in context or context['status'] == 'DONE':
        return public_context(context)
    service = runtime_service()
    try:
        job = service.job(context['job_id'])
        status = job.status()
        if hasattr(status, 'name'):
            status = status.name
        context['status'] = str(status)
        if status == 'DONE':
            result = job.result()
            request = ScalableChoiceRequest(**context['design'])
            model = compile_choices(request)
            sweeps = []
            for i, parameters in enumerate(context['parameters']):
                counts = result[0].data.meas.get_counts(loc=(i,))
                normalized = {bits.replace(' ', ''): int(n) for bits, n in counts.items()}
                row = summarize_counts(model, request, normalized)
                row['reference_quality'] = reference_quality(model, request, normalized, context['classical'])
                sweeps.append({"parameters": parameters, "counts": normalized, **row})
            best = min(sweeps, key=lambda row: row['sampled_expected_penalized_cost'])
            elapsed = time()-context['submitted_epoch']
            try:
                usage = job.usage()
            except Exception:
                usage = None
            context['result'] = {"provenance": "hardware", "execution_backend": context['backend_name'],
                "parameter_sweep": sweeps, "selected_parameter_result": best,
                "selection_method": "Lowest sampled mean penalized energy across a bounded, nonadaptive parameter sweep. No independent holdout verification; selection can overfit shot noise.",
                "total_shots": sum(row['shots'] for row in sweeps),
                "quantum_usage_seconds": usage, "submission_to_retrieval_seconds": elapsed,
                "comparison": "Compare all sweep shots, classical/compilation time, quality and queue-inclusive wall time. QPU usage alone is not end-to-end runtime or proof of speedup.",
                "sampled_minus_classical_objective": None if best['best_sampled'] is None else best['best_sampled']['objective']-context['classical']['best']['objective']}
    except Exception:
        raise ValueError("Unable to retrieve or decode this IBM workload. Check the workload dashboard and retry status; no new job is submitted by refresh.") from None
    save_context(key, context)
    return public_context(context)


def cancel_qpu(key):
    context = load_context(key)
    if 'job_id' not in context:
        raise ValueError("There is no job ID to cancel; check IBM's dashboard if submission was uncertain.")
    try:
        runtime_service().job(context['job_id']).cancel()
    except Exception:
        raise ValueError("Cancellation was not confirmed. Check the workload dashboard; already consumed runtime cannot be recovered.") from None
    return poll_qpu(key)
