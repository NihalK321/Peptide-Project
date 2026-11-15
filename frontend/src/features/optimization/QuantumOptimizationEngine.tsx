import { HardwareExecutionControl } from '../shared/HardwareExecution'
import { useHardwareExecution } from '../shared/useHardwareExecution'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Cpu, LoaderCircle, Play } from 'lucide-react'
import { Button, EmptyState, MetricCard, Panel, SectionHeading, StatusPill } from '../../components/ui'
import { blendResearch, loadLatestBlend, saveLatestBlend } from '../../services/blendResearch'
import type { BlendResult, QaoaExecution } from '../../services/blendResearch'
import { isWorkspacePersisted, matchingBlendResult, updateBlendWorkspace, validateBlendWorkspace } from '../../services/blendWorkspace'
import { BlendRunResults } from '../designer/BlendRunResults'
import { useBlendWorkspace } from '../shared/useBlendWorkspace'

const fields: { key: keyof QaoaExecution; label: string; min: number; max: number }[] = [
  { key: 'layers', label: 'QAOA layers', min: 1, max: 2 },
  { key: 'max_iterations', label: 'Maximum objective evaluations', min: 10, max: 120 },
  { key: 'shots', label: 'Simulated shots', min: 128, max: 8192 },
  { key: 'seed', label: 'Random seed', min: 0, max: 2147483647 },
]

function combinations(n: number, k: number) {
  if (!Number.isInteger(k) || k < 1 || k >= n) return 0
  let total = 1
  for (let i = 1; i <= k; i++) total = total * (n - i + 1) / i
  return Math.round(total)
}

export function QuantumOptimizationEngine() {
  const hardware = useHardwareExecution('blend')
  const draft = useBlendWorkspace()
  const { pool, goals, execution, blendSize } = draft
  const [result, setResult] = useState<BlendResult | null>(loadLatestBlend)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const problem = validateBlendWorkspace(draft)
  const resultMatches = result && !hardware.enabled ? matchingBlendResult(result, draft) : false

  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    if (problem) { setError(problem); return }
    setBusy(true); setError(null); setNote('')
    try {
      if (hardware.enabled) {
        await hardware.run('blend', { ...goals, candidate_ids: pool.map((candidate) => candidate.id), blend_size: blendSize, ...execution })
        setNote('IBM hardware job submitted. Refresh its status above; saved local results remain separate snapshots.')
        return
      }
      const response = await blendResearch.optimize(goals, pool.map((candidate) => candidate.id), blendSize, execution)
      setResult(response)
      setNote(saveLatestBlend(response)
        ? 'Simulation complete. This actual result is saved in this browser and available on Research Dashboard.'
        : 'Simulation complete. Browser storage is unavailable; download the result to keep it before leaving this page.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The QAOA request failed. Check that the backend is running and retry.')
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-5">
      <SectionHeading eyebrow="Step 2 · Whole-peptide QAOA" title="Blend Optimization"
        description="Run the existing Qiskit optimizer on the candidate pool and chemical goals selected in Peptide Designer. Compare the sampled blend with the exact optimum under the same objective."
        action={<StatusPill tone={busy ? 'amber' : pool.length ? 'blue' : 'slate'}>{busy ? 'Simulation running' : pool.length ? 'Candidate draft loaded' : 'Choose candidates first'}</StatusPill>} />
      <Link className="inline-flex items-center gap-2 text-sm font-semibold text-blue-800 underline" to="/designer?tab=library"><ArrowLeft size={15} /> Edit candidates and chemical goals</Link>
      <HardwareExecutionControl execution={hardware} disabled={busy} />
      {!pool.length ? <EmptyState title="No candidate pool yet" detail="Open Peptide Designer, set chemical targets, and choose eight supported peptides manually or with Auto-shortlist 8. Then continue here to run QAOA." action={<Link className="font-semibold text-blue-800 underline" to="/designer?tab=library">Choose peptides in Designer</Link>} /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Whole-peptide variables" value={`${pool.length} qubits`} detail="One bit selects one whole peptide" />
            <MetricCard label="Required selection" value={`${blendSize} peptides`} detail="Invalid cardinalities are penalized" />
            <MetricCard label="Exact feasible search" value={`${combinations(pool.length, blendSize)} subsets`} detail="Classical reference uses the identical objective" />
            <MetricCard label="Binary states" value={`${2 ** pool.length}`} detail="8 candidates, choose 3 gives 256 states and 56 subsets" />
          </div>
          <Panel className="space-y-4 p-5" aria-label="Candidate pool from Designer">
            <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">Your candidate pool</h2><StatusPill tone="slate">pH {goals.ph}</StatusPill></div>
            <p className="text-sm leading-6 text-[#65717D]">Target candidate charge: {goals.target_charge} e; target hydropathy: {goals.target_hydropathy}. Charge weight: {goals.charge_weight}; hydropathy weight: {goals.hydropathy_weight}; sequence redundancy weight: {goals.diversity_weight}. Descriptors and scores are recalculated by the backend for every run.</p>
            <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{pool.map((candidate, index) => <li className="min-w-0 rounded-lg border border-[#D9E0E7] bg-[#F8FAFC] p-3" key={candidate.id}>
              <p className="text-xs font-semibold text-blue-800">q{index} · {candidate.name}</p><p className="mt-2 break-all font-mono text-xs">{candidate.sequence}</p>
              <a className="mt-2 inline-block break-all text-xs text-blue-800 underline" href={candidate.source_url} target="_blank" rel="noreferrer">{candidate.source} / {candidate.accession}</a>
            </li>)}</ol>
            <p className="text-xs text-[#65717D]">Rightmost bit selects candidate q0. Chemical targets apply to individual sequences; this does not predict biological effects or physical mixture compatibility.</p>
          </Panel>
          <Panel className="space-y-4 p-5">
            <div className="flex items-center gap-2"><Cpu className="text-blue-700" size={20} /><h2 className="text-lg font-semibold">QAOA run configuration</h2></div>
            <p className="text-sm leading-6 text-[#65717D]">Execution uses your local Python backend and an ideal statevector simulator, followed by simulated measurement shots. The IBM QPU checkbox sends final circuit measurements to hardware after local parameter fitting; unchecked runs consume no QPU allowance.</p>
            <form onSubmit={(event) => void run(event)} className="space-y-4">
              <fieldset className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" disabled={busy}>
                <legend className="sr-only">Execution settings</legend>
                {fields.map((field) => <label className="research-label" key={field.key}>{field.label}<input className="research-input mt-1.5" type="number" required min={field.min} max={field.max} step={1}
                  value={Number.isFinite(execution[field.key]) ? execution[field.key] : ''}
                  onChange={(event) => { setError(null); setNote(''); updateBlendWorkspace((previous) => ({ ...previous, execution: { ...previous.execution, [field.key]: event.target.value === '' ? Number.NaN : Number(event.target.value) } })) }} /></label>)}
              </fieldset>
              {problem && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900" role="status">{problem}</p>}
              <div className="flex flex-wrap items-center gap-3"><Button type="submit" disabled={busy || problem !== null}>{busy ? <LoaderCircle className="animate-spin" size={16} /> : <Play size={16} />}{busy ? 'Preparing quantum run...' : hardware.enabled ? 'Run Blend on IBM QPU' : 'Run Quantum Optimization'}</Button>
                <span className="text-xs text-[#65717D]">{isWorkspacePersisted() ? 'Draft saved in this browser.' : 'Draft is available for this visit; browser storage is unavailable.'}</span></div>
              {busy && <p className="text-sm text-blue-800" role="status">Calculating chemical scores, fitting the QAOA circuit, and sampling outcomes…</p>}
            </form>
            {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
            {note && <p className="text-sm text-[#65717D]" role="status">{note}</p>}
          </Panel>
          <Panel className="space-y-3 p-5" aria-label="Blend objective">
            <h2 className="text-lg font-semibold">Objective used by the backend</h2>
            <p className="overflow-x-auto rounded-md bg-[#F8FAFC] p-3 font-mono text-sm">E(x) = -sum(S_i x_i) + {goals.diversity_weight} sum(P_ij x_i x_j) + lambda (sum(x_i) - {blendSize})²</p>
            <p className="text-sm leading-6 text-[#65717D]">S is normalized charge/hydropathy target matching. P is Jaccard overlap of adjacent-residue motifs. Lambda is calculated automatically above the full raw-objective range, protecting the cardinality constraint at the exact minimum. The fitted QAOA gamma/beta angles are optimized automatically; lambda and the sequence penalty are not those angles.</p>
          </Panel>
        </>
      )}
      {result && <div className="space-y-3">
        <p className={`rounded-lg border p-3 text-sm ${resultMatches ? 'border-blue-200 bg-blue-50 text-blue-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`} role="status">
          {resultMatches ? 'Saved result matches the current candidate pool, chemical goals, and execution settings.' : 'Previous run snapshot: your current draft differs from this saved result. Run again to evaluate the new settings; the results below have not been recalculated.'}
        </p>
        <BlendRunResults result={result} />
      </div>}
    </div>
  )
}
