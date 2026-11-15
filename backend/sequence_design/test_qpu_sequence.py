"""Runtime orchestration with local doubles only: never consume QPU time."""

from types import SimpleNamespace
import numpy as np
import pytest
from qiskit.primitives.containers import BitArray

from . import qpu_sequence as qpu
from .scalable_choices import ScalableChoiceRequest
from .test_scalable_choices import config


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(qpu, 'STORE', tmp_path)
    backend = SimpleNamespace(num_qubits=127, configuration=lambda: SimpleNamespace(simulator=False),
                              status=lambda: SimpleNamespace(operational=True))
    class Job:
        cancelled = False
        def job_id(self): return 'test-job-id'
        def status(self): return 'CANCELLED' if self.cancelled else 'DONE'
        def usage(self): return 2.5
        def cancel(self): self.cancelled = True
        def result(self):
            counts = BitArray.from_counts([{'0000': 100, '0001': 28}, {'0011': 128}, {'0010': 128}], num_bits=4)
            return [SimpleNamespace(data=SimpleNamespace(meas=counts))]
    job = Job()
    service = SimpleNamespace(backend=lambda name: backend, job=lambda key: job)
    monkeypatch.setattr(qpu, 'runtime_service', lambda: service)
    monkeypatch.setattr(qpu, 'generate_preset_pass_manager', lambda **kw: SimpleNamespace(run=lambda circuit: circuit))
    calls = []
    class Sampler:
        def __init__(self, mode, options):
            assert mode is backend and options['max_execution_time'] == 60
        def run(self, pubs):
            calls.append(pubs)
            return job
    monkeypatch.setattr('qiskit_ibm_runtime.SamplerV2', Sampler)
    return SimpleNamespace(calls=calls, backend=backend, job=job)


def prepare():
    return qpu.prepare_qpu(qpu.PrepareQPU(design=ScalableChoiceRequest(**config()), backend_name='ibm_test'))


def test_prepare_never_submits_and_qpy_persists(runtime):
    report = prepare()
    assert not runtime.calls and report['status'] == 'PREPARED'
    assert report['requested_total_shots'] == 384
    assert (qpu.STORE/f"{report['prepared_id']}.qpy").is_file()
    assert qpu.poll_qpu(report['prepared_id'])['status'] == 'PREPARED'


def test_confirmation_duplicate_protection_bindings_and_real_bitarray(runtime):
    report = prepare()
    key = report['prepared_id']
    with pytest.raises(ValueError, match='confirm'):
        qpu.submit_qpu(qpu.SubmitQPU(prepared_id=key))
    submitted = qpu.submit_qpu(qpu.SubmitQPU(prepared_id=key, confirm_runtime=True))
    assert submitted['job_id'] == 'test-job-id' and len(runtime.calls) == 1
    circuit, bindings, shots = runtime.calls[0][0]
    assert shots == 128
    np.testing.assert_allclose(bindings, [[1, .3], [2, .6], [3, .9]])
    assert [str(p) for p in circuit.parameters] == ['theta[0]', 'theta[1]']
    with pytest.raises(ValueError, match='twice'):
        qpu.submit_qpu(qpu.SubmitQPU(prepared_id=key, confirm_runtime=True))
    result = qpu.poll_qpu(key)
    assert result['status'] == 'DONE' and result['result']['provenance'] == 'hardware'
    assert result['result']['total_shots'] == 384 and result['result']['quantum_usage_seconds'] == 2.5
    assert result['result']['parameter_sweep'][1]['best_sampled'] is None
    assert result['result']['parameter_sweep'][1]['invalid_shots'] == 128
    assert len(runtime.calls) == 1
    assert qpu.poll_qpu(key)['result'] == result['result']


def test_expired_preparation_and_recovery(runtime):
    report = prepare()
    key = report['prepared_id']
    context = qpu.load_context(key)
    context['created_epoch'] -= 3601
    qpu.save_context(key, context)
    with pytest.raises(ValueError, match='expired'):
        qpu.submit_qpu(qpu.SubmitQPU(prepared_id=key, confirm_runtime=True))
    assert not runtime.calls


def test_submission_failure_not_retried_and_sensitive_error_hidden(runtime, monkeypatch):
    report = prepare()
    class FailingSampler:
        def __init__(self, **kwargs): pass
        def run(self, pubs): raise RuntimeError('secret credential must not be returned')
    monkeypatch.setattr('qiskit_ibm_runtime.SamplerV2', FailingSampler)
    with pytest.raises(ValueError, match='dashboard') as error:
        qpu.submit_qpu(qpu.SubmitQPU(prepared_id=report['prepared_id'], confirm_runtime=True))
    assert 'secret' not in str(error.value)
    assert qpu.load_context(report['prepared_id'])['status'] == 'SUBMISSION_UNCERTAIN'
    with pytest.raises(ValueError, match='twice'):
        qpu.submit_qpu(qpu.SubmitQPU(prepared_id=report['prepared_id'], confirm_runtime=True))


def test_capacity_gate_limit_and_cancel(runtime):
    runtime.backend.num_qubits = 2
    with pytest.raises(ValueError, match='few qubits'):
        prepare()
    runtime.backend.num_qubits = 127
    request = ScalableChoiceRequest(**config('ACDEFGHIKLMNPQRSTVWY', 10))
    with pytest.raises(ValueError, match='preflight budget'):
        qpu.prepare_qpu(qpu.PrepareQPU(design=request, backend_name='ibm_test'))
    report = prepare()
    key = report['prepared_id']
    qpu.submit_qpu(qpu.SubmitQPU(prepared_id=key, confirm_runtime=True))
    assert qpu.cancel_qpu(key)['status'] == 'CANCELLED'
    assert len(runtime.calls) == 1


def test_invalid_storage_identifier():
    with pytest.raises(ValueError, match='identifier'):
        qpu.load_context('../../somewhere')
