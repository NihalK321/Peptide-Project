import { HardwareExecutionControl } from '../shared/HardwareExecution'
import { useHardwareExecution } from '../shared/useHardwareExecution'
import { useEffect, useMemo, useState } from 'react'
import { Braces, CircuitBoard, FlaskConical, Info, Orbit } from 'lucide-react'
import { Button, EmptyState, MetricCard, Panel, SectionHeading, StatusPill } from '../../components/ui'
import { loadVerifiedHehExperiment } from '../../services/quantumChemistry'
import { createUnavailableHehExperiment } from '../../types/quantumChemistry'
import type { HeHExperiment, HeHEnergyPoint } from '../../types/quantumChemistry'
import { HeHStructureDiagram } from './HeHStructureDiagram'
import { ChartContextNote, EnergyErrorChart, PotentialEnergySurfaceChart, VqeConvergenceChart } from './HeHEnergyVisualizations'

const fallbackBondDistanceOptions = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3]

function statusTone(status: HeHExperiment['calculationStatus']): 'blue' | 'amber' | 'slate' | 'red' {
  if (status === 'completed') return 'blue'
  if (status === 'failed') return 'red'
  if (status === 'queued' || status === 'running') return 'amber'
  return 'slate'
}

function statusLabel(status: HeHExperiment['calculationStatus']): string {
  return status.replace('_', ' ')
}

function displaySpecified(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '' || value === 'not_specified') return 'Not yet specified'
  return typeof value === 'string' ? value.replaceAll('_', ' ') : String(value)
}

function formatEnergy(value: number | null): string {
  if (value === null) return 'Unavailable'
  return Math.abs(value) > 0 && Math.abs(value) < 1e-6 ? `${value.toExponential(3)} Ha` : `${value.toFixed(12)} Ha`
}

/** Quantum chemistry is intentionally separate from the peptide QAOA workflow. */
export function HeHQuantumChemistry({ experiment: suppliedExperiment }: { experiment?: HeHExperiment }) {
  const hardware = useHardwareExecution('heh')
  const [hardwareError, setHardwareError] = useState('')
  const [bundledExperiment, setBundledExperiment] = useState<HeHExperiment | null>(null)
  const [artifactError, setArtifactError] = useState<string | null>(null)
  const [bondDistance, setBondDistance] = useState(1.0)

  useEffect(() => {
    if (suppliedExperiment) return

    const controller = new AbortController()
    void loadVerifiedHehExperiment(controller.signal)
      .then((result) => { if (!controller.signal.aborted) setBundledExperiment(result) })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setArtifactError(error instanceof Error ? error.message : 'The verified HeH+ result artifact could not be loaded.')
        }
      })

    return () => controller.abort()
  }, [suppliedExperiment])

  const experiment = suppliedExperiment ?? bundledExperiment ?? createUnavailableHehExperiment()
  const isLoadingVerifiedArtifact = !suppliedExperiment && bundledExperiment === null && artifactError === null
  const calculatedDistances = useMemo(
    () => [...new Set(experiment.bondDistancesAngstrom)].sort((first, second) => first - second),
    [experiment.bondDistancesAngstrom],
  )
  const bondDistanceOptions = calculatedDistances.length > 0 ? calculatedDistances : fallbackBondDistanceOptions
  const selectedDistanceIndex = bondDistanceOptions.reduce(
    (nearestIndex, distance, index) => Math.abs(distance - bondDistance) < Math.abs(bondDistanceOptions[nearestIndex] - bondDistance) ? index : nearestIndex,
    0,
  )
  const selectedEnergyPoint = experiment.energyPoints.find((point) => Math.abs(point.bondDistanceAngstrom - bondDistance) < 0.0001)
  const selectedConvergence = useMemo(
    () => experiment.convergenceHistory.find((entry) => Math.abs(entry.bondDistanceAngstrom - bondDistance) < 0.0001)?.points ?? [],
    [bondDistance, experiment.convergenceHistory],
  )
  const vqeEnergyPoints = experiment.energyPoints.filter((point) => point.vqeEnergyHartree !== null)
  const lowestSampledVqePoint = vqeEnergyPoints.reduce<HeHEnergyPoint | undefined>((minimum, point) => {
    const energy = point.vqeEnergyHartree
    const minimumEnergy = minimum?.vqeEnergyHartree
    if (energy === null || energy === undefined) return minimum
    if (minimumEnergy === undefined || minimumEnergy === null || energy < minimumEnergy) return point
    return minimum
  }, undefined)

  const methodology = [
    { label: 'Ansatz', value: displaySpecified(experiment.method.ansatz), rationale: experiment.method.ansatz ? 'Verified configuration from the exported calculation record.' : 'Not yet specified by a calculation record.' },
    { label: 'Fermion-to-qubit mapping', value: displaySpecified(experiment.method.fermionToQubitMapping), rationale: experiment.method.fermionToQubitMapping ? 'Used without qubit reduction for the verified calculation.' : 'Not yet specified by a calculation record.' },
    { label: 'Classical optimizer', value: displaySpecified(experiment.method.classicalOptimizer), rationale: experiment.method.classicalOptimizer ? 'The displayed convergence record is specific to this optimizer configuration.' : 'Not yet specified by a calculation record.' },
    { label: 'Exact classical reference', value: displaySpecified(experiment.method.classicalReferenceMethod), rationale: experiment.method.classicalReferenceMethod ? 'Computed in the same model and basis, restricted to the physical two-electron sector.' : 'Not yet specified by a calculation record.' },
    { label: 'Basis set', value: displaySpecified(experiment.method.basisSet), rationale: experiment.method.basisSet ? 'The VQE and exact comparison use the same stated model chemistry.' : 'Not yet specified by a calculation record.' },
  ]

  const calculationBoundary = isLoadingVerifiedArtifact
    ? 'Loading the checked-in, verified HeH+ result artifact. No quantum calculation is run by this page.'
    : experiment.calculationStatus === 'unavailable' || experiment.calculationStatus === 'not_started'
    ? 'No verified HeH+ VQE experiment is connected. The current page is a backend-ready empty state: it shows molecular facts and a geometry diagram, but no molecular energy or algorithm metadata is invented.'
    : 'This page displays a verified, saved local ideal-state quantum simulation. It is not IBM physical hardware execution, does not model device noise, and is separate from peptide-blend QAOA.'

  return (
    <div className="space-y-6">
      <SectionHeading
        action={isLoadingVerifiedArtifact ? <StatusPill tone="slate">Loading verified artifact</StatusPill> : <div className="flex flex-wrap justify-end gap-2"><StatusPill tone={statusTone(experiment.calculationStatus)}>{statusLabel(experiment.calculationStatus)}</StatusPill>{experiment.method.executionContext && <StatusPill tone="slate">Local ideal-state simulation</StatusPill>}</div>}
        description="A separate VQE electronic-structure study of the helium hydride ion. It does not share a Hamiltonian, objective, or interpretation with peptide-blend QAOA optimization."
        eyebrow="Quantum chemistry workspace"
        title="Quantum Chemistry — HeH+"
      />

      <HardwareExecutionControl execution={hardware} />
      <div className="space-y-2"><Button disabled={!hardware.enabled || hardware.busy} onClick={() => { setHardwareError(''); void hardware.run('heh', { bond_distance_angstrom: bondDistance, maxiter: 60 }).catch((reason: unknown) => setHardwareError(reason instanceof Error ? reason.message : 'HeH+ hardware run failed.')) }}>Run selected geometry on IBM QPU</Button><p className="text-xs text-slate-600">The checkbox enables a new hardware energy measurement at the selected bond distance, using locally optimized VQE parameters. Saved local scan charts below remain local simulation data; they are not relabeled as hardware.</p>{hardwareError && <p role="alert" className="text-sm text-red-800">{hardwareError}</p>}</div>

      <Panel className="border-[#D7E7E9] bg-[#F8FAFC] p-4" role="note">
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" aria-hidden="true" />
          <div className="text-sm leading-6 text-[#49636D]">
            <p className="font-semibold text-[#394957]">Calculation boundary</p>
            <p className="mt-1">{calculationBoundary}</p>
          </div>
        </div>
      </Panel>

      {artifactError && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-900" role="alert"><p className="font-semibold">Verified HeH+ artifact unavailable</p><p className="mt-1">{artifactError}</p></div>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5" aria-label="Molecular overview">
        <MetricCard detail="Helium hydride ion" label="Molecule" value="HeH+" />
        <MetricCard detail="Molecular charge" label="Charge" value="+1" />
        <MetricCard detail="For the stated molecular charge" label="Electron count" value="2" />
        <MetricCard detail={selectedEnergyPoint ? 'A calculated scan point is selected' : 'Geometry selector only; no energy calculated'} label="Selected He–H separation" value={`${bondDistance.toFixed(2)} Å`} />
        <MetricCard detail={experiment.method.executionContext ? 'Qiskit StatevectorEstimator; no hardware noise model' : 'Execution context unavailable'} label="Execution" value={experiment.method.executionContext ? 'Local ideal-state simulation' : 'Not yet specified'} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <Panel className="p-5" aria-labelledby="geometry-heading">
          <div className="flex items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-blue-50 text-blue-700"><Orbit className="h-[18px] w-[18px]" aria-hidden="true" /></span>
            <div>
              <p className="research-eyebrow">Molecular overview</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="geometry-heading">Explore nuclear separation</h2>
              <p className="mt-1 text-sm leading-6 text-[#657B85]">Select a sampled He–H distance to inspect its geometry and any attached calculated record. This diagram itself is not an electronic-structure calculation.</p>
            </div>
          </div>

          <div className="mt-6">
            <label className="research-label" htmlFor="heh-bond-distance">{calculatedDistances.length > 0 ? 'Calculated He–H bond distance' : 'He–H bond distance'}</label>
            <div className="mt-2 flex items-center gap-3">
              <input
                className="h-1.5 min-w-0 flex-1 cursor-pointer appearance-none rounded-full bg-[#D8E6E8] accent-[#087E78]"
                id="heh-bond-distance"
                max={Math.max(0, bondDistanceOptions.length - 1)}
                min="0"
                onChange={(event) => setBondDistance(bondDistanceOptions[Number(event.target.value)] ?? bondDistance)}
                step="1"
                type="range"
                value={selectedDistanceIndex}
              />
              <output className="w-20 rounded-md border border-[#D9E0E7] bg-white px-2 py-1.5 text-right font-mono text-sm text-[#394957]}" htmlFor="heh-bond-distance">
                {bondDistance.toFixed(2)} Å
              </output>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" aria-label={calculatedDistances.length > 0 ? 'Calculated bond distances' : 'Common bond distances'}>
              {bondDistanceOptions.map((distance) => (
                <button
                  className={`rounded-md border px-2 py-1 text-xs font-semibold transition-colors ${Math.abs(distance - bondDistance) < 0.001 ? 'border-blue-700 bg-blue-700 text-white' : 'border-[#D9E0E7] bg-white text-[#65717D] hover:border-blue-600 hover:bg-blue-50'}`}
                  key={distance}
                  onClick={() => setBondDistance(distance)}
                  type="button"
                >
                  {distance.toFixed(2)} Å
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6 rounded-lg border border-[#D9E0E7] bg-white p-4">
            <dl className="grid gap-4 text-sm sm:grid-cols-2">
              <div><dt className="text-xs font-medium text-[#6B818B]">Energy convention</dt><dd className="mt-1 font-semibold text-[#394957]">{displaySpecified(experiment.energyConvention)}</dd></div>
              <div><dt className="text-xs font-medium text-[#6B818B]">Nuclear-repulsion treatment</dt><dd className="mt-1 font-semibold text-[#394957]">{displaySpecified(experiment.nuclearRepulsionTreatment)}</dd></div>
              <div><dt className="text-xs font-medium text-[#6B818B]">Calculation provenance</dt><dd className="mt-1 font-semibold text-[#394957]">{experiment.provenance.label}</dd></div>
            </dl>
          </div>
        </Panel>

        <Panel className="p-5" aria-labelledby="diagram-heading">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="research-eyebrow">Bond-distance diagram</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="diagram-heading">HeH+ nuclear geometry</h2>
            </div>
            <StatusPill tone="slate">Geometry only</StatusPill>
          </div>
          <div className="mt-4"><HeHStructureDiagram bondDistanceAngstrom={bondDistance} /></div>
          <p className="mt-4 text-xs leading-5 text-[#6B818B]">Helium is placed at the origin and hydrogen along the internuclear axis for visualization. The displayed separation is a coordinate choice, not a predicted equilibrium geometry.</p>
        </Panel>
      </section>

      <Panel className="p-5" aria-labelledby="pes-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="research-eyebrow">Potential energy surface</p>
            <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="pes-heading">VQE and exact classical total-energy curve</h2>
            <p className="mt-1 text-sm leading-6 text-[#657B85]">All ten sampled points use HeH+, charge +1, two electrons, STO-3G, and total molecular energy with nuclear repulsion included.</p>
          </div>
          {lowestSampledVqePoint ? <StatusPill tone="blue">Lowest sampled VQE: {lowestSampledVqePoint.bondDistanceAngstrom.toFixed(3)} Å</StatusPill> : <StatusPill tone="slate">No curve data</StatusPill>}
        </div>
        <div className="mt-5"><PotentialEnergySurfaceChart energyConvention={experiment.energyConvention} points={experiment.energyPoints} /></div>
        <ChartContextNote>The line connects only the ten sampled geometries. The lowest sampled VQE point is not claimed to be the exact equilibrium geometry.</ChartContextNote>
      </Panel>

      <Panel className="p-5" aria-labelledby="error-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="research-eyebrow">Comparison diagnostic</p>
            <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="error-heading">VQE energy error by geometry</h2>
            <p className="mt-1 text-sm leading-6 text-[#657B85]">Error is shown only when the record includes both a VQE value and a scientifically comparable classical reference.</p>
          </div>
          <StatusPill tone={experiment.energyPoints.some((point) => point.absoluteErrorHartree !== null) ? 'blue' : 'slate'}>
            {experiment.energyPoints.some((point) => point.absoluteErrorHartree !== null) ? 'Error data available' : 'No error data'}
          </StatusPill>
        </div>
        <div className="mt-5"><EnergyErrorChart points={experiment.energyPoints} /></div>
        <ChartContextNote>Absolute error and any VQE uncertainty are reported in Hartrees. They do not establish accuracy without the shared method, basis, and energy-convention metadata.</ChartContextNote>
      </Panel>

      <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel className="p-5" aria-labelledby="algorithm-heading">
          <div className="flex items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-[#EEF6F5] text-blue-700"><CircuitBoard className="h-[18px] w-[18px]" aria-hidden="true" /></span>
            <div>
              <p className="research-eyebrow">Quantum algorithm explorer</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="algorithm-heading">Method configuration</h2>
              <p className="mt-1 text-sm leading-6 text-[#657B85]">Verified method metadata accompanies the saved result artifact. The circuit image is from the 1.000 Å calculation.</p>
            </div>
          </div>
          <dl className="mt-5 divide-y divide-[#E6EFF1] text-sm">
            <MethodRow label="Ansatz" value={displaySpecified(experiment.method.ansatz)} />
            <MethodRow label="Fermion-to-qubit mapping" value={displaySpecified(experiment.method.fermionToQubitMapping)} />
            <MethodRow label="Classical optimizer" value={displaySpecified(experiment.method.classicalOptimizer)} />
            <MethodRow label="Estimator" value={displaySpecified(experiment.method.estimator)} />
            <MethodRow label="Execution context" value={displaySpecified(experiment.method.executionContext)} />
            <MethodRow label="Exact classical reference" value={displaySpecified(experiment.method.classicalReferenceMethod)} />
            <MethodRow label="Basis set" value={displaySpecified(experiment.method.basisSet)} />
            <MethodRow label="Qubits" value={displaySpecified(experiment.method.qubitCount)} />
            <MethodRow label="Variational parameters" value={displaySpecified(experiment.method.variationalParameterCount)} />
            <MethodRow label="Decomposed circuit depth" value={displaySpecified(experiment.method.circuitDepth)} />
            <MethodRow label="VQE objective evaluations (1.000 Å)" value={displaySpecified(experiment.method.optimizerIterations)} />
          </dl>
          {experiment.circuitMetadata?.imageUrl ? (
            <figure className="mt-5 overflow-hidden rounded-lg border border-[#D9E0E7] bg-[#F8FAFC] p-3">
              <img alt={experiment.circuitMetadata.imageAlt ?? 'Verified HeH+ VQE circuit'} className="h-auto w-full rounded border border-[#E5EEF0] bg-white" loading="lazy" src={experiment.circuitMetadata.imageUrl} />
              <figcaption className="mt-3 text-xs leading-5 text-[#657B85]">{experiment.circuitMetadata.imageCaption ?? experiment.circuitMetadata.provenance.detail}</figcaption>
            </figure>
          ) : (
            <div className="mt-5 rounded-md border border-[#D9E0E7] bg-[#F8FAFC] p-3 text-xs leading-5 text-[#657B85]">No approved circuit visualization was supplied with this experiment record.</div>
          )}
        </Panel>

        <Panel className="p-5" aria-labelledby="convergence-heading">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="research-eyebrow">VQE convergence</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="convergence-heading">Selected geometry: {bondDistance.toFixed(2)} Å</h2>
              <p className="mt-1 text-sm leading-6 text-[#657B85]">A completed run can attach a convergence history to this bond distance.</p>
            </div>
            <StatusPill tone={selectedConvergence.length > 0 ? 'blue' : 'slate'}>{selectedConvergence.length > 0 ? 'History available' : 'No history'}</StatusPill>
          </div>
          <div className="mt-5"><VqeConvergenceChart energyConvention={experiment.energyConvention} points={selectedConvergence} /></div>
          <ChartContextNote>The supplied 1.000 Å convergence trace is converted to total molecular energy by adding the recorded nuclear repulsion. Other scan points do not imply omitted convergence histories.</ChartContextNote>
        </Panel>
      </section>

      <Panel className="p-5" aria-labelledby="energy-table-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="research-eyebrow">Molecular energy comparison</p>
            <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="energy-table-heading">Calculation records</h2>
            <p className="mt-1 text-sm leading-6 text-[#657B85]">Verified total molecular energies in Hartrees, with each VQE point compared to the matched exact classical reference.</p>
          </div>
          <StatusPill tone={experiment.energyPoints.length > 0 ? 'blue' : 'slate'}>{experiment.energyPoints.length > 0 ? 'Verified saved artifact' : 'No calculation artifact'}</StatusPill>
        </div>
        {experiment.energyPoints.length === 0 ? (
          <div className="mt-5"><EmptyState detail="No completed HeH+ calculation has supplied energy points. The table will retain units and provenance once results are available." title="No energy-comparison records" /></div>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="research-table min-w-[76rem]">
              <thead><tr><th>Bond distance (Å)</th><th>VQE total energy (Ha)</th><th>VQE uncertainty (Ha)</th><th>Exact classical total (Ha)</th><th>Absolute error (Ha)</th><th>Relative error</th><th>Notes</th><th>Provenance</th></tr></thead>
              <tbody>
                {experiment.energyPoints.map((point) => (
                  <tr key={point.bondDistanceAngstrom}>
                    <td className="font-mono text-[#394957]">{point.bondDistanceAngstrom.toFixed(3)}</td>
                    <td>{formatEnergy(point.vqeEnergyHartree)}</td>
                    <td>{formatEnergy(point.vqeEnergyUncertaintyHartree)}</td>
                    <td>{formatEnergy(point.referenceEnergyHartree)}</td>
                    <td>{formatEnergy(point.absoluteErrorHartree)}</td>
                    <td>{point.relativeError === null ? 'Unavailable' : point.relativeError.toExponential(3)}</td>
                    <td className="max-w-56 whitespace-normal text-xs text-[#657B85]">{point.notes ?? '—'}</td>
                    <td><span className="text-xs text-[#657B85]">{point.provenance.label}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Panel className="p-5" aria-labelledby="methodology-heading">
          <div className="flex items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-[#F1F6F7] text-[#45636E]"><Braces className="h-[18px] w-[18px]" aria-hidden="true" /></span>
            <div>
              <p className="research-eyebrow">Methodology and justification</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="methodology-heading">Verified calculation method</h2>
            </div>
          </div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {methodology.map((item) => (
              <article className="rounded-lg border border-[#E1EBEE] bg-[#FCFEFE] p-4" key={item.label}>
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#6B818B]">{item.label}</p>
                <p className="mt-2 text-sm font-semibold text-[#394957]">{item.value}</p>
                <p className="mt-2 text-xs leading-5 text-[#718791]">{item.rationale}</p>
              </article>
            ))}
          </div>
          <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
            A classical reference is scientifically comparable only within the same molecular model and basis. The energy convention must explicitly state whether nuclear repulsion is included.
          </div>
        </Panel>

        <Panel className="p-5" aria-labelledby="limits-heading">
          <div className="flex items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-[#F5F8F9] text-[#52717B]"><FlaskConical className="h-[18px] w-[18px]" aria-hidden="true" /></span>
            <div>
              <p className="research-eyebrow">Scientific boundaries</p>
              <h2 className="mt-1 text-lg font-semibold text-[#28323C]" id="limits-heading">Interpret with calculation context</h2>
            </div>
          </div>
          <ul className="mt-5 space-y-3 text-sm leading-6 text-[#5E747F]">
            <li>VQE is an electronic-structure workflow; it is not the QAOA peptide-selection model.</li>
            <li>The diagram encodes only an internuclear separation and cannot establish an equilibrium geometry.</li>
            <li>The 0.900 Å point is the lowest sampled VQE total energy in this ten-point scan; it is not presented as an exact equilibrium distance.</li>
            <li>These calculations use an ideal-state local simulator, not IBM physical hardware, and do not model device noise.</li>
            <li>STO-3G is a small basis. The VQE and exact comparison are meaningful only within the stated molecular model and energy convention.</li>
          </ul>
          <div className="mt-6 border-t border-[#E5EEF0] pt-4 text-xs leading-5 text-[#718791]">
            <p>Experiment ID: {experiment.experimentId} · Provenance: {experiment.provenance.detail}</p>
            {experiment.artifactProvenance && <p className="mt-2 break-all">Source SHA-256: {experiment.artifactProvenance.calculationSource.sha256} · Qiskit {experiment.artifactProvenance.packageVersions.qiskit} · Qiskit Nature {experiment.artifactProvenance.packageVersions['qiskit-nature']}</p>}
          </div>
        </Panel>
      </section>
    </div>
  )
}

function MethodRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-5 py-3">
      <dt className="text-[#6B818B]">{label}</dt>
      <dd className="max-w-[60%] text-right font-medium text-[#394957]">{value}</dd>
    </div>
  )
}
