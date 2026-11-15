import { ApiClient, isApiClientError } from '../api/client'

export const residueCodes = 'ACDEFGHIKLMNPQRSTVWY'
export const residueNames = ['Alanine', 'Cysteine', 'Aspartic acid', 'Glutamic acid', 'Phenylalanine', 'Glycine', 'Histidine', 'Isoleucine', 'Lysine', 'Leucine', 'Methionine', 'Asparagine', 'Proline', 'Glutamine', 'Arginine', 'Serine', 'Threonine', 'Valine', 'Tryptophan', 'Tyrosine']

export interface SequenceGoals {
  ph: number
  target_charge: number
  charge_weight: number
  hydropathy_min: number
  hydropathy_max: number
  hydropathy_weight: number
  adjacent_repeat_weight: number
}
export interface SequenceRequest {
  length: number
  template_sequence: string | null
  allowed_amino_acids: string[]
  excluded_amino_acids: string[]
  required_amino_acids: string[]
  positions: { position: number; choices: string[] }[]
  max_mutations: number | null
  goals: SequenceGoals
  layers: number
  max_iterations: number
  shots: number
  seed: number
}
export interface SequenceProperties {
  length: number
  charge: number
  hydropathy: number
  mass_da: number
  isoelectric_point: number
}
export interface SequenceCandidate {
  bitstring: string
  sequence: string
  properties: SequenceProperties
  objective: number
  components: { charge: number; hydropathy: number; adjacent_repeats: number }
  component_weight_sum: number
  charge_error_e: number
  hydropathy_distance: number
  adjacent_repeat_count: number
  mutation_count: number | null
  missing_required_amino_acids: string[]
  mutation_budget_excess: number
  constraint_violation: number
  feasible: boolean
  penalized_objective: number
  probability: number
  count: number
  observed_frequency: number
}
export interface SequencePreview {
  contract_version: string
  provenance: string
  request: SequenceRequest
  variables: { qubit: number; position: number; choices: string[] }[]
  domains: string[][]
  qubits: number
  state_count: number
  feasible_state_count: number
  cost_representation: string
  cost_polynomial_degree: number
  template_properties: SequenceProperties | null
  methods: Record<string, string>
  limitations: string[]
}
export interface SequenceResult {
  contract_version: string
  experiment_id: string
  created_at: string
  provenance: 'simulated'
  execution_backend: string
  status: string
  request: SequenceRequest
  variables: SequencePreview['variables']
  domains: string[][]
  best_sampled: SequenceCandidate | null
  candidate_sequences: SequenceCandidate[]
  classical_reference: SequenceCandidate
  template_properties: SequenceProperties | null
  benchmark: { state_count: number; feasible_state_count: number; qubits: number; sampled_objective_gap: number | null; optimum_probability: number; uniform_optimum_probability: number; feasible_probability: number; feasible_shots: number; infeasible_shots: number; uniform_feasible_probability: number; optimal_sequences_count: number }
  cost: { degree: number; representation: string; penalty: number; reconstruction_max_error: number; qubo: { constant: number; matrix_upper_triangle: number[][]; convention: string } | null; terms: { mask: number; variables: number[]; coefficient: number }[]; energies_in_bitstring_order: number[] }
  validation: { checked_states: number; cost_reconstruction_max_error: number; all_feasible_energies_below_all_infeasible: boolean }
  history: { evaluation: number; expected_penalized_objective: number; feasible_probability: number }[]
  parameters: number[]
  circuit: { qasm: string; text: string; depth: number; gate_counts: Record<string, number> }
  optimizer: { method: string; evaluations: number; converged: boolean; message: string }
  states: SequenceCandidate[]
  elapsed_seconds: number
  methods: Record<string, string>
  limitations: string[]
}

const client = new ApiClient()
async function post<T>(path: string, body: unknown): Promise<T> {
  try { return await client.request<T>(`sequence-design/${path}`, { method: 'POST', body }) }
  catch (error) {
    if (isApiClientError(error) && typeof error.detail === 'object' && error.detail !== null && 'detail' in error.detail && Array.isArray(error.detail.detail)) {
      throw new Error(error.detail.detail.map((item: { loc?: (string | number)[]; msg?: string }) => `${item.loc?.slice(1).join(' / ') || 'Input'}: ${item.msg || 'Invalid value'}`).join('; '))
    }
    throw error
  }
}
export const sequenceDesign = {
  preview: (request: SequenceRequest) => post<SequencePreview>('preview', request),
  optimize: (request: SequenceRequest) => post<SequenceResult>('optimize', request),
  structure: (sequence: string) => post<{ sequence: string; svg: string; provenance: string; model: string }>('structure', { sequence }),
}

export function requestSignature(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item)
}
export function downloadSequenceFile(content: string, filename: string, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = filename; anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
