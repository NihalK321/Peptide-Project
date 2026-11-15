import { useState } from 'react'
import { Button, Panel } from '../../components/ui'
import { downloadSequenceFile } from '../../services/sequenceDesign'
import type { useHardwareExecution } from './useHardwareExecution'
import { hardwareApi } from '../../services/hardware'

export function HardwareExecutionControl({ execution, disabled = false }: { execution: ReturnType<typeof useHardwareExecution>; disabled?: boolean }) {
  const { enabled, settings, job, recoveryId, busy, error } = execution
  const [controlError, setControlError] = useState('')
  const [backends, setBackends] = useState<{ name: string; qubits: number }[] | null>(null)
  const [loadingBackends, setLoadingBackends] = useState(false)
  async function discoverBackends() {
    setLoadingBackends(true); setControlError(''); setBackends(null)
    try { setBackends((await hardwareApi.backends()).backends) }
    catch (reason) { setControlError(reason instanceof Error ? reason.message : 'IBM backend discovery failed.') }
    finally { setLoadingBackends(false) }
  }
  async function action(work: () => Promise<unknown>) {
    try { setControlError(''); await work() } catch (reason) { setControlError(reason instanceof Error ? reason.message : 'Hardware request failed.') }
  }
  return <Panel className="space-y-3 border-blue-200 p-4" aria-label="Quantum execution target">
    <label className="flex items-start gap-2 text-sm font-semibold"><input aria-label="Use IBM quantum computer (QPU)" type="checkbox" checked={enabled} disabled={disabled || busy} onChange={(event) => execution.setEnabled(event.target.checked)} /><span>Use IBM quantum computer (QPU)</span></label>
    <p className="text-xs leading-5 text-slate-600">{enabled ? 'Clicking Run submits a hardware job and consumes IBM runtime. Chemistry and classical calculations stay local. Existing small optimizers fit parameters locally before hardware measurement; larger modes use the displayed starting angles or angle sweep.' : 'Unchecked: keep the existing local workflow. Checking the box alone never submits a job.'}</p>
    {enabled && <fieldset disabled={disabled || busy} className="grid min-w-0 gap-3 md:grid-cols-3">
      <label className="research-label">IBM backend name<input aria-label="QPU backend name" className="research-input mt-1" placeholder="Backend available to your IBM account" value={settings.backend_name} onChange={(event) => execution.setSettings({ ...settings, backend_name: event.target.value })} /></label>
      <label className="research-label">Hardware shots<input aria-label="Hardware shots" className="research-input mt-1" type="number" min={128} max={1024} step={1} value={settings.shots} onChange={(event) => execution.setSettings({ ...settings, shots: Number(event.target.value) })} /></label>
      <label className="research-label">Job execution cap (seconds)<input aria-label="Hardware execution cap" className="research-input mt-1" type="number" min={10} max={180} step={1} value={settings.max_execution_seconds} onChange={(event) => execution.setSettings({ ...settings, max_execution_seconds: Number(event.target.value) })} /></label>
      <div className="space-y-2 md:col-span-3"><Button variant="secondary" disabled={loadingBackends} onClick={() => void discoverBackends()}>{loadingBackends ? 'Loading IBM backends...' : 'Load my IBM backends'}</Button><p className="text-xs text-slate-600">Uses the account configured in the running Python backend. Listing computers does not consume QPU runtime.</p>{backends && (backends.length ? <label className="research-label block">Available IBM quantum computers<select aria-label="Available IBM quantum computers" className="research-select mt-1" value={backends.some((backend) => backend.name === settings.backend_name) ? settings.backend_name : ''} onChange={(event) => execution.setSettings({ ...settings, backend_name: event.target.value })}><option value="" disabled>Select a backend your account can access</option>{backends.map((backend) => <option key={backend.name} value={backend.name}>{backend.name} · {backend.qubits} qubits</option>)}</select></label> : <p role="status" className="text-xs text-amber-900">No operational physical QPUs were returned for the server account. Check the IBM instance and region associated with that account.</p>)}</div>
      <p className="text-xs leading-5 text-slate-600 md:col-span-3">Configure the IBM account once on the backend and enable PEPPERQ_ENABLE_QPU=1. Backend/shots/cap settings are reused across pages. Sampler shots are per circuit; for HeH+ they are requested shots per measurement basis, not total job usage. The cap does not represent remaining allowance.</p>
    </fieldset>}
    {busy && <p role="status" className="text-sm text-blue-900">Preparing or contacting IBM. Do not start another run if the response is interrupted; recover this run ID first.</p>}
    {(error || controlError) && <p role="alert" className="text-sm text-red-800">{error || controlError}</p>}
    {job && <div className="space-y-2 rounded border p-3 text-sm"><p>Hardware run snapshot: <strong>{job.status}</strong> · {job.backend_name}{job.job_id && <> · IBM job <code className="break-all">{job.job_id}</code></>}</p><p>{job.notice}</p>{job.warm_start && <p>{job.warm_start.method}. {job.warm_start.note}</p>}{job.circuits && <p>{job.circuits.length} circuit(s); {job.circuits[0].logical_qubits} logical qubits; routed depth {job.circuits[0].depth}.</p>}
      {job.result && <div className="space-y-2"><p className="font-semibold text-blue-900">Actual IBM hardware result</p>{job.result.selected && <><p>Best observed: <code className="break-all">{job.result.selected.best_sampled?.sequence ?? job.result.selected.best_sampled?.candidate_ids?.join(', ') ?? job.result.selected.best_sampled?.bitstring ?? 'No feasible sample'}</code>{job.result.selected.best_sampled && <> · objective {job.result.selected.best_sampled.objective.toFixed(6)}</>}</p><p>{job.result.selected.feasible_shots}/{job.result.selected.shots} feasible shots in selected circuit; {job.result.total_shots} total hardware shots across circuits.</p></>}{job.result.total_molecular_energy_hartree !== undefined && <p>Total molecular energy: {job.result.total_molecular_energy_hartree.toFixed(8)} Ha; reported standard error {job.result.reported_standard_error_hartree?.toExponential(2) ?? 'unavailable'} Ha. {job.result.note}</p>}<p>QPU usage: {job.result.quantum_usage_seconds === null ? 'unavailable' : `${job.result.quantum_usage_seconds.toFixed(3)} s`}; submission-to-retrieval {job.result.submission_to_retrieval_seconds.toFixed(1)} s (includes queue/polling delay). No speedup inferred.</p></div>}
      <Button variant="secondary" onClick={() => downloadSequenceFile(JSON.stringify(job, null, 2), 'ibm_hardware_result.json', 'application/json')}>Download hardware job / result</Button>
    </div>}
    {(enabled || recoveryId || job) && <div className="space-y-2"><label className="research-label block">Hardware run ID<input aria-label="Hardware run ID" className="research-input mt-1 font-mono" value={recoveryId} onChange={(event) => execution.setRecoveryId(event.target.value)} /></label><div className="flex flex-wrap gap-3"><Button variant="secondary" disabled={busy || !recoveryId} onClick={() => void action(execution.refresh)}>Refresh / recover hardware run</Button><Button variant="ghost" disabled={busy || !job?.job_id || ['DONE','CANCELLED','ERROR'].includes(job.status)} onClick={() => void action(execution.cancel)}>Cancel hardware job</Button></div></div>}
  </Panel>
}
