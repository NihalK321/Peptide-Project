import { ApiClient, isApiClientError } from '../api/client'
import type { SequenceCandidate, SequenceGoals } from './sequenceDesign'

export interface ScalableRequest {
  length: number
  template_sequence: string
  positions: { position: number; choices: string[] }[]
  goals: SequenceGoals
  layers: number
  shots: number
  seed: number
  max_iterations: number
  training_shots: number
  bond_dimension: number
  classical_seconds: number
  parameter_sets: number[][]
}
export interface ScalablePreview {
  contract_version: string
  request: ScalableRequest
  qubits: number
  editable_positions: number
  valid_sequence_count: string
  encoded_state_count: string
  uniform_valid_probability: number
  cost_terms: number
  maximum_pauli_weight: number
  logical_gate_count: number
  formulation_seconds: number
  penalty: number
  validation: { maximum_error: number; checked_assignments: number; method: string }
  limitations: string[]
}
export interface ClassicalSearch {
  best: SequenceCandidate
  method: string
  exact_optimum_available: boolean
  evaluations: number
  elapsed_seconds: number
  budget_seconds: number
  seed: number
  history: { evaluation: number; seconds: number; objective: number }[]
}
export interface ShotSummary {
  best_sampled: SequenceCandidate | null
  candidate_sequences: SequenceCandidate[]
  shots: number
  feasible_shots: number
  invalid_shots: number
  observed_feasible_frequency: number
  sampled_expected_penalized_cost: number
  reference_quality?: { target_is_exact_optimum: boolean; matched_or_better_shots: number; total_shots: number; observed_frequency: number; wilson_95_interval: number[]; interval_assumption: string }
}
export interface ScalableRun extends ScalablePreview {
  provenance: 'prepared' | 'simulated_approximate'
  execution_backend: string
  parameters: number[]
  summary: ShotSummary | null
  classical: ClassicalSearch
  circuit: { qasm: string; depth: number; gate_counts: Record<string, number> }
  quantum_workflow_seconds: number | null
  comparison: string
  elapsed_seconds: number
}
export interface QPUJob {
  prepared_id: string
  status: string
  job_id?: string
  backend_name: string
  design: ScalableRequest
  max_execution_seconds: number
  preview: ScalablePreview
  classical: ClassicalSearch
  circuit: { logical_qubits: number; physical_qubits: number; depth: number; two_qubit_gates: number; transpilation_seconds: number }
  requested_total_shots: number
  notice: string
  result?: {
    provenance: 'hardware'
    selected_parameter_result: ShotSummary
    parameter_sweep: (ShotSummary & { parameters: number[] })[]
    total_shots: number
    quantum_usage_seconds: number | null
    submission_to_retrieval_seconds: number
    sampled_minus_classical_objective: number | null
    selection_method: string
    comparison: string
  }
}
const client = new ApiClient()
async function request<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  try { return await client.request<T>(`sequence-design/scalable/${path}`, { method, body }) }
  catch (error) {
    if (isApiClientError(error) && error.detail && typeof error.detail === 'object' && 'detail' in error.detail && Array.isArray(error.detail.detail)) {
      throw new Error(error.detail.detail.map((item: { loc?: (string | number)[]; msg?: string }) => `${item.loc?.slice(1).join('/')}: ${item.msg}`).join('; '))
    }
    throw error
  }
}
export const scalableSequence = {
  preview: (body: ScalableRequest) => request<ScalablePreview>('preview', body),
  run: (body: ScalableRequest) => request<ScalableRun>('optimize', body),
  export: (body: ScalableRequest) => request<ScalableRun>('export', body),
  prepare: (design: ScalableRequest, backend_name: string, max_execution_seconds: number) => request<QPUJob>('qpu/prepare', { design, backend_name, max_execution_seconds }),
  submit: (prepared_id: string) => request<QPUJob>('qpu/submit', { prepared_id, confirm_runtime: true }),
  status: (id: string) => request<QPUJob>(`qpu/jobs/${encodeURIComponent(id)}`, undefined, 'GET'),
  cancel: (id: string) => request<QPUJob>(`qpu/jobs/${encodeURIComponent(id)}/cancel`, {}),
}
