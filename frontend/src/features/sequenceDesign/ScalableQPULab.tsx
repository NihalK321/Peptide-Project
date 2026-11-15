import { HardwareExecutionControl } from '../shared/HardwareExecution'
import { useHardwareExecution } from '../shared/useHardwareExecution'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, MetricCard, Panel, SectionHeading } from '../../components/ui'
import { downloadSequenceFile, residueCodes, requestSignature } from '../../services/sequenceDesign'
import { scalableSequence } from '../../services/scalableSequence'
import type { ClassicalSearch, QPUJob, ScalablePreview, ScalableRequest, ScalableRun, ShotSummary } from '../../services/scalableSequence'

const jobKey = 'pepperq.scalable-qpu.prepared-id'
const initial: ScalableRequest = {
  length: 10, template_sequence: 'GAGAGAGAGA',
  positions: Array.from({ length: 10 }, (_, index) => ({ position: index+1, choices: [...'AGKR'] })),
  goals: { ph: 7.4, target_charge: 2, charge_weight: 1, hydropathy_min: 0, hydropathy_max: 0, hydropathy_weight: .5, adjacent_repeat_weight: 0 },
  layers: 1, shots: 256, seed: 42, max_iterations: 10, training_shots: 64, bond_dimension: 8, classical_seconds: 1,
  parameter_sets: [[1, .3], [2, .6], [3, .9]],
}
const codes = (text: string) => [...text.toUpperCase().replace(/[\s,]/g, '')]

export function ScalableQPULab() {
  const hardware = useHardwareExecution('scalable')
  const [input, setInput] = useState(initial)
  const [template, setTemplate] = useState(initial.template_sequence)
  const [preview, setPreview] = useState<ScalablePreview | null>(null)
  const [run, setRun] = useState<ScalableRun | null>(null)
  const [job, setJob] = useState<QPUJob | null>(null)
  const [jobId, setJobId] = useState(() => { try { return localStorage.getItem(jobKey) ?? '' } catch { return '' } })
  const [backend, setBackend] = useState('')
  const [cap, setCap] = useState(60)
  const [confirmation, setConfirmation] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const report = preview ?? run ?? job?.preview
  const signature = (request: ScalableRequest) => requestSignature(Object.fromEntries(Object.keys(initial).map((key) => [key, request[key as keyof ScalableRequest]])))
  const matches = (request: ScalableRequest) => signature(request) === signature(input) && template === input.template_sequence
  const jobMatches = job !== null && matches(job.design) && job.backend_name === backend && job.max_execution_seconds === cap

  function update(next: ScalableRequest) {
    setInput(next); setPreview(null); setConfirmation(false); setError('')
  }
  async function action(label: string, work: () => Promise<void>) {
    if (busy) return
    setBusy(label); setError('')
    try { await work() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Request failed.') }
    finally { setBusy('') }
  }
  function checkedInput() {
    if (template !== input.template_sequence) throw new Error('Apply the edited template first.')
    return input
  }
  function remember(value: QPUJob) {
    setJob(value); setJobId(value.prepared_id)
    try { localStorage.setItem(jobKey, value.prepared_id) } catch { /* ID remains visible and downloadable. */ }
    setConfirmation(false)
  }
  function applyTemplate() {
    const sequence = template.toUpperCase().replace(/\s/g, '')
    if (!/^[ACDEFGHIKLMNPQRSTVWY]{2,50}$/.test(sequence)) { setError('Use 2–50 standard amino-acid letters.'); return }
    setTemplate(sequence)
    update({ ...input, length: sequence.length, template_sequence: sequence,
      positions: [...sequence].map((letter, index) => ({ position: index+1, choices: [letter] })) })
  }
  function preset(alphabet: string) {
    const value = { ...initial, positions: initial.positions.map((row) => ({ ...row, choices: [...alphabet] })) }
    update(value); setTemplate(value.template_sequence)
  }
  const numberFields: { key: 'shots' | 'seed' | 'max_iterations' | 'training_shots' | 'bond_dimension' | 'classical_seconds'; label: string; min: number; max: number; step: number }[] = [
    { key: 'shots', label: 'Shots per hardware angle set / final local sample', min: 128, max: 1024, step: 1 },
    { key: 'max_iterations', label: 'Local QAOA evaluation budget', min: 10, max: 30, step: 1 },
    { key: 'training_shots', label: 'Local training shots', min: 32, max: 128, step: 1 },
    { key: 'bond_dimension', label: 'Local MPS bond-dimension cap', min: 2, max: 16, step: 1 },
    { key: 'classical_seconds', label: 'Classical search budget (seconds)', min: .1, max: 5, step: .1 },
    { key: 'seed', label: 'Random seed', min: 0, max: 2147483647, step: 1 },
  ]
  return <div className="space-y-5">
    <SectionHeading eyebrow="Scalable sequence experiment" title="Scalable QPU Lab" description="Compile position-based costs without enumerating every peptide. Run a bounded local experiment, or explicitly submit a parameter sweep to IBM hardware." />
    <Link to="/sequence-design" className="text-sm text-blue-800 underline">Return to the exact sequence designer and existing modes</Link>
    <Panel className="p-4 text-sm leading-6">Ten editable positions can each offer up to 20 amino acids, using up to 50 qubits. Search-space size alone is not a speedup. The full alphabet creates a long circuit; inspect gates and device routing before committing QPU runtime. Objectives remain estimated charge, hydropathy and an optional adjacent-repeat preference.</Panel>
    <HardwareExecutionControl execution={hardware} disabled={!!busy} />
    <fieldset disabled={!!busy} className="min-w-0 space-y-5">
      <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">1. Set the sequence space</h2>
        <div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => preset('AGKR')}>10 positions × 4 choices</Button><Button variant="secondary" onClick={() => preset(residueCodes)}>10 positions × 20 choices</Button></div>
        <label className="research-label block">Template sequence<input aria-label="Scalable template" className="research-input mt-1 font-mono" value={template} onChange={(event) => { setTemplate(event.target.value.toUpperCase()); setConfirmation(false) }} /></label>
        <Button variant="secondary" onClick={applyTemplate}>Apply template and lock positions</Button>
        <p className="text-xs leading-6 text-slate-600">Apply a template to lock every position. Check up to ten sites and enter their allowed letters. One allowed letter means fixed. Every run retains sequence length. No mutation budget or required-residue constraint is added by this page.</p>
        <div className="max-h-96 overflow-auto"><table className="research-table"><thead><tr><th>Position</th><th>Editable</th><th>Allowed amino acids</th><th>Choices</th></tr></thead><tbody>{input.positions.map((row, index) => <tr key={row.position}><td>{row.position}</td><td><input type="checkbox" aria-label={`Scalable position ${row.position} editable`} checked={row.choices.length > 1} disabled={row.choices.length <= 1 && input.positions.filter((item) => item.choices.length > 1).length >= 10} onChange={(event) => update({ ...input, positions: input.positions.map((item, i) => i === index ? { ...item, choices: event.target.checked ? [...'AGKR'] : [input.template_sequence[index]] } : item) })} /></td><td><input aria-label={`Scalable position ${row.position} choices`} className="research-input min-w-48 font-mono" value={row.choices.join('')} onChange={(event) => update({ ...input, positions: input.positions.map((item, i) => i === index ? { ...item, choices: codes(event.target.value) } : item) })} /></td><td>{row.choices.length}</td></tr>)}</tbody></table></div>
      </Panel>
      <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">2. Goals and experiment budget</h2><p className="text-sm text-slate-600">pH is the solution condition. Hydropathy is a point target in this scalable workflow. Different sequence orders can tie under composition-based goals.</p>
        <div className="grid gap-4 md:grid-cols-3">{([
          { key: 'ph', label: 'Solution pH', min: 2, max: 12 },
          { key: 'target_charge', label: 'Target charge (e)', min: -51, max: 51 },
          { key: 'hydropathy_min', label: 'Hydropathy point target', min: -4.5, max: 4.5 },
          { key: 'charge_weight', label: 'Charge weight', min: 0, max: 10 },
          { key: 'hydropathy_weight', label: 'Hydropathy weight', min: 0, max: 10 },
          { key: 'adjacent_repeat_weight', label: 'Adjacent-repeat preference weight', min: 0, max: 10 },
        ] as const).map((field) => <label key={field.key} className="research-label">{field.label}<input aria-label={field.label} className="research-input mt-1" type="number" min={field.min} max={field.max} step={.1} value={input.goals[field.key]} onChange={(event) => update({ ...input, goals: { ...input.goals, [field.key]: Number(event.target.value), ...(field.key === 'hydropathy_min' ? { hydropathy_max: Number(event.target.value) } : {}) } })} /></label>)}</div>
        <div className="grid gap-4 md:grid-cols-3">{numberFields.map((field) => <label key={field.key} className="research-label">{field.label}<input aria-label={field.label} className="research-input mt-1" type="number" min={field.min} max={field.max} step={field.step} value={input[field.key]} onChange={(event) => update({ ...input, [field.key]: Number(event.target.value) })} /></label>)}</div>
        <p className="text-xs text-slate-600">This page uses one QAOA layer. Local fitting uses COBYLA. Hardware uses the explicit angle sets below, not an adaptive training loop. The classical comparison uses categorical multistart descent and simulated annealing, or an exact reference for at most 4,096 sequences.</p>
        <div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => void action('Compiling scalable cost', async () => setPreview(await scalableSequence.preview(checkedInput())))}>Preview scalable cost</Button><Button onClick={() => void action('Running local QAOA and classical search', async () => { if (hardware.enabled) await hardware.run('scalable', checkedInput()); else setRun(await scalableSequence.run(checkedInput())) })}>{hardware.enabled ? 'Run Scalable QAOA on IBM QPU' : 'Run bounded local comparison'}</Button><Button variant="secondary" onClick={() => void action('Exporting circuit and running classical baseline', async () => setRun(await scalableSequence.export(checkedInput())))}>Export circuit + classical baseline</Button></div>
      </Panel>
      <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">3. Advanced IBM workflow: prepare and inspect separately</h2>
        <p className="text-sm leading-6">The backend must have Qiskit Runtime credentials configured and <code>PEPPERQ_ENABLE_QPU=1</code>. Credentials never go into this webpage. Preparation connects read-only and transpiles for your chosen device; it does not submit a workload. A separate submit action consumes account runtime.</p>
        <div className="grid gap-4 md:grid-cols-2"><label className="research-label">IBM backend name<input aria-label="IBM backend name" className="research-input mt-1" placeholder="An operational backend available to your account" value={backend} onChange={(event) => { setBackend(event.target.value); setConfirmation(false) }} /></label><label className="research-label">Job execution cap (seconds)<input aria-label="Job execution cap (seconds)" className="research-input mt-1" type="number" min={10} max={180} step={1} value={cap} onChange={(event) => { setCap(Number(event.target.value)); setConfirmation(false) }} /></label></div>
        <p className="text-xs text-slate-600">The execution cap is not an estimate of usage or remaining allowance. This prototype rejects preparations above 15,000 logical gates or routed depth/two-qubit count above 20,000. Reduce choices if the circuit is too large.</p>
        {run?.provenance === 'simulated_approximate' && <Button variant="secondary" disabled={!matches(run.request)} onClick={() => update({ ...input, parameter_sets: [run.parameters] })}>Use local fitted angles for hardware verification</Button>}
        <div className="space-y-2"><p className="research-label">Hardware angle sets (gamma, beta in radians; up to eight)</p>{input.parameter_sets.map((angles, index) => <div key={index} className="flex flex-wrap gap-2">{angles.map((angle, j) => <label key={j} className="research-label">Set {index+1} {j === 0 ? 'gamma' : 'beta'}<input aria-label={`Set ${index+1} ${j === 0 ? 'gamma' : 'beta'}`} className="research-input mt-1 w-28" type="number" step={.1} min={-6.28} max={6.28} value={angle} onChange={(event) => update({ ...input, parameter_sets: input.parameter_sets.map((values, i) => i === index ? values.map((v, k) => k === j ? Number(event.target.value) : v) : values) })} /></label>)}</div>)}<div className="flex gap-3"><Button variant="ghost" disabled={input.parameter_sets.length >= 8} onClick={() => update({ ...input, parameter_sets: [...input.parameter_sets, [1, .5]] })}>Add angle set</Button><Button variant="ghost" disabled={input.parameter_sets.length <= 1} onClick={() => update({ ...input, parameter_sets: input.parameter_sets.slice(0, -1) })}>Remove last set</Button></div><p className="text-xs">Requested hardware shots: {input.shots * input.parameter_sets.length} total. Every angle set is measured; the lowest mean penalized cost selects the reported set.</p></div>
        <Button variant="secondary" disabled={!backend.trim()} onClick={() => void action('Preparing backend-specific circuit; no QPU job submitted', async () => remember(await scalableSequence.prepare(checkedInput(), backend, cap)))}>Prepare hardware circuit — no submission</Button>
        {job && <div className="space-y-3 rounded-lg border p-4 text-sm"><p>{jobMatches ? 'Preparation matches the current form.' : 'Previous preparation snapshot: inputs differ. Restore them or prepare again before submitting.'}</p><p>Status: <strong>{job.status}</strong> · backend {job.backend_name} · {job.circuit.logical_qubits} logical qubits · routed depth {job.circuit.depth} · {job.circuit.two_qubit_gates} two-qubit gates · {job.requested_total_shots} total shots</p><p className="break-all">Preparation ID: {job.prepared_id}{job.job_id && <> · IBM job: {job.job_id}</>}</p><p>{job.notice}</p>
          <label className="flex items-start gap-2"><input aria-label="Confirm QPU runtime consumption" type="checkbox" checked={confirmation} onChange={(event) => setConfirmation(event.target.checked)} /><span>I want to submit this prepared job and consume my IBM QPU runtime allowance.</span></label>
          <Button disabled={!jobMatches || !confirmation || job.status !== 'PREPARED'} onClick={() => void action('Submitting one IBM Runtime job', async () => remember(await scalableSequence.submit(job.prepared_id)))}>Submit prepared job to QPU</Button>
          <Button variant="secondary" onClick={() => downloadSequenceFile(JSON.stringify(job, null, 2), 'pepperq_qpu_experiment.json', 'application/json')}>Download job / result JSON</Button>
        </div>}
        <label className="research-label block">Preparation ID to recover or refresh<input aria-label="Preparation ID to recover or refresh" className="research-input mt-1 font-mono" value={jobId} onChange={(event) => setJobId(event.target.value)} /></label><div className="flex flex-wrap gap-3"><Button variant="secondary" disabled={!jobId} onClick={() => void action('Reading IBM job status; no submission', async () => remember(await scalableSequence.status(jobId)))}>Refresh / recover job status</Button><Button variant="ghost" disabled={!job?.job_id || ['DONE', 'CANCELLED', 'ERROR'].includes(job.status)} onClick={() => void action('Requesting cancellation', async () => remember(await scalableSequence.cancel(job!.prepared_id)))}>Cancel this QPU job</Button><Button variant="ghost" disabled={!job} onClick={() => { if (job) { setInput(job.design); setTemplate(job.design.template_sequence); setBackend(job.backend_name); setCap(job.max_execution_seconds); setConfirmation(false) } }}>Restore prepared inputs</Button></div>
      </Panel>
    </fieldset>
    {busy && <p role="status" className="rounded bg-blue-50 p-4 text-sm">{busy}…</p>}
    {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-900">{error}</p>}
    {report && <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">Compiled cost snapshot</h2><p className="text-xs">{matches(report.request) ? 'Matches current sequence inputs.' : 'Previous snapshot; inputs have changed.'}</p><div className="grid gap-3 md:grid-cols-3"><MetricCard label="Qubits" value={String(report.qubits)} detail={`${report.editable_positions} editable positions`} /><MetricCard label="Valid sequences" value={Number(report.valid_sequence_count).toLocaleString()} detail={`${Number(report.encoded_state_count).toLocaleString()} encoded states`} /><MetricCard label="Logical gates" value={report.logical_gate_count.toLocaleString()} detail={`${report.cost_terms} Pauli terms; no global energy table`} /></div><p className="text-xs">Compilation: {report.formulation_seconds.toFixed(3)} s. Mapping error: {report.validation.maximum_error.toExponential(2)} across {report.validation.checked_assignments} deterministic/seeded assignments. This is not an exhaustive correctness proof. Uniform valid-code probability: {(100*report.uniform_valid_probability).toFixed(2)}%; extra binary codes consume shots unless the circuit suppresses them.</p><details><summary className="cursor-pointer text-sm">Methods and limitations</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-xs">{report.limitations.map((line) => <li key={line}>{line}</li>)}</ul></details></Panel>}
    {run && <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">{run.provenance === 'prepared' ? 'Circuit export and classical reference' : 'Local approximate QAOA comparison'}</h2><p className="text-xs">{matches(run.request) ? 'Matches current inputs.' : 'Previous run snapshot; inputs have changed.'}</p><Comparison classical={run.classical} summary={run.summary} /><p className="text-sm">QAOA local fit and sampling: {run.quantum_workflow_seconds === null ? 'Not executed' : `${run.quantum_workflow_seconds.toFixed(3)} s`}. {run.comparison}</p><div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => downloadSequenceFile(run.circuit.qasm, 'scalable_sequence.qasm')}>Download IBM Composer circuit</Button><Button variant="secondary" onClick={() => downloadSequenceFile(JSON.stringify(run, null, 2), 'scalable_sequence_result.json', 'application/json')}>Download complete experiment</Button></div></Panel>}
    {job?.result && <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">Actual IBM hardware measurements</h2><Comparison classical={job.classical} summary={job.result.selected_parameter_result} /><p className="text-sm">All parameter sets: {job.result.total_shots} shots. QPU usage: {job.result.quantum_usage_seconds === null ? 'Unavailable' : `${job.result.quantum_usage_seconds.toFixed(3)} s`}. Submission to retrieval (includes queue and polling delay): {job.result.submission_to_retrieval_seconds.toFixed(1)} s.</p><p className="text-xs">{job.result.selection_method} {job.result.comparison}</p></Panel>}
  </div>
}

function Comparison({ classical, summary }: { classical: ClassicalSearch; summary: ShotSummary | null }) {
  return <div className="space-y-3 text-sm"><p>Classical best: <code className="break-all">{classical.best.sequence}</code> · objective {classical.best.objective.toFixed(6)} · {classical.evaluations.toLocaleString()} evaluations · {classical.elapsed_seconds.toFixed(3)} s.</p><p className="text-xs">{classical.method}. {classical.exact_optimum_available ? 'Exact optimum available for this small instance.' : 'No optimality certificate; a stronger or longer classical search may improve this result.'}</p>{summary && <><p>Quantum sampled best: {summary.best_sampled ? <><code className="break-all">{summary.best_sampled.sequence}</code> · objective {summary.best_sampled.objective.toFixed(6)} · sampled-minus-classical difference {(summary.best_sampled.objective-classical.best.objective).toFixed(6)}</> : 'No feasible sequence observed. No classical answer substituted.'}</p><p>{summary.feasible_shots}/{summary.shots} feasible shots; {summary.invalid_shots} unused-code shots. Observed feasible frequency {(100*summary.observed_feasible_frequency).toFixed(1)}% (finite-shot estimate).</p>{summary.reference_quality && <p className="text-xs">Shots matching or beating the {summary.reference_quality.target_is_exact_optimum ? 'exact classical optimum' : 'classical heuristic score'}: {summary.reference_quality.matched_or_better_shots}/{summary.reference_quality.total_shots}. Wilson 95% interval: {summary.reference_quality.wilson_95_interval.map((v) => `${(100*v).toFixed(1)}%`).join(' to ')}. {summary.reference_quality.interval_assumption}</p>}</>}</div>
}
