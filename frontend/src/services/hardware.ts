import { ApiClient, isApiClientError } from '../api/client'

export type HardwareWorkflow = 'sequence' | 'sequence_multi' | 'sequence_large' | 'scalable' | 'blend' | 'torsion' | 'heh'
export interface HardwareJob {
  request_id: string
  workflow: HardwareWorkflow
  backend_name: string
  status: string
  job_id: string | null
  settings: unknown
  shots_requested: number
  max_execution_seconds: number
  warm_start?: { method: string; parameters: number[] | number[][]; note: string }
  circuits?: { logical_qubits: number; physical_qubits: number; depth: number; two_qubit_gates: number }[]
  classical_reference?: unknown
  notice: string
  result?: {
    provenance: 'hardware'
    total_shots?: number
    quantum_usage_seconds: number | null
    submission_to_retrieval_seconds: number
    selected?: { best_sampled: { sequence?: string; bitstring?: string; candidate_ids?: string[]; objective: number; energy_kcal_mol?: number } | null; shots: number; feasible_shots: number; invalid_shots: number }
    electronic_energy_hartree?: number
    total_molecular_energy_hartree?: number
    reported_standard_error_hartree?: number | null
    note?: string
  }
}
export interface HardwareSettings { backend_name: string; shots: number; max_execution_seconds: number }
const client = new ApiClient()
async function request<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  try { return await client.request<T>(`hardware/${path}`, { method, body }) }
  catch (error) {
    if (isApiClientError(error) && error.detail && typeof error.detail === 'object' && 'detail' in error.detail && Array.isArray(error.detail.detail)) {
      throw new Error(error.detail.detail.map((entry: { loc?: (string | number)[]; msg?: string }) => `${entry.loc?.slice(1).join('/')}: ${entry.msg}`).join('; '))
    }
    throw error
  }
}
export const hardwareApi = {
  backends: () => request<{ backends: { name: string; qubits: number }[]; notice: string }>('backends', undefined, 'GET'),
  run: (workflow: HardwareWorkflow, settings: unknown, hardware: HardwareSettings, request_id: string) => request<HardwareJob>('run', { workflow, settings, ...hardware, request_id, use_qpu: true }),
  status: (id: string) => request<HardwareJob>(`jobs/${encodeURIComponent(id)}`, undefined, 'GET'),
  cancel: (id: string) => request<HardwareJob>(`jobs/${encodeURIComponent(id)}/cancel`, {}),
}
