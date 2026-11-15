# Large sequence-design circuits: up to 50 real qubits

The default small-instance mode is preserved. Select **Bounded approximate MPS**
or **Prepare circuit only**, or click **Load 50-qubit example** in Sequence Design.
Use **Set first N positions editable** to choose any count up to the mode's limit;
individual position checkboxes still allow arbitrary fixed/variable locations.

## What a larger qubit count means

A 50-qubit circuit has a Hilbert space with 2^50 basis states. This is not a
promise that every sequence is searched and read out, that the problem is hard
for every classical solver, or that more qubits create a speed advantage.
Charge/GRAVY objectives have exploitable structure, and a classical optimizer can
perform very well. Qiskit Aer MPS is a **classical quantum-circuit simulation**.
Its execution time must never be called a measured QPU execution time.

A dense 50-qubit complex128 statevector alone would occupy 16*2^50 bytes
(16 PiB, about 18 PB), excluding overhead. This path never constructs one.
There is no full sequence table, full probability vector, all-state polynomial
transform, or exhaustive search. The old exact eight-qubit path is unchanged.

## Analytical QUBO

At a fixed pH, the supported Biopython charge model is affine in independent
binary residue choices, including the separately position-dependent terminal
contributions. GRAVY is also affine:

```
q(x) = q0 + sum(dq_i*x_i)
h(x) = h0 + sum(dh_i*x_i)
```

The baseline and single-position changes take O(n) chemistry calls. Squared
deviation from a target gives an exact quadratic polynomial: for
`weight*(b+sum(d_i*x_i))^2`, add `weight*b^2` to the constant,
`weight*(2*b*d_i+d_i^2)` to Q_ii, and `2*weight*d_i*d_j` to Q_ij (i<j).
Adjacent-repeat terms are expanded directly from each two-position truth table.
The upper-triangular matrix takes O(n²) memory. Substitution x=(1-Z)/2 uses the
existing Ising mapping and RZ/RZZ/RX QAOA circuit builder. Gate coefficients use
a positive analytic scale `sum(abs(linear))+sum(abs(pair))`; no exponential
energy table is used even for parameter normalization.

The same raw objective and chemical scoring function are retained. We do not
silently replace a hydropathy range with a midpoint target. A range is accepted
only when the entire attainable hydropathy interval lies inside it or entirely
on one side; otherwise use a point target, disable that weight, or use small
exact mode. This is a restriction of large mode, not a chemistry equivalence.

Required residues must already occur at fixed positions, and any mutation
budget must be at least the maximum changes possible in the encoded domains.
These checks guarantee that every encoded assignment is feasible. Binding
inequalities/higher-order constraints are rejected with an explanation. The
small exact mode continues to implement them without approximation.

Coefficient construction is checked against direct chemistry and Ising values
on both endpoints and 32 seeded assignments. Small-instance tests also verify
all assignments. The large-mode validation is explicitly **not exhaustive**.

## Bounded local simulation

Optional dependency:

```powershell
python -m pip install -r backend/sequence_design/requirements-large.txt
```

The implementation uses Aer `matrix_product_state`, not `statevector`:

- Maximum bond dimension: user-selectable 8,16,32 (API accepts 2-32).
- Truncation threshold: 1e-10. Both the cap and threshold may discard state data.
- Explicit `mps_apply_measure` sampling, which avoids an exponential probability
  vector. No `save_statevector` or full probability instruction is used.
- One QAOA layer above 20 qubits; 10-30 COBYLA objective evaluations.
- 64-256 training shots/evaluation and 128-8192 final shots.
- Training uses the configured seed; independent final sampling uses seed+1.
- A 256 MB simulator memory setting, two CPU threads, and gate fusion disabled.

There is no certified end-to-end approximation bound. Small-state tests compare
the sampled distribution with exact statevector probabilities. Truncation and
shot noise can change optimization outcomes; more qubits can make both accuracy
and runtime worse. Maximum supported qubits here is 50, matching the sequence
position limit; hardware feasibility depends on transpiled depth and device
connectivity, not just a QPU's advertised number of qubits.

The circuit-only option creates an **unoptimized** circuit at starting angles
gamma=1, beta=0.5 per layer. It returns zero shots, no candidate proposal and
`execution_backend=not_executed`. Downloaded QASM needs hardware authentication,
transpilation and explicit submission before any IBM QPU execution occurs.

## Honest comparisons

The classical baseline uses six starting assignments and bounded binary
coordinate descent. The app reports its actual raw score and objective budget.
This is a heuristic, not a proven exact answer. The output leaves exact optimum,
ideal optimum probability and optimality gap unavailable. A sampled-minus-
heuristic score difference is labeled accordingly, including when QAOA is worse.

Measured wall-clock sections separately cover analytical formulation, QAOA
simulation/fitting/final sampling, classical heuristic search, and circuit
export. Both algorithms run on a classical CPU with different evaluation
budgets and potentially different solution quality. These timings are useful
profiling data, **not evidence of a hardware quantum speedup**. No extrapolated
brute-force runtime is displayed as though it were measured.

## API and reproduction

The same base sequence request shape is used, with `max_iterations` default 10
(maximum 30), plus `mps_bond_dimension` (16), `training_shots` (64), and starting
`initial_gamma` (1), `initial_beta` (0.5).

- POST `/api/v1/sequence-design/large/preview`: analytical validation, no circuit execution.
- POST `/api/v1/sequence-design/large/optimize`: actual bounded MPS QAOA simulation.
- POST `/api/v1/sequence-design/large/export`: prepare only; no execution.

Responses use contract 1.1, with explicit `prepared` or `simulated_approximate`
provenance, counts/frequencies, native QASM/text metadata, analytic QUBO/Ising
coefficients, sample-based history, classical heuristic, timings and limitations.
The original contract 1.0 exact routes and saved results remain supported.

```powershell
python -m pytest backend/sequence_design -q
python -m backend.sequence_design.experiment --large --output experiments/sequence_design_50_qubit
python -m backend.sequence_design.experiment --large --prepare-only --input experiments/sequence_design_50_qubit/input.json --output experiments/sequence_design_50_prepared
```

New output directories are required so prior experiments are not overwritten.
Large runs export JSON/QASM/text, avoiding a giant 50-qubit Matplotlib PNG.
The text file is explicitly a short circuit summary; the QASM retains every
gate and angle. Full folded text drawings can also grow to several megabytes.

Validation includes actual 50-qubit MPS execution, all-state small-instance
chemical/QUBO/Ising checks, MPS-vs-statevector sampling checks on small circuits,
constraint rejection, correct 50-bit decoding, circuit-only/no-execution behavior,
and the preserved exact APIs. The complete backend suite passed 143 tests, with
one optional VQE module skipped. Browser checks cover 50-qubit preview/run,
counts, timing displays, saved results, circuit export, qubit-count selection,
preparation-only execution and the original exact mode.

Primary reference: [Qiskit Aer MPS options and measurement algorithms](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.AerSimulator.html).
