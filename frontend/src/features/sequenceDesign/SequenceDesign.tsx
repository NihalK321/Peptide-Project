import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Dna, LoaderCircle, Play, ScanSearch } from 'lucide-react'
import { Button, MetricCard, Panel, SectionHeading, StatusPill } from '../../components/ui'
import { residueCodes, residueNames, requestSignature, sequenceDesign } from '../../services/sequenceDesign'
import type { SequenceGoals, SequencePreview, SequenceRequest, SequenceResult } from '../../services/sequenceDesign'
import { SequenceDesignResults } from './SequenceDesignResults'

interface PositionDraft { first: string; second: string; variable: boolean }
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
}
const inputKey = 'pepperq.sequence-design-v1.input'
const resultKey = 'pepperq.sequence-design-v1.result'
const sample: SequenceRequest = {
  length: 8, template_sequence: 'GAGAGAGA', allowed_amino_acids: [...residueCodes],
  excluded_amino_acids: [], required_amino_acids: ['K'],
  positions: Array.from({ length: 8 }, (_, i) => ({ position: i + 1, choices: i % 2 ? ['A', 'K'] : ['G'] })),
  max_mutations: 2, goals: { ph: 7.4, target_charge: 2, charge_weight: 1, hydropathy_min: -1.5,
    hydropathy_max: .5, hydropathy_weight: .5, adjacent_repeat_weight: 0 }, layers: 1, max_iterations: 60, shots: 2048, seed: 42,
}

function loadInput(): SequenceRequest {
  try {
    const value = JSON.parse(localStorage.getItem(inputKey) ?? 'null') as SequenceRequest | null
    if (value && Array.isArray(value.positions) && value.positions.length === value.length && value.length >= 2 && value.length <= 50
      && value.positions.every((row) => Array.isArray(row.choices) && row.choices.length >= 1 && row.choices.length <= 2 && row.choices.every((letter) => residueCodes.includes(letter) && letter.length === 1))
      && Array.isArray(value.allowed_amino_acids) && Array.isArray(value.required_amino_acids) && Array.isArray(value.excluded_amino_acids)
      && value.goals && typeof value.goals.ph === 'number') return value
  } catch { /* A disabled or obsolete browser store must not prevent design. */ }
  return sample
}
function loadResult(): SequenceResult | null {
  try {
    const value = JSON.parse(localStorage.getItem(resultKey) ?? 'null') as SequenceResult | null
    return value?.contract_version === '1.0' && value.provenance === 'simulated' && value.circuit && value.benchmark && Array.isArray(value.states) ? value : null
  } catch { return null }
}
function draftFrom(request: SequenceRequest): Draft {
  return { mode: request.template_sequence ? 'redesign' : 'new', template: request.template_sequence ?? '',
    length: request.length, allowed: request.allowed_amino_acids.join(''), excluded: request.excluded_amino_acids.join(''),
    required: request.required_amino_acids.join(''), maxMutations: request.max_mutations === null ? '' : String(request.max_mutations),
    positions: request.positions.map((row) => ({ first: row.choices[0], second: row.choices[1] ?? (row.choices[0] === 'K' ? 'A' : 'K'), variable: row.choices.length === 2 })),
    goals: request.goals, layers: request.layers, max_iterations: request.max_iterations, shots: request.shots, seed: request.seed }
}
const codes = (text: string) => [...text.replace(/[\s,]/g, '').toUpperCase()]
function makeRequest(draft: Draft, templateInput: string): SequenceRequest {
  if (draft.mode === 'redesign' && templateInput.replace(/\s/g, '').toUpperCase() !== draft.template) throw new Error('Click Apply template after editing the sequence, so the position choices match it.')
  return { length: draft.positions.length, template_sequence: draft.mode === 'redesign' ? draft.template : null,
    allowed_amino_acids: codes(draft.allowed), excluded_amino_acids: codes(draft.excluded), required_amino_acids: codes(draft.required),
    positions: draft.positions.map((row, index) => ({ position: index + 1, choices: row.variable ? [row.first, row.second] : [row.first] })),
    max_mutations: draft.mode === 'redesign' && draft.maxMutations !== '' ? Number(draft.maxMutations) : null,
    goals: draft.goals, layers: draft.layers, max_iterations: draft.max_iterations, shots: draft.shots, seed: draft.seed }
}

export function SequenceDesign() {
  const [draft, setDraft] = useState(() => draftFrom(loadInput()))
  const [templateInput, setTemplateInput] = useState(() => draft.template)
  const [preview, setPreview] = useState<SequencePreview | null>(null)
  const [result, setResult] = useState<SequenceResult | null>(loadResult)
  const [busy, setBusy] = useState<'preview' | 'optimize' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const variableCount = draft.positions.filter((row) => row.variable).length
  let currentResult = false
  try { currentResult = result !== null && requestSignature(result.request) === requestSignature(makeRequest(draft, templateInput)) } catch { /* Unapplied input is a different draft. */ }

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
    setNote('Length applied. Positions start fixed to A; set their residues and select up to eight variable positions.')
  }
  async function submit(kind: 'preview' | 'optimize') {
    if (busy) return
    setError(null); setNote('')
    try {
      const request = makeRequest(draft, templateInput)
      if (draft.mode === 'new' && draft.length !== draft.positions.length) throw new Error('Click Apply length to update the position editor.')
      if (kind === 'optimize' && variableCount === 0) throw new Error('Select at least one variable position for QAOA, or use Preview to evaluate a fixed sequence.')
      setBusy(kind)
      if (kind === 'preview') {
        setPreview(await sequenceDesign.preview(request))
      } else {
        const response = await sequenceDesign.optimize(request)
        setResult(response)
        try { localStorage.setItem(resultKey, JSON.stringify(response)) }
        catch { setNote('Result displayed, but browser storage is unavailable. Download the JSON to keep it.') }
      }
      try { localStorage.setItem(inputKey, JSON.stringify(request)) }
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
    <SectionHeading eyebrow="New research workflow" title="Peptide Sequence Design" description="Design a single peptide by choosing residues at selected positions. Use QAOA to propose sequences under explicit constraints, then check them against the exact classical optimum." action={<StatusPill tone="blue">Position-based sequence optimization</StatusPill>} />
    <div className="flex flex-wrap gap-4 text-xs text-[#65717D]"><Link className="text-blue-800 underline" to="/designer">Existing peptide library and blend designer</Link><Link className="text-blue-800 underline" to="/optimization">Existing blend optimization</Link><Link className="text-blue-800 underline" to="/quantum-chemistry">Separate HeH+ quantum chemistry</Link></div>
    <Panel className="border-blue-200 bg-blue-50/40 p-4 text-sm leading-6">This is a real QAOA research prototype, not demonstrated quantum advantage. It supports 2–50 total residues and up to eight positions with two choices each. Classical chemistry defines the objective; QAOA does not predict folding, binding, reactions, or biological effects. The current execution is a local ideal simulator and uses no IBM QPU allowance.</Panel>
    <form onSubmit={(event) => { event.preventDefault(); void submit('optimize') }} className="space-y-5">
      <fieldset className="min-w-0 space-y-5" disabled={busy !== null}>
        <Panel className="space-y-4 p-5"><div className="flex items-center gap-2"><Dna className="text-blue-700" size={20} /><h2 className="text-lg font-semibold">1. Define the sequence space</h2></div>
          <label className="research-label block">Design mode<select aria-label="Design mode" className="research-select mt-1" value={draft.mode} onChange={(event) => change((previous) => ({ ...previous, mode: event.target.value as Draft['mode'] }))}><option value="redesign">Redesign an existing sequence</option><option value="new">Design a sequence from a length</option></select></label>
          {draft.mode === 'redesign' ? <div className="space-y-2"><label className="research-label block">Template sequence<textarea aria-label="Template sequence" className="research-textarea mt-1 font-mono" value={templateInput} onChange={(event) => { setTemplateInput(event.target.value); setPreview(null); setError(null) }} /></label><Button variant="secondary" onClick={applyTemplate}>Apply template</Button><p className="text-xs text-[#65717D]">Changing and applying the template resets the position editor to fixed residues. The initial example has four editable positions; it is a demonstration input, not a known therapeutic peptide.</p></div> : <div className="flex flex-wrap items-end gap-3"><label className="research-label">Requested length<input type="number" className="research-input mt-1 w-32" min={2} max={50} step={1} required value={draft.length} onChange={(event) => change((previous) => ({ ...previous, length: Number(event.target.value) }))} /></label><Button variant="secondary" onClick={initializeLength}>Apply length</Button></div>}
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="research-label">Globally allowed amino acids<input className="research-input mt-1 font-mono" value={draft.allowed} onChange={(event) => change((previous) => ({ ...previous, allowed: event.target.value.toUpperCase() }))} /></label>
            <label className="research-label">Excluded amino acids<input className="research-input mt-1 font-mono" value={draft.excluded} placeholder="Optional, e.g. C" onChange={(event) => change((previous) => ({ ...previous, excluded: event.target.value.toUpperCase() }))} /></label>
            <label className="research-label">Required at least once<input className="research-input mt-1 font-mono" value={draft.required} placeholder="Optional, e.g. KR" onChange={(event) => change((previous) => ({ ...previous, required: event.target.value.toUpperCase() }))} /></label>
          </div>
          <p className="text-xs leading-6 text-[#65717D]">Allowed does not mean required. Exclusions override the allowed set. Position choices must belong to the remaining allowed set. Use uppercase one-letter codes; commas and spaces are accepted.</p>
          <details className="text-xs"><summary className="cursor-pointer font-semibold">Show all 20 amino-acid options</summary><div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">{[...residueCodes].map((code, index) => <span key={code}><strong>{code}</strong> — {residueNames[index]}</span>)}</div></details>
        </Panel>
        <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">2. Choose fixed and editable positions</h2>
          <p className="text-sm text-[#65717D]">Unchecked positions keep option 0. Checked positions let the algorithm choose option 0 or option 1. At most eight positions can be variable; this is a software limit for the validated demonstration.</p>
          <div className="grid gap-3 sm:grid-cols-3"><MetricCard label="Total positions" value={String(draft.positions.length)} detail="Fixed length during this run" /><MetricCard label="Variable positions / qubits" value={`${variableCount}/8`} detail="One qubit per two-choice position" /><MetricCard label="Restricted design space" value={`${2 ** variableCount} sequences`} detail="Before required-residue and mutation constraints" /></div>
          <div className="max-h-96 overflow-auto rounded-lg border border-[#D9E0E7]"><table className="research-table"><thead><tr><th>Position</th><th>May change</th><th>Option 0 / fixed</th><th>Option 1</th></tr></thead><tbody>{draft.positions.map((row, index) => <tr key={index}><td>{index + 1}</td><td><input type="checkbox" aria-label={`Position ${index + 1} can change`} checked={row.variable} disabled={!row.variable && variableCount >= 8} onChange={(event) => changePosition(index, { variable: event.target.checked })} /></td>{(['first', 'second'] as const).map((key) => <td key={key}><select aria-label={`Position ${index + 1} option ${key === 'first' ? 0 : 1}`} className="research-select min-w-32" disabled={key === 'second' && !row.variable} value={row[key]} onChange={(event) => changePosition(index, { [key]: event.target.value })}>{[...residueCodes].map((code, i) => <option key={code} value={code}>{code} · {residueNames[i]}</option>)}</select></td>)}</tr>)}</tbody></table></div>
          {draft.mode === 'redesign' && <label className="research-label block">Maximum changes from template (blank = no budget)<input className="research-input mt-1 w-40" type="number" min={0} max={draft.positions.length} step={1} value={draft.maxMutations} onChange={(event) => change((previous) => ({ ...previous, maxMutations: event.target.value }))} /></label>}
        </Panel>
        <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">3. Set chemical research goals</h2><p className="text-sm leading-6 text-[#65717D]">pH is the surrounding solution condition. The algorithm targets estimated net charge at that pH. Hydropathy range and charge are soft preferences, not guaranteed outcomes. Required residues and the mutation budget are hard constraints.</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{goalFields.map((field) => <label className="research-label" key={field.key}>{field.label}<input className="research-input mt-1" type="number" required min={field.min} max={field.max} step={field.step} value={Number.isFinite(draft.goals[field.key]) ? draft.goals[field.key] : ''} onChange={(event) => change((previous) => ({ ...previous, goals: { ...previous.goals, [field.key]: event.target.value === '' ? Number.NaN : Number(event.target.value) } }))} /></label>)}</div>
          <p className="text-xs leading-6 text-[#65717D]">At least one weight must be positive. The optional adjacent-repeat weight discourages identical neighboring residues as a design preference, not a stability prediction. With composition-only scores, different residue orders may tie.</p>
        </Panel>
        <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">4. Validate and run QAOA</h2><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{([{ key: 'layers', label: 'QAOA layers', min: 1, max: 2 }, { key: 'max_iterations', label: 'Objective evaluation budget', min: 10, max: 120 }, { key: 'shots', label: 'Simulated shots', min: 128, max: 8192 }, { key: 'seed', label: 'Random seed', min: 0, max: 2147483647 }] as const).map((field) => <label className="research-label" key={field.key}>{field.label}<input className="research-input mt-1" type="number" required min={field.min} max={field.max} step={1} value={Number.isFinite(draft[field.key]) ? draft[field.key] : ''} onChange={(event) => change((previous) => ({ ...previous, [field.key]: event.target.value === '' ? Number.NaN : Number(event.target.value) }))} /></label>)}</div>
          <div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => void submit('preview')}><ScanSearch size={15} /> Validate and preview</Button><Button type="submit" disabled={variableCount === 0}><Play size={15} /> Run Sequence QAOA</Button><Button variant="ghost" onClick={() => { change(() => draftFrom(sample)); setTemplateInput(sample.template_sequence!) }}>Load demonstration input</Button></div>
          <p className="text-xs text-[#65717D]">Preview works for fully fixed sequences. Runs require at least one editable position. Nothing runs automatically when you change a field. Last successfully submitted inputs and the latest result are saved in this browser when storage is available.</p>
        </Panel>
      </fieldset>
      {busy && <p role="status" className="flex items-center gap-2 rounded-lg bg-blue-50 p-4 text-sm text-blue-900"><LoaderCircle className="animate-spin" size={18} />{busy === 'preview' ? 'Calculating chemistry and validating the restricted sequence space…' : 'Fitting the quantum circuit, sampling sequences, and checking the exact classical reference…'}</p>}
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">{error}</p>}
      {note && <p role="status" className="text-sm text-[#65717D]">{note}</p>}
    </form>
    {preview && <Panel className="space-y-3 p-5" aria-label="Validated sequence design space"><h2 className="text-lg font-semibold">Validated design space</h2><p className="text-sm">{preview.qubits} qubits, {preview.state_count} possible sequences, {preview.feasible_state_count} feasible sequences. Cost representation: {preview.cost_representation.replaceAll('_', ' ')} (degree {preview.cost_polynomial_degree}).</p>{preview.template_properties && <p className="text-sm">Template at pH {preview.request.goals.ph}: charge {preview.template_properties.charge.toFixed(3)} e, GRAVY {preview.template_properties.hydropathy.toFixed(3)}, mass {preview.template_properties.mass_da.toFixed(2)} Da.</p>}<p className="text-xs text-[#65717D]">Calculated preview only; no QAOA circuit has been run by this preview action.</p></Panel>}
    {result && <SequenceDesignResults key={result.experiment_id} result={result} current={currentResult} />}
  </div>
}
