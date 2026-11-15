import { useEffect, useState } from 'react'
import { Database, LoaderCircle, ArrowRight, Search, WandSparkles, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button, Panel, StatusPill } from '../../components/ui'
import { blendResearch } from '../../services/blendResearch'
import type { BlendCandidate, CatalogPage, ChemicalGoals } from '../../services/blendResearch'
import { isWorkspacePersisted, updateBlendWorkspace, validateBlendWorkspace } from '../../services/blendWorkspace'
import { useBlendWorkspace } from '../shared/useBlendWorkspace'

export function PeptideBlendResearch({ onUseTemplate }: { onUseTemplate?: (candidate: BlendCandidate) => void }) {
  const draft = useBlendWorkspace()
  const { goals, pool, blendSize } = draft
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState({ query: '', page: 1, revision: 0 })
  const [catalog, setCatalog] = useState<CatalogPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'shortlist' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  function setPool(update: BlendCandidate[] | ((previous: BlendCandidate[]) => BlendCandidate[])) {
    updateBlendWorkspace((previous) => ({ ...previous, pool: typeof update === 'function' ? update(previous.pool) : update }))
  }

  useEffect(() => {
    const controller = new AbortController()
    void blendResearch.catalog(search.query, search.page, controller.signal)
      .then((response) => { if (!controller.signal.aborted) setCatalog(response) })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Could not load the local catalog.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [search])

  function updateGoal(key: keyof ChemicalGoals, value: number) {
    updateBlendWorkspace((previous) => ({ ...previous, goals: { ...previous.goals, [key]: value },
      pool: previous.pool.map(({ score: _score, charge: _charge, hydropathy: _hydropathy, ...candidate }) => candidate) }))
    setNote('Targets changed. Rerank the catalog or continue to Optimization; previous scores are no longer current.')
  }

  function browse(page = 1) {
    setLoading(true)
    setError(null)
    setSearch((previous) => ({ query: query.trim(), page, revision: previous.revision + 1 }))
  }

  function toggle(candidate: BlendCandidate) {
    setPool((previous) => previous.some((item) => item.id === candidate.id)
      ? previous.filter((item) => item.id !== candidate.id)
      : previous.length < 8 ? [...previous, candidate] : previous)
  }

  async function autoShortlist() {
    setBusy('shortlist'); setError(null)
    try {
      if (goals.charge_weight + goals.hydropathy_weight <= 0) throw new Error('Set at least one property weight above zero.')
      const response = await blendResearch.shortlist(goals, query.trim())
      setPool(response.candidates)
      setNote(`Classically scored ${response.scored_count.toLocaleString()} matching, eligible sequences and shortlisted ${response.candidates.length}. ${response.shortlist_method}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Shortlisting failed.')
    } finally { setBusy(null) }
  }

  const inputs: { key: keyof ChemicalGoals; label: string; min: number; max: number; step: number }[] = [
    { key: 'ph', label: 'pH for charge estimate', min: 2, max: 12, step: 0.1 },
    { key: 'target_charge', label: 'Target candidate charge (e)', min: -20, max: 20, step: 0.5 },
    { key: 'target_hydropathy', label: 'Target candidate hydropathy', min: -4.5, max: 4.5, step: 0.1 },
    { key: 'charge_weight', label: 'Charge score weight', min: 0, max: 1, step: 0.05 },
    { key: 'hydropathy_weight', label: 'Hydropathy score weight', min: 0, max: 1, step: 0.05 },
    { key: 'diversity_weight', label: 'Sequence redundancy penalty', min: 0, max: 2, step: 0.1 },
  ]

  return (
    <div className="space-y-5" aria-label="Database-backed quantum blend research">
      <Panel className="min-w-0 space-y-5 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3"><Database className="h-5 w-5 text-teal-700" /><div><p className="research-eyebrow">Live local database + QAOA</p><h2 className="mt-1 text-lg font-semibold">{onUseTemplate ? 'Browse known peptides' : 'Find a chemical-property research blend'}</h2></div></div>
          <StatusPill tone={catalog ? 'blue' : 'amber'}>{catalog ? `${catalog.catalog.imported_source_records.toLocaleString()} imported source records` : 'Connecting to catalog'}</StatusPill>
        </div>
        <p className="text-sm leading-6 text-[#526A75]">{onUseTemplate && 'Choose Use as template to design a single sequence from a database peptide. Imported templates start with all positions locked; the sequence editor supports 2–50 standard residues. '}For a blend, set chemical goals and choose up to eight known sequences, then continue to the separate Blend Optimization page. Classical shortlisting searches the catalog; QAOA selects only from the small pool.</p>
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-6 text-amber-900">This selects research candidates by estimated charge, hydropathy, and motif diversity. It does not predict appetite effects, muscle growth, physical compatibility, or efficacy of a mixture. Scores assume linear free-termini sequences; chemical forms are not verified.</div>
        <fieldset className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" disabled={busy !== null}>
          <legend className="sr-only">Chemical goals</legend>
          {inputs.map((input) => <label className="research-label" key={input.key}>{input.label}<input className="research-input mt-1.5" type="number" min={input.min} max={input.max} step={input.step} value={goals[input.key]} onChange={(event) => updateGoal(input.key, Number(event.target.value))} /></label>)}
        </fieldset>
        <div className="flex flex-wrap gap-2">
          <input aria-label="Search known peptides for blending" className="research-input min-w-0 flex-1" placeholder="Search names or sequences (blank searches the full local catalog)" value={query} disabled={busy !== null} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') browse() }} />
          <Button disabled={busy !== null || loading} onClick={() => browse()} variant="secondary"><Search size={15} /> Search</Button>
          <Button disabled={busy !== null || loading || !catalog?.catalog.unique_eligible_sequences} onClick={() => void autoShortlist()}><WandSparkles size={15} /> {busy === 'shortlist' ? 'Scoring catalog…' : 'Auto-shortlist 8'}</Button>
        </div>
        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
        {loading ? <p className="flex items-center gap-2 text-sm" role="status"><LoaderCircle className="h-4 w-4 animate-spin" /> Loading real database records…</p> : catalog && (
          <>
            <p className="text-xs text-[#607883]">{catalog.total.toLocaleString()} matching eligible sequences. Explicit modifications and unsupported residues are excluded; duplicate sequences are collapsed.</p>
            <div className="max-h-80 overflow-auto rounded-lg border border-[#DCE7EC]">
              <table className="research-table min-w-[38rem]"><thead><tr><th>Pool</th><th>Known peptide</th><th>Sequence / source</th>{onUseTemplate && <th>Sequence design</th>}</tr></thead><tbody>
                {catalog.items.map((candidate) => {
                  const selected = pool.some((item) => item.id === candidate.id)
                  return <tr key={candidate.id}><td><input aria-label={`Include ${candidate.name}`} type="checkbox" checked={selected} disabled={busy !== null || (!selected && (pool.length >= 8 || candidate.sequence.length > 60))} onChange={() => toggle(candidate)} /></td><td className="font-semibold">{candidate.name}<p className="mt-1 text-xs font-normal">{candidate.sequence.length} residues</p></td><td><p className="max-w-md break-all font-mono text-xs">{candidate.sequence}</p><a className="mt-1 inline-block text-xs text-teal-800 underline" href={candidate.source_url} rel="noreferrer" target="_blank">{candidate.source}: {candidate.accession}</a></td>{onUseTemplate && <td><Button variant="secondary" aria-label={`Use ${candidate.name} as template`} disabled={busy !== null || !/^[ACDEFGHIKLMNPQRSTVWY]{2,50}$/.test(candidate.sequence)} onClick={() => onUseTemplate(candidate)}>Use as template</Button>{candidate.sequence.length > 50 && <p className="mt-1 text-xs text-slate-500">Exceeds the 50-residue editor limit</p>}</td>}</tr>
                })}
              </tbody></table>
              {!catalog.items.length && <p className="p-4 text-sm">No eligible records match. Import source data or clear the search; no example records are substituted.</p>}
            </div>
            <div className="flex items-center justify-between text-xs text-[#607883]"><Button disabled={busy !== null || catalog.page <= 1} variant="ghost" onClick={() => browse(catalog.page - 1)}>Previous</Button><span>Page {catalog.page} of {Math.max(1, Math.ceil(catalog.total / catalog.page_size))}</span><Button disabled={busy !== null || catalog.page * catalog.page_size >= catalog.total} variant="ghost" onClick={() => browse(catalog.page + 1)}>Next</Button></div>
          </>
        )}
        <div className="border-t border-[#DCE7EC] pt-4">
          <div className="flex flex-wrap items-end justify-between gap-3"><div><h3 className="font-semibold">Quantum candidate pool: {pool.length}/8</h3><p className="mt-1 text-xs text-[#607883]">One qubit per peptide. Choose fewer blend members than pool candidates.</p></div>
            <label className="research-label">Peptides to select<input aria-label="Peptides in blend" className="research-input mt-1 w-24" type="number" min={1} max={7} disabled={busy !== null} value={blendSize} onChange={(event) => updateBlendWorkspace((previous) => ({ ...previous, blendSize: Number(event.target.value) }))} /></label></div>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">{pool.map((candidate, index) => <li className="rounded-md border border-[#DCE7EC] p-3 text-xs" key={candidate.id}><div className="flex items-start justify-between gap-1"><span className="font-semibold">q{index}: {candidate.name}</span><button aria-label={`Remove ${candidate.name}`} disabled={busy !== null} onClick={() => toggle(candidate)} type="button"><X size={14} /></button></div><p className="mt-2 break-all font-mono">{candidate.sequence}</p>{candidate.score !== undefined && <p className="mt-2 text-teal-800">Calculated score: {candidate.score.toFixed(4)}</p>}</li>)}</ul>
          <Button className="mt-4" disabled={busy !== null || pool.length < 2 || pool.length <= blendSize || blendSize < 1 || !Number.isInteger(blendSize)} onClick={() => { const problem = validateBlendWorkspace(draft, false); if (problem) setError(problem); else navigate('/optimization') }}>Continue to Blend Optimization <ArrowRight size={15} /></Button>
          <p className="mt-2 text-xs text-[#607883]">{isWorkspacePersisted() ? 'Candidates and targets are saved in this browser.' : 'Browser storage is unavailable. Your draft is shared between pages for this visit, but will be lost on refresh.'} QAOA runs on the next page.</p>
          {busy && <LoaderCircle className="ml-3 inline-block h-4 w-4 animate-spin text-teal-700" aria-label="Working" />}
        </div>
        {note && <p className="text-xs leading-6 text-[#607883]" role="status">{note}</p>}
      </Panel>
    </div>
  )
}
