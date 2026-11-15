import { useMemo, useState } from 'react'
import { Dna, FlaskConical, Save, SlidersHorizontal } from 'lucide-react'
import { demoBlendConfiguration, demoCandidates } from '../../demo/researchDemo'
import { Button, Panel, SectionHeading, StatusPill } from '../../components/ui'
import type { SelectedPeptideCandidate } from '../../types/peptideLibrary'
import { MockDataNotice } from '../shared/MockDataNotice'
import { CandidatePoolTable } from './CandidatePoolTable'
import { PeptideLibraryPanel } from './PeptideLibraryPanel'
import { PeptideBlendResearch } from './PeptideBlendResearch'
import type { BlendCandidate } from '../../services/blendResearch'

const aminoAcids = ['A', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'W', 'Y']

const aminoAcidGroups = [
  { label: 'Hydrophobic', members: 'A, V, I, L, M, F, W, Y' },
  { label: 'Polar', members: 'S, T, N, Q, C' },
  { label: 'Charged', members: 'D, E, K, R, H' },
]

function replaceResidue(sequence: string, position: number, residue: string): string {
  if (position < 1 || position > sequence.length) {
    return sequence
  }

  return `${sequence.slice(0, position - 1)}${residue}${sequence.slice(position)}`
}

export function PeptideDesigner({ embedded = false, onUseTemplate }: { embedded?: boolean; onUseTemplate?: (candidate: BlendCandidate) => void }) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(demoCandidates.filter((candidate) => candidate.selected).map((candidate) => candidate.id)),
  )
  const [blendSize, setBlendSize] = useState(demoBlendConfiguration.selectedCount)
  const [targetPh, setTargetPh] = useState(demoBlendConfiguration.targetPh)
  const [activeCandidateId, setActiveCandidateId] = useState(demoCandidates[0].id)
  const [position, setPosition] = useState(5)
  const [replacement, setReplacement] = useState('Y')
  const [weights, setWeights] = useState(demoBlendConfiguration.propertyWeights)
  const [draftStatus, setDraftStatus] = useState('Interface draft has not been submitted.')
  const [libraryCandidates, setLibraryCandidates] = useState<SelectedPeptideCandidate[]>([])

  const activeCandidate = useMemo(
    () => demoCandidates.find((candidate) => candidate.id === activeCandidateId) ?? demoCandidates[0],
    [activeCandidateId],
  )
  const substitutedResidue = activeCandidate.sequence.at(position - 1) ?? '—'
  const variantSequence = replaceResidue(activeCandidate.sequence, position, replacement)
  const selectedCandidates = demoCandidates.filter((candidate) => selectedIds.has(candidate.id))
  const librarySelectedIds = useMemo(
    () => new Set(libraryCandidates.map((candidate) => candidate.peptideId)),
    [libraryCandidates],
  )

  function toggleCandidate(candidateId: string) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(candidateId)) {
        next.delete(candidateId)
      } else if (next.size < blendSize) {
        next.add(candidateId)
      }
      return next
    })
  }

  function updateBlendSize(nextSize: number) {
    setBlendSize(nextSize)
    setSelectedIds((current) => new Set([...current].slice(0, nextSize)))
  }

  function updateWeight(label: string, value: number) {
    setWeights((current) => current.map((weight) => (weight.label === label ? { ...weight, value } : weight)))
  }

  function toggleLibraryCandidate(candidate: SelectedPeptideCandidate) {
    setLibraryCandidates((current) => {
      if (current.some((selected) => selected.peptideId === candidate.peptideId)) {
        return current.filter((selected) => selected.peptideId !== candidate.peptideId)
      }
      return current.length < 8 ? [...current, candidate] : current
    })
  }

  return (
    <div className="space-y-6">
      {!embedded && <SectionHeading
        eyebrow="Candidate configuration"
        title="Peptide Designer"
        description="Choose known peptide candidates and chemical goals, then continue to Blend Optimization to run QAOA on the selected pool."
        action={<StatusPill tone="blue">Database + quantum research</StatusPill>}
      />}

      <PeptideBlendResearch onUseTemplate={onUseTemplate} />

      <details className="space-y-4 rounded-lg border border-slate-200 p-4">
      <summary className="cursor-pointer text-sm font-semibold">Additional library controls and legacy previews</summary>
      <MockDataNotice detail="The older configuration controls, weights, and candidate previews BELOW this notice remain display fixtures. Use the live candidate pool ABOVE, then Continue to Blend Optimization for an actual QAOA run." />

      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel className="p-5">
          <div className="flex items-start gap-3">
            <span className="rounded-lg bg-blue-50 p-2 text-blue-700"><FlaskConical size={18} aria-hidden="true" /></span>
            <div>
              <p className="research-eyebrow">Research inputs</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]">Targets and blend definition</h2>
              <p className="mt-1 text-sm leading-6 text-[#657B85]">These controls remain local to the interface until a validated scoring and API contract is available.</p>
            </div>
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <label className="research-label">Target pH
              <input className="research-input mt-1.5" inputMode="decimal" onChange={(event) => setTargetPh(event.target.value)} value={targetPh} />
              <span className="mt-1 block text-[11px] font-normal text-[#78909A]">UI setting; no charge calculation is performed.</span>
            </label>
            <label className="research-label">Peptides in blend
              <select className="research-select mt-1.5" onChange={(event) => updateBlendSize(Number(event.target.value))} value={blendSize}>
                {[2, 3, 4].map((value) => <option key={value} value={value}>{value} candidates</option>)}
              </select>
              <span className="mt-1 block text-[11px] font-normal text-[#78909A]">MVP reference setting: select 3 of 8.</span>
            </label>
            <label className="research-label">Constraint note
              <input className="research-input mt-1.5" defaultValue="No exclusions declared" />
              <span className="mt-1 block text-[11px] font-normal text-[#78909A]">Stored only in this page state.</span>
            </label>
          </div>
        </Panel>

        <Panel className="p-5">
          <p className="research-eyebrow">Selection summary</p>
          <div className="mt-2 flex items-baseline justify-between gap-3">
            <h2 className="text-lg font-semibold text-[#28323C]">{selectedIds.size} of {blendSize} selected</h2>
            <StatusPill tone={selectedIds.size === blendSize ? 'blue' : 'amber'}>
              {selectedIds.size === blendSize ? 'Ready for review' : 'Complete selection'}
            </StatusPill>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-[#F7FBFB] p-3"><p className="text-xs text-[#708690]">Candidate pool</p><p className="mt-1 font-semibold text-[#203B46]">{demoCandidates.length} candidates</p></div>
            <div className="rounded-lg bg-[#F7FBFB] p-3"><p className="text-xs text-[#708690]">Reference search space</p><p className="mt-1 font-semibold text-[#203B46]">{demoBlendConfiguration.feasibleSubsets} subsets</p></div>
          </div>
          <p className="mt-4 text-xs leading-5 text-[#657B85]">The 56-subset count applies only to the stated 8-candidate, 3-selection reference configuration. It is not an optimization result.</p>
        </Panel>
      </div>

      <PeptideLibraryPanel
        maxSelections={8}
        onToggle={toggleLibraryCandidate}
        selectedIds={librarySelectedIds}
      />

      {libraryCandidates.length > 0 && (
        <Panel className="p-5" aria-labelledby="future-qaoa-candidates-heading">
          <p className="research-eyebrow">Future QAOA hand-off</p>
          <div className="mt-1 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-lg font-semibold text-[#28323C]" id="future-qaoa-candidates-heading">Validated imported candidates</h2>
            <StatusPill tone={libraryCandidates.length === 8 ? 'blue' : 'amber'}>{libraryCandidates.length} of 8 selected</StatusPill>
          </div>
          <p className="mt-2 text-sm leading-6 text-[#657B85]">This typed selection retains peptide IDs, sequences, source accessions, and special-handling flags for a future blend-optimization contract. It has not been scored or sent to QAOA.</p>
          <ul className="mt-4 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
            {libraryCandidates.map((candidate) => (
              <li className="rounded-md border border-[#D9E0E7] bg-[#FCFEFE] p-3" key={candidate.peptideId}>
                <p className="font-semibold text-[#394957]">{candidate.name}</p>
                <p className="mt-1 break-all font-mono text-xs tracking-[0.07em] text-[#65717D]">{candidate.sequence}</p>
                <p className="mt-2 text-[11px] text-[#718791]">{candidate.sourceDatabase} · {candidate.sourceAccession}</p>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-[#D9E0E7] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="research-eyebrow">Candidate pool</p>
            <h2 className="mt-1 text-lg font-semibold text-[#28323C]">Select entire peptide candidates</h2>
          </div>
          <p className="max-w-md text-sm leading-5 text-[#657B85]">Selection is a local preview. Each later QAOA variable represents a whole candidate—not an amino acid position.</p>
        </div>
        <div className="p-2 sm:p-3">
          <CandidatePoolTable candidates={demoCandidates} onToggle={toggleCandidate} selectedIds={selectedIds} selectionLimit={blendSize} />
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[1fr_1.05fr]">
        <Panel className="p-5">
          <div className="flex items-start gap-3">
            <span className="rounded-lg bg-[#EFF7F7] p-2 text-blue-700"><Dna size={18} aria-hidden="true" /></span>
            <div>
              <p className="research-eyebrow">Position-specific variant</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]">Sequence comparison workspace</h2>
            </div>
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-3">
            <label className="research-label sm:col-span-3">Source candidate
              <select className="research-select mt-1.5" onChange={(event) => setActiveCandidateId(event.target.value)} value={activeCandidateId}>
                {demoCandidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.id} · {candidate.sequence}</option>)}
              </select>
            </label>
            <label className="research-label">Position (1-based)
              <select className="research-select mt-1.5" onChange={(event) => setPosition(Number(event.target.value))} value={position}>
                {Array.from({ length: activeCandidate.sequence.length }, (_, index) => index + 1).map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <label className="research-label">Current residue
              <input className="research-input mt-1.5 bg-slate-50" disabled value={substitutedResidue} />
            </label>
            <label className="research-label">Variant residue
              <select className="research-select mt-1.5" onChange={(event) => setReplacement(event.target.value)} value={replacement}>
                {aminoAcids.map((residue) => <option key={residue} value={residue}>{residue}</option>)}
              </select>
            </label>
          </div>

          <div className="mt-5 rounded-lg border border-[#D9E0E7] bg-[#FCFEFE] p-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div><p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#728993]">Source</p><p className="mt-2 break-all font-mono text-sm tracking-[0.12em] text-[#203B46]">{activeCandidate.sequence}</p></div>
              <div><p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#728993]">Unsubmitted variant</p><p className="mt-2 break-all font-mono text-sm tracking-[0.12em] text-blue-800">{variantSequence}</p></div>
            </div>
            <p className="mt-3 text-xs leading-5 text-[#657B85]">Position {position}: {substitutedResidue} → {replacement}. This is a UI variant preview, not a generated candidate or a biochemical prediction.</p>
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-start gap-3">
            <span className="rounded-lg bg-[#F4F7FB] p-2 text-[#315D76]"><SlidersHorizontal size={18} aria-hidden="true" /></span>
            <div>
              <p className="research-eyebrow">Objective emphasis</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]">Research-priority weights</h2>
              <p className="mt-1 text-sm leading-6 text-[#657B85]">Interface-only controls; numeric values are not chemistry scores or an approved objective.</p>
            </div>
          </div>
          <div className="mt-5 space-y-5">
            {weights.map((weight) => (
              <label key={weight.label} className="block">
                <span className="flex items-center justify-between gap-3 text-sm font-medium text-[#36505C]">
                  {weight.label}<span className="font-mono text-xs text-[#087E78]">{weight.value.toFixed(2)}</span>
                </span>
                <input
                  aria-label={`${weight.label} weight`}
                  className="mt-2 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[#D8E6E8] accent-[#087E78]"
                  max="1"
                  min="0"
                  onChange={(event) => updateWeight(weight.label, Number(event.target.value))}
                  step="0.05"
                  type="range"
                  value={weight.value}
                />
              </label>
            ))}
          </div>
          <div className="mt-6 flex flex-wrap gap-3 border-t border-[#E7EFF1] pt-5">
            <Button onClick={() => setDraftStatus('Interface draft marked ready for backend review. No data was submitted.')}><Save size={15} aria-hidden="true" /> Save interface draft</Button>
            <Button onClick={() => setDraftStatus('Variant preview retained locally for comparison. No candidate was generated.')} variant="secondary">Keep variant preview</Button>
          </div>
          <p aria-live="polite" className="mt-3 text-xs leading-5 text-[#657B85]">{draftStatus}</p>
        </Panel>
      </div>

      <Panel className="p-5">
        <p className="research-eyebrow">Reference groups</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {aminoAcidGroups.map((group) => (
            <div key={group.label} className="rounded-lg border border-[#E2ECEF] bg-[#FCFEFE] p-3">
              <p className="text-sm font-semibold text-[#36505C]">{group.label}</p>
              <p className="mt-1 font-mono text-xs leading-5 text-[#657B85]">{group.members}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs leading-5 text-[#738992]">These residue categories are an interaction aid only. They do not assign descriptors, compatibility, or scores to a candidate.</p>
      </Panel>

      {selectedCandidates.length > 0 && (
        <p className="text-xs text-[#6B818B]">Current local blend preview: {selectedCandidates.map((candidate) => candidate.id).join(', ')}.</p>
      )}
      </details>
    </div>
  )
}
