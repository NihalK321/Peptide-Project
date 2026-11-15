import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Dna, LoaderCircle, Play, ScanSearch } from 'lucide-react'
import { Button, MetricCard, Panel, SectionHeading, StatusPill } from '../../components/ui'
import { residueCodes, residueNames, requestSignature, sequenceDesign } from '../../services/sequenceDesign'
import type { SequenceGoals, SequencePreview, SequenceRequest, SequenceResult, LargeSequenceResult } from '../../services/sequenceDesign'
import { SequenceDesignResults } from './SequenceDesignResults'
import { LargeSequenceResults } from './LargeSequenceResults'

interface PositionDraft { first: string; second: string; variable: boolean; choices?: string[] }
interface Draft {
  mode: 'redesign' | 'new'
  template: string
  length: number
  allowed: string
  excluded: string
  required: string
  positions: PositionDraft[]
  maxMutations: string
  goals: SequenceGoals
  layers: number
  max_iterations: number
  shots: number
  seed: number
  executionMode: 'exact' | 'multi' | 'mps' | 'export'
  bondDimension: number
  trainingShots: number
}
const inputKey = 'pepperq.sequence-design-v1.input'
const resultKey = 'pepperq.sequence-design-v1.result'
const modeKey = 'pepperq.sequence-design-v1.execution-mode'
const sample: SequenceRequest = {
  length: 8, template_sequence: 'GAGAGAGA', allowed_amino_acids: [...residueCodes],
  excluded_amino_acids: [], required_amino_acids: ['K'],
  positions: Array.from({ length: 8 }, (_, i) => ({ position: i + 1, choices: i % 2 ? ['A', 'K'] : ['G'] })),
  max_mutations: 2, goals: { ph: 7.4, target_charge: 2, charge_weight: 1, hydropathy_min: -1.5,
    hydropathy_max: .5, hydropathy_weight: .5, adjacent_repeat_weight: 0 }, layers: 1, max_iterations: 60, shots: 2048, seed: 42,
}

const multiSample: SequenceRequest = { ...sample, required_amino_acids: [],
  positions: sample.positions.map((row, index) => ({ position: row.position,
    choices: index === 1 || index === 3 ? [...residueCodes] : [sample.template_sequence![index]] })) }

function loadInput(): SequenceRequest {
  try {
    const value = JSON.parse(localStorage.getItem(inputKey) ?? 'null') as SequenceRequest | null
    if (value && Array.isArray(value.positions) && value.positions.length === value.length && value.length >= 2 && value.length <= 50
      && value.positions.every((row) => Array.isArray(row.choices) && row.choices.length >= 1 && row.choices.length <= 20 && row.choices.every((letter) => residueCodes.includes(letter) && letter.length === 1))
      && Array.isArray(value.allowed_amino_acids) && Array.isArray(value.required_amino_acids) && Array.isArray(value.excluded_amino_acids)
      && value.goals && typeof value.goals.ph === 'number') return value
  } catch { /* A disabled or obsolete browser store must not prevent design. */ }
  return multiSample
}
function loadMode(): Draft['executionMode'] {
  try { const mode = localStorage.getItem(modeKey); return mode === 'mps' || mode === 'export' || mode === 'multi' ? mode : mode === 'exact' ? 'exact' : 'multi' } catch { return 'multi' }
}
function loadResult(): SequenceResult | LargeSequenceResult | null {
  try {
    const value = JSON.parse(localStorage.getItem(resultKey) ?? 'null') as SequenceResult | LargeSequenceResult | null
    if (value && 'exact_optimum_available' in value && value.contract_version === '1.1' && value.circuit && Array.isArray(value.candidate_sequences)) return value
    return value && 'benchmark' in value && value.contract_version === '1.0' && value.provenance === 'simulated' && value.circuit && value.benchmark && Array.isArray(value.states) ? value : null
  } catch { return null }
}
function draftFrom(request: SequenceRequest, executionMode: Draft['executionMode'] = 'exact'): Draft {
  return { mode: request.template_sequence ? 'redesign' : 'new', template: request.template_sequence ?? '',
    length: request.length, allowed: request.allowed_amino_acids.join(''), excluded: request.excluded_amino_acids.join(''),
    required: request.required_amino_acids.join(''), maxMutations: request.max_mutations === null ? '' : String(request.max_mutations),
    positions: request.positions.map((row) => ({ first: row.choices[0], second: row.choices[1] ?? (row.choices[0] === 'K' ? 'A' : 'K'), choices: row.choices, variable: row.choices.length > 1 })),
    goals: request.goals, layers: request.layers, max_iterations: request.max_iterations, shots: request.shots, seed: request.seed,
    executionMode, bondDimension: request.mps_bond_dimension ?? 16, trainingShots: request.training_shots ?? 64 }
}
const codes = (text: string) => [...text.replace(/[\s,]/g, '').toUpperCase()]
function makeRequest(draft: Draft, templateInput: string): SequenceRequest {
  if (draft.mode === 'redesign' && templateInput.replace(/\s/g, '').toUpperCase() !== draft.template) throw new Error('Click Apply template after editing the sequence, so the position choices match it.')
  const request: SequenceRequest = { length: draft.positions.length, template_sequence: draft.mode === 'redesign' ? draft.template : null,
    allowed_amino_acids: codes(draft.allowed), excluded_amino_acids: codes(draft.excluded), required_amino_acids: codes(draft.required),
    positions: draft.positions.map((row, index) => ({ position: index + 1, choices: row.variable ? (draft.executionMode === 'multi' ? row.choices ?? [...residueCodes] : [row.first, row.second]) : [row.first] })),
    max_mutations: draft.mode === 'redesign' && draft.maxMutations !== '' ? Number(draft.maxMutations) : null,
    goals: draft.goals, layers: draft.layers, max_iterations: draft.max_iterations, shots: draft.shots, seed: draft.seed }
  return draft.executionMode === 'exact' || draft.executionMode === 'multi' ? request : { ...request, mps_bond_dimension: draft.bondDimension,
    training_shots: draft.trainingShots, initial_gamma: 1, initial_beta: .5 }
}

export function SequenceDesign() {
  const [draft, setDraft] = useState(() => draftFrom(loadInput(), loadMode()))
  const [templateInput, setTemplateInput] = useState(() => draft.template)
  const [preview, setPreview] = useState<SequencePreview | null>(null)
  const [result, setResult] = useState<SequenceResult | LargeSequenceResult | null>(loadResult)
  const [busy, setBusy] = useState<'preview' | 'optimize' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const variableCount = draft.positions.filter((row) => row.variable).length
  const isSmall = draft.executionMode === 'exact' || draft.executionMode === 'multi'
  const isMulti = draft.executionMode === 'multi'
  const variableLimit = isMulti ? 2 : isSmall ? 8 : 50
  const qubitCount = draft.positions.reduce((total, row) => total + (row.variable ? (isMulti ? Math.ceil(Math.log2(Math.max(1, (row.choices ?? [...residueCodes]).length))) : 1) : 0), 0)
  const validSequenceCount = draft.positions.reduce((total, row) => total * (row.variable ? (isMulti ? (row.choices ?? [...residueCodes]).length : 2) : 1), 1)
  let currentResult = false
  try { currentResult = result !== null && requestSignature(result.request) === requestSignature(makeRequest(draft, templateInput))
    && ('exact_optimum_available' in result ? (result.status === 'circuit_prepared' ? 'export' : 'mps') : result.encoding ? 'multi' : 'exact') === draft.executionMode } catch { /* Unapplied input is a different draft. */ }

  function change(update: (previous: Draft) => Draft) {
    setDraft(update); setPreview(null); setError(null); setNote('')
  }
  function changePosition(index: number, update: Partial<PositionDraft>) {
    change((previous) => ({ ...previous, positions: previous.positions.map((row, i) => i === index ? { ...row, ...update } : row) }))
  }
  function applyTemplate() {
    const sequence = templateInput.replace(/\s/g, '').toUpperCase()
    if (!/^[ACDEFGHIKLMNPQRSTVWY]{2,50}$/.test(sequence)) { setError('Enter 2–50 standard one-letter amino-acid codes.'); return }
    setTemplateInput(sequence)
    change((previous) => ({ ...previous, template: sequence, length: sequence.length,
      positions: [...sequence].map((letter) => ({ first: letter, second: letter === 'K' ? 'A' : 'K', variable: false })) }))
    setNote('Template applied. All positions start fixed; select the positions the algorithm may change.')
  }
  function initializeLength() {
    if (!Number.isInteger(draft.length) || draft.length < 2 || draft.length > 50) { setError('Choose a whole-number length from 2 to 50.'); return }
    change((previous) => ({ ...previous, positions: Array.from({ length: previous.length }, () => ({ first: 'A', second: 'K', variable: false })) }))
    setNote('Length applied. Positions start fixed to A; set their residues and select variable positions within the selected execution limit.')
  }
  async function submit(kind: 'preview' | 'optimize') {
    if (busy) return
    setError(null); setNote('')
    try {
      if (isMulti && draft.positions.some((row) => row.variable && (row.choices ?? [...residueCodes]).length < 2)) throw new Error('Select at least two amino-acid choices at each editable position, or uncheck it to keep a fixed residue.')
      const request = makeRequest(draft, templateInput)
      if (draft.mode === 'new' && draft.length !== draft.positions.length) throw new Error('Click Apply length to update the position editor.')
      if (kind === 'optimize' && variableCount === 0) throw new Error('Select at least one variable position for QAOA, or use Preview to evaluate a fixed sequence.')
      setBusy(kind)
      if (kind === 'preview') {
        setPreview(await (isMulti ? sequenceDesign.previewMulti(request) : isSmall ? sequenceDesign.preview(request) : sequenceDesign.previewLarge(request)))
      } else {
        const response = await (isMulti ? sequenceDesign.optimizeMulti(request) : isSmall ? sequenceDesign.optimize(request) : draft.executionMode === 'mps' ? sequenceDesign.optimizeLarge(request) : sequenceDesign.exportLarge(request))
        setResult(response)
        try { localStorage.setItem(resultKey, JSON.stringify(response)) }
        catch { setNote('Result displayed, but browser storage is unavailable. Download the JSON to keep it.') }
      }
      try { localStorage.setItem(inputKey, JSON.stringify(request)); localStorage.setItem(modeKey, draft.executionMode) }
      catch { setNote('Browser storage is unavailable. Inputs remain available for this visit; download any completed result before leaving.') }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Sequence design failed. Check the backend and try again.') }
    finally { setBusy(null) }
  }
  const goalFields: { key: keyof SequenceGoals; label: string; min: number; max: number; step: number }[] = [
    { key: 'ph', label: 'Solution pH', min: 2, max: 12, step: .1 },
    { key: 'target_charge', label: 'Target estimated charge (e)', min: -51, max: 51, step: .1 },
    { key: 'charge_weight', label: 'Charge deviation weight', min: 0, max: 10, step: .1 },
    { key: 'hydropathy_min', label: 'Hydropathy minimum', min: -4.5, max: 4.5, step: .1 },
    { key: 'hydropathy_max', label: 'Hydropathy maximum', min: -4.5, max: 4.5, step: .1 },
    { key: 'hydropathy_weight', label: 'Hydropathy range weight', min: 0, max: 10, step: .1 },
    { key: 'adjacent_repeat_weight', label: 'Adjacent-repeat preference weight', min: 0, max: 10, step: .1 },
  ]
  return <div className="space-y-5">
    <Link className="block rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm font-semibold text-blue-900 underline" to="/sequence-qpu">Open Scalable QPU Lab: up to 10 editable positions, 20 choices per position, classical comparison and explicit IBM hardware submission</Link>
    <SectionHeading eyebrow="New research workflow" title="Peptide Sequence Design" description="Design a single peptide by choosing residues at selected positions. Compare QAOA with an exact classical reference for small instances, or a classical heuristic for large circuits." action={<StatusPill tone="blue">Position-based sequence optimization</StatusPill>} />
    <div className="flex flex-wrap gap-4 text-xs text-[#65717D]"><Link className="text-blue-800 underline" to="/designer">Existing peptide library and blend designer</Link><Link className="text-blue-800 underline" to="/optimization">Existing blend optimization</Link><Link className="text-blue-800 underline" to="/quantum-chemistry">Separate HeH+ quantum chemistry</Link></div>
    <Panel className="border-blue-200 bg-blue-50/40 p-4 text-sm leading-6">Choose multi-choice design (up to 20 amino acids at each of two editable positions, up to 10 qubits), binary exact small-instance simulation (up to 8 qubits) or analytical large circuits (up to 50 qubits). Large local runs use bounded approximate MPS simulation; circuit preparation alone does not execute a quantum job. Larger circuits are not proof of quantum advantage. No IBM QPU allowance is consumed.</Panel>
    <form onSubmit={(event) => { event.preventDefault(); void submit('optimize') }} className="space-y-5">
      <fieldset className="min-w-0 space-y-5" disabled={busy !== null}>
        <Panel className="space-y-4 p-5"><div className="flex items-center gap-2"><Dna className="text-blue-700" size={20} /><h2 className="text-lg font-semibold">1. Define the sequence space</h2></div>
          <label className="research-label block">Execution method<select aria-label="Execution method" className="research-select mt-1" value={draft.executionMode} onChange={(event) => change((previous) => ({ ...previous, executionMode: event.target.value as Draft['executionMode'], positions: previous.positions.map((row, index) => ({ ...row, choices: event.target.value === 'multi' ? (row.choices && row.choices.length > 2 ? row.choices : [...residueCodes]) : row.choices, variable: event.target.value === 'multi' ? row.variable && previous.positions.slice(0, index).filter((item) => item.variable).length < 2 : row.variable })), max_iterations: event.target.value === 'exact' || event.target.value === 'multi' ? 60 : 10, layers: 1 }))}><option value="multi">Multi-choice sequence design - 20 choices at up to 2 positions</option><option value="exact">Exact statevector and benchmark · up to 8 qubits</option><option value="mps">Bounded approximate MPS · up to 50 qubits</option><option value="export">Prepare circuit only · up to 50 qubits</option></select></label>
          <Button variant="secondary" onClick={() => { change(() => draftFrom(multiSample, 'multi')); setTemplateInput(sample.template_sequence!) }}>Load 20-amino-acid example</Button>
          {isMulti && <p className="rounded-lg bg-blue-50 p-3 text-sm leading-6">Choose up to two editable positions and select their allowed amino acids below. Each position uses ceil(log2(choices)) qubits: 20 choices need 5 qubits. Two full alphabets give 400 valid sequences in 1,024 binary states. Unused codes are penalized and never proposed as peptides. Switching to this mode keeps only the first two checked positions editable; other positions keep their fixed residue.</p>}
          <Button variant="secondary" onClick={() => { change(() => draftFrom({ ...sample, length: 50, template_sequence: null, required_amino_acids: [], max_mutations: null, positions: Array.from({ length: 50 }, (_, i) => ({ position: i + 1, choices: ['A', 'K'] })), goals: { ...sample.goals, hydropathy_min: 0, hydropathy_max: 0 }, max_iterations: 10, shots: 256 }, 'mps')); setTemplateInput('') }}>Load 50-qubit example</Button>
          {!isSmall && <p className="rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900">Large mode needs a genuine quadratic cost: use a hydropathy point target (minimum = maximum), zero hydropathy weight, or a range covering all choices. Required residues must be locked into fixed positions; mutation budgets must not restrict any encoded choice. Unsupported constraints are rejected. Above 20 qubits, only one layer is supported. No exact optimum or ideal success probability is claimed.</p>}
          <label className="research-label block">Design mode<select aria-label="Design mode" className="research-select mt-1" value={draft.mode} onChange={(event) => change((previous) => ({ ...previous, mode: event.target.value as Draft['mode'] }))}><option value="redesign">Redesign an existing sequence</option><option value="new">Design a sequence from a length</option></select></label>
          {draft.mode === 'redesign' ? <div className="space-y-2"><label className="research-label block">Template sequence<textarea aria-label="Template sequence" className="research-textarea mt-1 font-mono" value={templateInput} onChange={(event) => { setTemplateInput(event.target.value); setPreview(null); setError(null) }} /></label><Button variant="secondary" onClick={applyTemplate}>Apply template</Button><p className="text-xs text-[#65717D]">Changing and applying the template resets the position editor to fixed residues. Examples are demonstration inputs, not known therapeutic peptides.</p></div> : <div className="flex flex-wrap items-end gap-3"><label className="research-label">Requested length<input type="number" className="research-input mt-1 w-32" min={2} max={50} step={1} required value={draft.length} onChange={(event) => change((previous) => ({ ...previous, length: Number(event.target.value) }))} /></label><Button variant="secondary" onClick={initializeLength}>Apply length</Button></div>}
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="research-label">Globally allowed amino acids<input className="research-input mt-1 font-mono" value={draft.allowed} onChange={(event) => change((previous) => ({ ...previous, allowed: event.target.value.toUpperCase() }))} /></label>
            <label className="research-label">Excluded amino acids<input className="research-input mt-1 font-mono" value={draft.excluded} placeholder="Optional, e.g. C" onChange={(event) => change((previous) => ({ ...previous, excluded: event.target.value.toUpperCase() }))} /></label>
            <label className="research-label">Required at least once<input className="research-input mt-1 font-mono" value={draft.required} placeholder="Optional, e.g. KR" onChange={(event) => change((previous) => ({ ...previous, required: event.target.value.toUpperCase() }))} /></label>
          </div>
          <p className="text-xs leading-6 text-[#65717D]">Allowed does not mean required. Exclusions override the allowed set. Position choices must belong to the remaining allowed set. Use uppercase one-letter codes; commas and spaces are accepted.</p>
          <details className="text-xs"><summary className="cursor-pointer font-semibold">Show all 20 amino-acid options</summary><div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">{[...residueCodes].map((code, index) => <span key={code}><strong>{code}</strong> — {residueNames[index]}</span>)}</div></details>
        </Panel>
        <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">2. Choose fixed and editable positions</h2>
          <label className="research-label block">Set first N positions editable<input aria-label="Set first N positions editable" className="research-input mt-1 w-36" type="number" min={0} max={Math.min(draft.positions.length, variableLimit)} step={1} value={variableCount} onChange={(event) => { const count = Number(event.target.value); if (Number.isInteger(count) && count >= 0 && count <= Math.min(draft.positions.length, variableLimit)) change((previous) => ({ ...previous, positions: previous.positions.map((row, index) => ({ ...row, variable: index < count })) })) }} /></label>
          <p className="text-sm text-[#65717D]">Unchecked positions keep their fixed residue. In multi-choice mode, check up to two positions and select any subset of the 20 amino acids for each. Other execution modes use two choices per editable position.</p>
          <div className="grid gap-3 sm:grid-cols-3"><MetricCard label="Total positions" value={String(draft.positions.length)} detail="Fixed length during this run" /><MetricCard label="Editable positions" value={`${variableCount}/${variableLimit}`} detail={`${qubitCount} qubits; ${isMulti ? "up to 5 per editable position" : "one per two-choice position"}`} /><MetricCard label="Restricted design space" value={variableCount > 16 ? `2^${variableCount} sequences` : `${validSequenceCount} sequences`} detail="Before required-residue and mutation constraints" /></div>
          <div className="max-h-96 overflow-auto rounded-lg border border-[#D9E0E7]"><table className="research-table"><thead><tr><th>Position</th><th>May change</th><th>{isMulti ? 'Fixed residue' : 'Option 0 / fixed'}</th><th>{isMulti ? 'Allowed amino acids at editable position' : 'Option 1'}</th></tr></thead><tbody>{draft.positions.map((row, index) => <tr key={index}><td>{index + 1}</td><td><input type="checkbox" aria-label={`Position ${index + 1} can change`} checked={row.variable} disabled={!row.variable && variableCount >= variableLimit} onChange={(event) => changePosition(index, { variable: event.target.checked })} /></td>{(isMulti ? ['first'] as const : ['first', 'second'] as const).map((key) => <td key={key}><select aria-label={`Position ${index + 1} option ${key === 'first' ? 0 : 1}`} className="research-select min-w-32" disabled={(key === 'second' && !row.variable) || (isMulti && row.variable)} value={row[key]} onChange={(event) => changePosition(index, { [key]: event.target.value })}>{[...residueCodes].map((code, i) => <option key={code} value={code}>{code} · {residueNames[i]}</option>)}</select></td>)}{isMulti && <td className="min-w-72">{row.variable ? <div className="space-y-2"><div className="flex gap-3 text-xs"><button type="button" className="text-blue-800 underline" onClick={() => changePosition(index, { choices: [...residueCodes].filter((code) => codes(draft.allowed).includes(code) && !codes(draft.excluded).includes(code)) })}>Select all globally allowed</button><span>{(row.choices ?? [...residueCodes]).length} choices</span></div><div className="flex flex-wrap gap-2">{[...residueCodes].map((code, acidIndex) => <label key={code} title={residueNames[acidIndex]} className="flex items-center gap-1 rounded border p-1 text-xs"><input type="checkbox" aria-label={`Position ${index + 1} allow ${code}`} checked={(row.choices ?? [...residueCodes]).includes(code)} onChange={(event) => { const choices = row.choices ?? [...residueCodes]; changePosition(index, { choices: event.target.checked ? [...residueCodes].filter((letter) => letter === code || choices.includes(letter)) : choices.filter((letter) => letter !== code) }) }} />{code}</label>)}</div></div> : <span className="text-xs text-slate-500">Fixed position</span>}</td>}</tr>)}</tbody></table></div>
          {draft.mode === 'redesign' && <label className="research-label block">Maximum changes from template (blank = no budget)<input className="research-input mt-1 w-40" type="number" min={0} max={draft.positions.length} step={1} value={draft.maxMutations} onChange={(event) => change((previous) => ({ ...previous, maxMutations: event.target.value }))} /></label>}
        </Panel>
        <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">3. Set chemical research goals</h2><p className="text-sm leading-6 text-[#65717D]">pH is the surrounding solution condition. The algorithm targets estimated net charge at that pH. Hydropathy range and charge are soft preferences, not guaranteed outcomes. Required residues and the mutation budget are hard constraints.</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{goalFields.map((field) => <label className="research-label" key={field.key}>{field.label}<input className="research-input mt-1" type="number" required min={field.min} max={field.max} step={field.step} value={Number.isFinite(draft.goals[field.key]) ? draft.goals[field.key] : ''} onChange={(event) => change((previous) => ({ ...previous, goals: { ...previous.goals, [field.key]: event.target.value === '' ? Number.NaN : Number(event.target.value) } }))} /></label>)}</div>
          <p className="text-xs leading-6 text-[#65717D]">At least one weight must be positive. The optional adjacent-repeat weight discourages identical neighboring residues as a design preference, not a stability prediction. With composition-only scores, different residue orders may tie.</p>
        </Panel>
        <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">4. Validate and run QAOA</h2><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{([{ key: 'layers', label: 'QAOA layers', min: 1, max: !isSmall && variableCount > 20 ? 1 : 2 }, { key: 'max_iterations', label: 'Objective evaluation budget', min: 10, max: isSmall ? 120 : 30 }, { key: 'shots', label: 'Simulated shots', min: 128, max: 8192 }, { key: 'seed', label: 'Random seed', min: 0, max: 2147483647 }] as const).map((field) => <label className="research-label" key={field.key}>{field.label}<input className="research-input mt-1" type="number" required min={field.min} max={field.max} step={1} value={Number.isFinite(draft[field.key]) ? draft[field.key] : ''} onChange={(event) => change((previous) => ({ ...previous, [field.key]: event.target.value === '' ? Number.NaN : Number(event.target.value) }))} /></label>)}</div>
          {!isSmall && <div className="grid gap-4 sm:grid-cols-2"><label className="research-label">MPS maximum bond dimension<select aria-label="MPS maximum bond dimension" className="research-select mt-1" value={draft.bondDimension} onChange={(event) => change((previous) => ({ ...previous, bondDimension: Number(event.target.value) }))}><option value={8}>8 · lower compute cost, more truncation risk</option><option value={16}>16 · default bounded simulation</option><option value={32}>32 · higher compute cost</option></select></label><label className="research-label">Training shots per evaluation<input className="research-input mt-1" type="number" required min={64} max={256} step={1} value={draft.trainingShots} onChange={(event) => change((previous) => ({ ...previous, trainingShots: Number(event.target.value) }))} /></label></div>}
          <div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => void submit('preview')}><ScanSearch size={15} /> Validate and preview</Button><Button type="submit" disabled={variableCount === 0}><Play size={15} /> {draft.executionMode === 'export' ? 'Prepare Sequence Circuit' : 'Run Sequence QAOA'}</Button><Button variant="ghost" onClick={() => { change(() => draftFrom(sample)); setTemplateInput(sample.template_sequence!) }}>Load demonstration input</Button></div>
          <p className="text-xs text-[#65717D]">Preview works for fully fixed sequences. Runs require at least one editable position. Nothing runs automatically when you change a field. Last successfully submitted inputs and the latest result are saved in this browser when storage is available.</p>
        </Panel>
      </fieldset>
      {busy && <p role="status" className="flex items-center gap-2 rounded-lg bg-blue-50 p-4 text-sm text-blue-900"><LoaderCircle className="animate-spin" size={18} />{busy === 'preview' ? 'Calculating chemistry and validating the restricted sequence space…' : isSmall ? 'Fitting the quantum circuit, sampling sequences, and checking the exact classical reference...' : draft.executionMode === 'export' ? 'Preparing the analytical circuit without executing it...' : 'Running bounded MPS simulation and comparing with a classical heuristic...'}</p>}
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">{error}</p>}
      {note && <p role="status" className="text-sm text-[#65717D]">{note}</p>}
    </form>
    {preview && <Panel className="space-y-3 p-5" aria-label="Validated sequence design space"><h2 className="text-lg font-semibold">Validated design space</h2><p className="text-sm">{preview.qubits} qubits, {preview.state_count.toLocaleString()} encoded states, {preview.feasible_state_count.toLocaleString()} feasible sequences. Cost representation: {preview.cost_representation.replaceAll('_', ' ')} (degree {preview.cost_polynomial_degree}).</p>{preview.template_properties && <p className="text-sm">Template at pH {preview.request.goals.ph}: charge {preview.template_properties.charge.toFixed(3)} e, GRAVY {preview.template_properties.hydropathy.toFixed(3)}, mass {preview.template_properties.mass_da.toFixed(2)} Da.</p>}<p className="text-xs text-[#65717D]">{preview.encoding && `${preview.encoding.valid_sequence_count} valid sequence codes; ${preview.encoding.invalid_code_count} unused codes are penalized. `}Calculated preview only; no QAOA circuit has been run by this preview action.</p></Panel>}
    {result && ('exact_optimum_available' in result ? <LargeSequenceResults key={result.experiment_id} result={result} current={currentResult} /> : <SequenceDesignResults key={result.experiment_id} result={result} current={currentResult} />)}
  </div>
}
