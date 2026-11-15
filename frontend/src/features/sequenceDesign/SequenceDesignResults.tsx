import { useState } from 'react'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Button, MetricCard, Panel, StatusPill } from '../../components/ui'
import { downloadSequenceFile, sequenceDesign } from '../../services/sequenceDesign'
import type { SequenceResult } from '../../services/sequenceDesign'

export function SequenceDesignResults({ result, current }: { result: SequenceResult; current: boolean }) {
  const [drawing, setDrawing] = useState<{ sequence: string; svg: string; model: string } | null>(null)
  const [drawingError, setDrawingError] = useState<string | null>(null)
  const [drawingBusy, setDrawingBusy] = useState(false)
  const chosen = result.best_sampled
  const percent = (value: number) => `${(value * 100).toFixed(1)}%`
  async function draw(sequence: string) {
    setDrawingBusy(true); setDrawingError(null)
    try { setDrawing(await sequenceDesign.structure(sequence)) }
    catch (error) { setDrawingError(error instanceof Error ? error.message : 'Structure request failed.') }
    finally { setDrawingBusy(false) }
  }
  return <div className="space-y-5" aria-label="Sequence design results">
    <p className={`rounded-lg border p-3 text-sm ${current ? 'border-blue-200 bg-blue-50 text-blue-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`} role="status">{current ? 'These results match the current design inputs.' : 'Previous run snapshot: the design inputs have changed. Run again to evaluate them.'}</p>
    <Panel className="space-y-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">Quantum-proposed sequence</h2><StatusPill tone="blue">Actual Qiskit simulation</StatusPill></div>
      {chosen ? <>
        <p className="break-all rounded-lg bg-blue-50 p-4 font-mono text-2xl font-semibold tracking-wider text-blue-900">{chosen.sequence}</p>
        <p className="text-sm leading-6 text-[#65717D]">Best feasible observed sample: <code>{chosen.bitstring}</code>. {chosen.count} of {result.request.shots} simulated shots produced this sequence. {chosen.mutation_count !== null && `${chosen.mutation_count} changes from the template.`} Lower objective values are better.</p>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label={`Estimated charge at pH ${result.request.goals.ph}`} value={`${chosen.properties.charge.toFixed(3)} e`} detail={`Target ${result.request.goals.target_charge}; deviation ${chosen.charge_error_e.toFixed(3)} e`} />
          <MetricCard label="Hydropathy (GRAVY)" value={chosen.properties.hydropathy.toFixed(3)} detail={`Requested range ${result.request.goals.hydropathy_min} to ${result.request.goals.hydropathy_max}`} />
          <MetricCard label="Calculated mass" value={`${chosen.properties.mass_da.toFixed(2)} Da`} detail="Linear, unmodified, free termini" />
          <MetricCard label="Estimated isoelectric point" value={chosen.properties.isoelectric_point.toFixed(3)} detail="Descriptor only; not the target solution pH" />
        </div>
        <p className="text-sm text-[#65717D]">Objective {chosen.objective.toFixed(6)} = (charge {chosen.components.charge.toFixed(6)} + hydropathy {chosen.components.hydropathy.toFixed(6)} + repeat preference {chosen.components.adjacent_repeats.toFixed(6)}) / weight sum {chosen.component_weight_sum}. All encoded hard constraints satisfied; soft chemical targets may still have a nonzero deviation.</p>
        <Button variant="secondary" onClick={() => void draw(chosen.sequence)} disabled={drawingBusy}>{drawingBusy ? 'Generating connectivity…' : 'Inspect molecular connectivity'}</Button>
      </> : <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">No feasible sequence was observed in these shots. The exact reference below is shown separately; it has not been substituted as a quantum result.</p>}
      {drawingError && <p role="alert" className="text-sm text-red-800">{drawingError}</p>}
      {drawing && <div className="space-y-2"><p className="break-all font-mono text-sm">{drawing.sequence}</p><div className="overflow-x-auto rounded-lg border bg-white"><img className="min-w-[700px]" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(drawing.svg)}`} alt={`Calculated two-dimensional molecular connectivity for ${drawing.sequence}`} /></div><p className="text-xs text-[#65717D]">{drawing.model}</p><Button variant="ghost" onClick={() => downloadSequenceFile(drawing.svg, `peptide_${drawing.sequence}.svg`, 'image/svg+xml')}>Download structure SVG</Button></div>}
    </Panel>
    <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">Exact classical comparison</h2>
      <p className="break-all text-sm">Reference sequence: <code>{result.classical_reference.sequence}</code>. Exact objective: {result.classical_reference.objective.toFixed(6)}. There are {result.benchmark.optimal_sequences_count} tied optimal sequences in this restricted space.</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Sampled objective gap" value={result.benchmark.sampled_objective_gap?.toFixed(6) ?? 'Unavailable'} detail="Sampled raw objective minus exact raw optimum" />
        <MetricCard label="Probability of an optimum" value={percent(result.benchmark.optimum_probability)} detail={`Uniform baseline ${percent(result.benchmark.uniform_optimum_probability)}`} />
        <MetricCard label="Feasible simulated shots" value={`${result.benchmark.feasible_shots}/${result.request.shots}`} detail={`${result.benchmark.infeasible_shots} infeasible shots`} />
        <MetricCard label="Validated search space" value={`${result.benchmark.state_count} encoded states`} detail={`${result.benchmark.feasible_state_count} feasible; ${result.benchmark.qubits} qubits`} />
      </div>
      <p className="text-sm text-[#65717D]">Optimizer: {result.optimizer.converged ? 'convergence criterion reached' : 'convergence criterion not reached'}. {result.optimizer.message} A zero observed gap does not guarantee the optimum on another shot or establish quantum advantage.</p>
    </Panel>
    <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">Observed candidate sequences</h2>
      <div className="overflow-x-auto"><table className="research-table"><thead><tr><th>Sequence</th><th>Objective</th><th>Charge (e)</th><th>GRAVY</th><th>Changes</th><th>Shots</th></tr></thead><tbody>{result.candidate_sequences.map((candidate) => <tr key={candidate.bitstring}><td className="break-all font-mono">{candidate.sequence}</td><td>{candidate.objective.toFixed(6)}</td><td>{candidate.properties.charge.toFixed(3)}</td><td>{candidate.properties.hydropathy.toFixed(3)}</td><td>{candidate.mutation_count ?? 'New design'}</td><td>{candidate.count}</td></tr>)}</tbody></table></div>
      <p className="text-xs text-[#65717D]">Up to ten feasible sequences actually observed in the simulated shots. Unobserved exact solutions are not inserted here.</p>
    </Panel>
    <Panel className="space-y-4 p-5"><h2 className="text-lg font-semibold">Actual QAOA circuit and history</h2>
      <p className="text-sm">{result.benchmark.qubits} qubits · {result.request.layers} layers · {result.circuit.depth} circuit depth · {result.optimizer.evaluations} evaluations · {result.elapsed_seconds.toFixed(2)} s</p>
      <div className="h-56 min-w-0"><ResponsiveContainer width="100%" height="100%"><LineChart data={result.history}><XAxis dataKey="evaluation" /><YAxis width={60} /><Tooltip /><Line dataKey="expected_penalized_objective" stroke="#2563eb" dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
      <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => downloadSequenceFile(result.circuit.qasm, 'sequence_design.qasm')}>Download circuit for IBM Composer</Button><Button variant="secondary" onClick={() => downloadSequenceFile(JSON.stringify(result, null, 2), 'sequence_design_result.json', 'application/json')}>Download complete design result</Button></div>
      <details><summary className="cursor-pointer text-sm font-semibold">Inspect circuit and position encoding</summary><p className="my-2 text-xs">{result.methods.bit_order}</p>{result.encoding ? <div className="my-2 space-y-2 text-xs"><p>{result.encoding.valid_sequence_count} valid sequence codes; {result.encoding.invalid_code_count} unused codes receive a penalty. Feasible probabilities include losses to unused codes and hard-constraint violations.</p>{result.encoding.blocks.map((block) => <p key={block.position}>Position {block.position}: qubits {block.qubits.join(', ')} (least significant first). {block.choices.map((code, index) => `${index}=${code}`).join('; ')}. Unused codes: {block.unused_codes}.</p>)}</div> : <ul className="my-2 text-xs">{result.variables.map((variable) => <li key={variable.qubit}>q{variable.qubit}: position {variable.position}, 0 = {variable.choices[0]}, 1 = {variable.choices[1]}</li>)}</ul>}<pre className="max-h-96 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-slate-100">{result.circuit.text}</pre></details>
      <details><summary className="cursor-pointer text-sm font-semibold">Inspect mathematical validation and scoring methods</summary><p className="my-2 text-sm">Representation: {result.cost.representation.replaceAll('_', ' ')}; polynomial degree {result.cost.degree}; constraint penalty {result.cost.penalty.toFixed(6)}. Maximum reconstruction error: {result.validation.cost_reconstruction_max_error.toExponential(2)} across {result.validation.checked_states} states.</p>{result.cost.qubo ? <pre className="max-h-64 overflow-auto text-xs">{JSON.stringify(result.cost.qubo, null, 2)}</pre> : <p className="text-sm">These constraints require higher-order terms. They are included exactly in a diagonal Hamiltonian; the result is not claimed to be a quadratic QUBO.</p>}<dl className="mt-3 space-y-2 text-xs">{Object.entries(result.methods).map(([key, value]) => <div key={key}><dt className="font-semibold">{key.replaceAll('_', ' ')}</dt><dd>{value}</dd></div>)}</dl><ul className="mt-4 list-disc space-y-1 pl-5 text-xs">{result.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>
    </Panel>
  </div>
}
