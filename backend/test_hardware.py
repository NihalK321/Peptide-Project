"""Shared QPU routing and recovery tests; every cloud call is a local double."""

from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp

from .api import app
from . import hardware as hw
from .hardware_workflows import build_workload, decode_measurements


def sequence_config():
    return {'length': 2, 'template_sequence': 'AA', 'positions': [{'position': 1, 'choices': ['A','K']}],
            'max_iterations': 10, 'shots': 128}


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(hw, 'STORE', tmp_path)
    backend = SimpleNamespace(num_qubits=127, status=lambda: SimpleNamespace(operational=True),
                              configuration=lambda: SimpleNamespace(simulator=False))
    class Job:
        cancelled = False
        def job_id(self): return 'local-test-job'
        def status(self): return 'CANCELLED' if self.cancelled else 'DONE'
        def cancel(self): self.cancelled = True
        def usage(self): return 1.25
        def result(self):
            if sampler_calls:
                counts = SimpleNamespace(get_counts=lambda: {'0': 100, '1': 28})
                return [SimpleNamespace(data=SimpleNamespace(meas=counts))]
            return [SimpleNamespace(data=SimpleNamespace(evs=np.array(-3.), stds=np.array(.02)))]
    job = Job()
    service = SimpleNamespace(backend=lambda name: backend, job=lambda key: job)
    monkeypatch.setattr(hw, 'runtime_service', lambda: service)
    monkeypatch.setattr(hw, 'generate_preset_pass_manager', lambda **kwargs: SimpleNamespace(run=lambda circuit: circuit))
    sampler_calls, estimator_calls = [], []
    class Sampler:
        def __init__(self, **kwargs): pass
        def run(self, pubs, shots): sampler_calls.append((pubs, shots)); return job
    class Estimator:
        def __init__(self, **kwargs):
            assert kwargs['options']['default_shots'] == 256
        def run(self, pubs): estimator_calls.append(pubs); return job
    monkeypatch.setattr('qiskit_ibm_runtime.SamplerV2', Sampler)
    monkeypatch.setattr('qiskit_ibm_runtime.EstimatorV2', Estimator)
    return SimpleNamespace(sampler=sampler_calls, estimator=estimator_calls, job=job)


def request(workflow='sequence', settings=None):
    return hw.HardwareRun(workflow=workflow, settings=sequence_config() if settings is None else settings,
        backend_name='ibm_test', use_qpu=True, request_id=str(uuid4()))


def test_real_sequence_adapter_sampler_idempotent_and_recovery(runtime):
    config = request()
    response = hw.start(config)
    assert response['status'] == 'SUBMITTED' and len(runtime.sampler) == 1
    assert 'decoding' not in response and 'local ideal-statevector' in response['warm_start']['method']
    assert hw.start(config)['job_id'] == response['job_id'] and len(runtime.sampler) == 1
    result = hw.poll(config.request_id)
    assert result['result']['provenance'] == 'hardware'
    assert result['result']['total_shots'] == 128
    assert result['result']['selected']['best_sampled']['count'] > 0
    assert 'probability' not in result['result']['selected']['best_sampled']
    assert hw.poll(config.request_id)['result'] == result['result']
    assert len(runtime.sampler) == 1


def test_heh_estimator_layout_energy_convention(runtime, monkeypatch):
    applied = []
    class Observable:
        def apply_layout(self, layout): applied.append(layout); return SparsePauliOp('Z')
    monkeypatch.setattr(hw, 'build_workload', lambda *args: {
        'circuits': [QuantumCircuit(1)], 'primitive': 'estimator', 'observable': Observable(),
        'warm_start': {'method': 'unit-test local fitted VQE'}, 'reference': {},
        'decoding': {'kind': 'heh', 'nuclear_repulsion_hartree': 1.,
                     'classical_electronic_energy_hartree': -3.1, 'classical_total_molecular_energy_hartree': -2.1}})
    config = request('heh', {'bond_distance_angstrom': 1})
    hw.start(config)
    result = hw.poll(config.request_id)['result']
    assert len(applied) == 1 and len(runtime.estimator) == 1 and not runtime.sampler
    assert result['electronic_energy_hartree'] == -3
    assert result['total_molecular_energy_hartree'] == -2
    assert result['reported_standard_error_hartree'] == .02


def test_disabled_service_does_not_fit_or_submit(monkeypatch):
    def disabled(): raise ValueError('QPU access disabled')
    monkeypatch.setattr(hw, 'runtime_service', disabled)
    monkeypatch.setattr(hw, 'build_workload', lambda *args: pytest.fail('Must not fit before checking enabled account'))
    with TestClient(app) as client:
        response = client.post('/api/v1/hardware/run', json=request().model_dump())
        assert response.status_code == 422 and 'disabled' in response.text


def test_checkbox_required_and_no_arbitrary_workflow():
    with TestClient(app) as client:
        body = request().model_dump()
        for change in ({'use_qpu': False}, {'workflow': 'arbitrary-python-function'}, {'shots': 100000}):
            assert client.post('/api/v1/hardware/run', json={**body, **change}).status_code == 422


def test_submission_uncertainty_and_atomic_claim(runtime, monkeypatch):
    class Failure:
        def __init__(self, **kwargs): pass
        def run(self, *args, **kwargs): raise RuntimeError('secret text')
    monkeypatch.setattr('qiskit_ibm_runtime.SamplerV2', Failure)
    config = request()
    with pytest.raises(ValueError, match='confirmed job ID') as error:
        hw.start(config)
    assert 'secret' not in str(error.value)
    assert hw.poll(config.request_id)['status'] == 'SUBMISSION_UNCERTAIN'
    assert hw.start(config)['status'] == 'SUBMISSION_UNCERTAIN'
    another = request()
    hw.path(another.request_id).with_suffix('.claim').touch()
    with pytest.raises(ValueError, match='already being prepared'):
        hw.start(another)


def test_cancel_and_reused_id_settings(runtime):
    config = request()
    hw.start(config)
    assert hw.cancel(config.request_id)['status'] == 'CANCELLED'
    modified = config.model_copy(update={'shots': 512})
    with pytest.raises(ValueError, match='different settings'):
        hw.start(modified)


@pytest.mark.parametrize('workflow,settings', [
    ('sequence_multi', {**sequence_config(), 'positions': [{'position': 1, 'choices': ['A','K','R']}]}),
    ('sequence_large', {**sequence_config(), 'goals': {'hydropathy_weight': 0}}),
    ('scalable', {**sequence_config(), 'goals': {'hydropathy_min': 0, 'hydropathy_max': 0}, 'classical_seconds': .1}),
    ('torsion', {'sequence': 'GA', 'torsion_count': 1, 'max_iterations': 10}),
])
def test_all_qaoa_adapters_generate_real_measured_circuits(workflow, settings):
    workload = build_workload(workflow, settings, 256)
    assert workload['primitive'] == 'sampler'
    circuit = workload['circuits'][0]
    assert circuit.num_qubits > 0 and circuit.num_parameters == 0
    counts = {'0'*circuit.num_qubits: 256}
    summary = decode_measurements(workload['decoding'], counts)
    assert summary['shots'] == 256
    assert summary['best_sampled']['count'] == 256


def test_blend_adapter_real_catalog_fixture(monkeypatch):
    records = [{'id': str(i), 'sequence': seq, 'name': seq, 'source': 'test', 'accession': str(i), 'source_url': 'https://example.org'}
               for i, seq in enumerate(['AA','AK','KR','GA'])]
    monkeypatch.setattr('backend.blends.api.get_blend_catalog', lambda: SimpleNamespace(load=lambda: (records, {})))
    workload = build_workload('blend', {'candidate_ids': ['0','1','2','3'], 'blend_size': 2, 'max_iterations': 10}, 256)
    summary = decode_measurements(workload['decoding'], {'0011': 128, '0000': 128})
    assert summary['shots'] == 256 and summary['invalid_shots'] == 128
    assert summary['best_sampled']['candidate_ids'] == ['0','1']


def test_no_feasible_measurement_never_uses_classical_answer():
    data = {'kind': 'rows', 'rows': {'00': {'feasible': False, 'objective': None}}}
    assert decode_measurements(data, {'00': 128})['best_sampled'] is None


def test_backend_discovery_is_read_only_and_returns_only_names_and_sizes(monkeypatch):
    filters = []
    def backends(**kwargs):
        filters.append(kwargs)
        return [SimpleNamespace(name='ibm_z', num_qubits=156), SimpleNamespace(name='ibm_a', num_qubits=127)]
    monkeypatch.setattr(hw, 'runtime_service', lambda: SimpleNamespace(backends=backends))
    with TestClient(app) as client:
        response = client.get('/api/v1/hardware/backends')
    assert response.status_code == 200
    assert response.json()['backends'] == [{'name': 'ibm_a', 'qubits': 127}, {'name': 'ibm_z', 'qubits': 156}]
    assert filters == [{'operational': True, 'simulator': False}]


def test_listing_errors_do_not_reveal_credentials(monkeypatch):
    def fail(**kwargs): raise RuntimeError('secret credential')
    monkeypatch.setattr(hw, 'runtime_service', lambda: SimpleNamespace(backends=fail))
    with pytest.raises(ValueError, match='instance') as error:
        hw.available_backends()
    assert 'secret' not in str(error.value)


def test_backend_lookup_and_status_errors_are_distinct(runtime, monkeypatch):
    def fail(*args, **kwargs): raise RuntimeError('sensitive SDK error')
    monkeypatch.setattr(hw, 'runtime_service', lambda: SimpleNamespace(backend=fail))
    with pytest.raises(ValueError, match='Load my IBM backends'):
        hw.start(request())
    monkeypatch.setattr(hw, 'runtime_service', lambda: SimpleNamespace(backend=lambda name: SimpleNamespace(status=fail)))
    with pytest.raises(ValueError, match='status could not be read'):
        hw.start(request())
    assert not runtime.sampler and not runtime.estimator
