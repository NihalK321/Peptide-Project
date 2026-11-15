import { HardwareExecutionControl } from '../shared/HardwareExecution'
import { useHardwareExecution } from '../shared/useHardwareExecution'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { LoaderCircle, RefreshCw } from 'lucide-react'
import { Button, StatusPill } from '../../components/ui'
import { generateMolecularStructure } from '../../services/molecularStructure'
import type { GeneratedStructure } from '../../services/molecularStructure'
import { MolecularStructureViewer } from './MolecularStructureViewer'

export function GeneratedMolecularStructure() {
  const hardware = useHardwareExecution('torsion')
  const [sequence, setSequence] = useState('GAGA')
  const [request, setRequest] = useState({ sequence: 'GAGA', revision: 0 })
  const [result, setResult] = useState<GeneratedStructure | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [inputError, setInputError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void generateMolecularStructure(request.sequence, controller.signal)
      .then((structure) => {
        if (!controller.signal.aborted) setResult(structure)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          const detail = reason instanceof Error ? reason.message : 'Unknown structure service error.'
          setError(`Could not load the model. Check that the FastAPI backend is running on the configured structure API URL. ${detail}`)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [request])

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const normalized = sequence.trim().toUpperCase()
    if (!/^[ACDEFGHIKLMNPQRSTVWY]{2,8}$/.test(normalized)) {
      setInputError('Enter 2–8 standard one-letter amino-acid codes, for example GAGA.')
      return
    }
    setInputError(null)
    if (hardware.enabled) {
      void hardware.run('torsion', { sequence: normalized, method: 'qaoa', torsion_count: 3, layers: 1, max_iterations: 30, seed: 42 }).catch((reason: unknown) => setInputError(reason instanceof Error ? reason.message : 'Hardware torsion run failed.'))
      return
    }
    setSequence(normalized)
    setLoading(true)
    setResult(null)
    setError(null)
    setRequest((previous) => ({ sequence: normalized, revision: previous.revision + 1 }))
  }

  return (
    <div className="space-y-4">
      <HardwareExecutionControl execution={hardware} disabled={loading || hardware.busy} />
      {hardware.enabled && <p className="text-xs text-slate-600">Generate now submits the peptide torsion QAOA circuit to IBM after local fitting. The 3D viewer remains a separately calculated classical conformer; hardware measurements and chosen angles appear above.</p>}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-[#28323C]">Structure stats</h3>
          <p className="mt-1 text-xs leading-5 text-[#667E88]">A short peptide model loaded directly from the backend, without downloading or uploading a file.</p>
        </div>
        <StatusPill tone={loading ? 'slate' : result ? 'blue' : 'amber'}>
          {loading ? 'Generating model' : result ? 'Calculated conformer' : 'Model unavailable'}
        </StatusPill>
      </div>

      <form className="flex flex-wrap items-end gap-2" onSubmit={handleSubmit}>
        <label className="min-w-0 flex-1 text-xs font-medium text-[#46616B]" htmlFor="structure-sequence">
          Sequence to model (2–8 residues)
          <input
            aria-describedby={inputError ? 'structure-sequence-error' : undefined}
            aria-invalid={Boolean(inputError)}
            className="mt-1 block w-full rounded-md border border-[#BFD2D7] bg-white px-3 py-2 font-mono text-sm uppercase text-[#173B46]"
            id="structure-sequence" onChange={(event) => setSequence(event.target.value)}
            placeholder="GAGA" value={sequence}
          />
        </label>
        <Button disabled={loading || hardware.busy} type="submit" variant="secondary">
          {loading ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
          {loading ? 'Generating' : hardware.enabled ? 'Run torsion circuit on IBM QPU' : 'Show structure'}
        </Button>
      </form>
      {inputError && <p className="text-sm text-red-700" id="structure-sequence-error" role="alert">{inputError}</p>}

      {loading && (
        <div aria-live="polite" className="flex h-[28rem] items-center justify-center gap-3 rounded-lg border border-[#D9E0E7] bg-[#F3F5F7] text-sm text-[#526D78]" role="status">
          <LoaderCircle className="h-5 w-5 animate-spin" aria-hidden="true" /> Building the 3D peptide model…
        </div>
      )}
      {error && <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900" role="alert">{error}</div>}

      {result && (
        <>
          <dl className="grid grid-cols-2 gap-2 rounded-lg bg-[#F4F8F9] p-3 text-xs sm:grid-cols-3">
            <div><dt className="text-[#667E88]">Modeled sequence</dt><dd className="mt-1 font-mono font-semibold text-[#394957]">{result.sequence}</dd></div>
            <div><dt className="text-[#667E88]">Residues</dt><dd className="mt-1 font-semibold text-[#394957]">{result.sequence.length}</dd></div>
            <div><dt className="text-[#667E88]">Selected grid configuration</dt><dd className="mt-1 font-mono font-semibold text-[#394957]">{result.best_configuration.bitstring}</dd></div>
          </dl>
          <MolecularStructureViewer
            initialStructure={{ text: result.best_structure_pdb, name: `${result.sequence}.pdb` }}
            key={`${request.sequence}-${request.revision}`}
          />
          <p className="text-xs leading-5 text-[#667E88]">
            Model: {result.energy_model}. Classical search of two choices for each of {result.torsions.length} backbone torsions (seed 42).
            This model uses the sequence above, independently of the demo candidate record. It is a generated conformer, not a measured structure or a full folding prediction.
          </p>
        </>
      )}
    </div>
  )
}
