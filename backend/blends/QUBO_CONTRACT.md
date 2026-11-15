# Validated whole-peptide QUBO and existing QAOA integration

## Scope and implementation audit

The working whole-peptide QAOA implementation is
`backend/blends/quantum.py`. It accepts Ising fields, upper-triangle couplings,
alternating gamma/beta parameters, and an energy scale. Its circuit and
statevector simulator are reused without edits. The existing COBYLA fit and
seeded multinomial sampling in `solver.py` are also retained.

`backend/quantum.py` and `backend/optimizer.py` implement a different, at-most-five
qubit bond-angle experiment with a full energy table. They are not the 8-peptide
selection backend and have not been changed or extended to represent it.

No compatible standalone `backend/peptide_analysis/` interface is present in
this checkout; `research/scoring_model.md` is empty. The existing supported
chemistry interface is `blends.scoring.descriptors`: Biopython charge at pH,
Kyte-Doolittle GRAVY, and average mass for a linear free-termini chain. The
catalog adapter supplies real local reference sequences and source URLs.
This validates a documented research proxy, not experimental peptide effects.

## Score and mathematical convention

For individual peptide i, with estimated charge q_i at the requested pH and
dimensionless Kyte-Doolittle GRAVY h_i:

```
C_i = 1 / (1 + abs(q_i - target_charge) / 2)
H_i = 1 / (1 + abs(h_i - target_hydropathy))
S_i = (charge_weight*C_i + hydropathy_weight*H_i)
      / (charge_weight + hydropathy_weight)
```

The tolerances (2 elementary-charge units and 1 GRAVY unit) are declared
research design choices, not fitted biological constants. Scores are in [0,1].
At least one property weight must be positive. These fixed transforms do not
depend on the contents or order of the candidate pool.

P_ij defaults to Jaccard overlap of sets of adjacent residue pairs. For example,
`GAGA` has {GA, AG}. This is a sequence redundancy penalty, not an interaction
energy or a measure of physical compatibility. Optional explicit pairs must
cover all unordered pairs, use known IDs, lie in [0,1], and document their
method. Missing, reversed duplicate, self, and unsupported pair terms fail.
A pair labeled `sequence_bigram_jaccard` is checked against the sequences.

With w = `diversity_weight` (the user's pair-weight gamma, distinct from QAOA's
phase angle gamma), k = selection count, and x_i in {0,1}, minimize:

```
raw(x) = -sum_i S_i*x_i + w*sum_(i<j) P_ij*x_i*x_j
E(x) = raw(x) + lambda*(sum_i x_i-k)^2
lambda = sum_i S_i + w*sum_(i<j) P_ij + 1

c = lambda*k^2
a_i = -S_i + lambda*(1-2*k)
b_ij = w*P_ij + 2*lambda                  (i<j)
Q_upper[i,i] = a_i
Q_upper[i,j] = b_ij                       (i<j)
Q_upper[i,j] = 0                          (i>j)
E(x) = c + x.T @ Q_upper @ x
```

The matrix is **upper triangular, not symmetrized**. Count each pair once.
For a symmetric convention the off-diagonal entries would instead be b_ij/2.
The complete numeric 8x8 matrix for the saved experiment is in
`experiments/peptide_blend_verified/result.json`, field
`qubo.matrix_upper_triangle`; the constant c is retained separately.

Since raw(x) lies between -sum(S) and w*sum(P), an infeasible cardinality costs
at least lambda, greater than the entire possible raw-objective range. Therefore
every infeasible penalized state is worse than every feasible state. This is
checked exhaustively, but does not force finite-depth QAOA shots to be feasible.

Substitute x_i=(1-Z_i)/2:

```
J_ij = b_ij/4
h_i = -a_i/2 - sum_(j!=i) b_min(i,j),max(i,j)/4
offset = c + sum(a_i)/2 + sum_(i<j) b_ij/4
H = offset*I + sum_i h_i*Z_i + sum_(i<j) J_ij*Z_i*Z_j
```

The existing circuit applies RZ(2*gamma*h_i/s), RZZ(2*gamma*J_ij/s), then
RX(2*beta). Here s=max(abs(h), abs(J), 1e-12). The omitted offset contributes
only a global phase. COBYLA minimizes the expectation of
`(E-min(E))/s`, a positive affine transform preserving the optimum. Reported
blend scores and gaps always use **raw(x)**, the same objective as the exact
feasible reference, not the shifted training cost.

Candidate i maps to qubit i; the **rightmost** bit is candidate 0. In an
eight-candidate pool, `00000111` selects input IDs 0,1,2.

## Input and response handoff

Existing version-1 catalog routes and field names are preserved. No frontend,
`backend/api.py`, peptide-library code, or VQE code was edited. Existing
`POST /api/v1/blends/optimize` still takes candidate IDs and calculates its
descriptors on the backend. Its additional response fields are described below.

For a future chemistry teammate's descriptor integration, validate JSON with
`DescriptorExperiment.model_validate(...)`, then call
`optimize_descriptor_input(experiment)` from `solver.py`. This is a backend
Python contract, **not a newly published HTTP endpoint**. Coordinate a route
and frontend adapter with their owners before exposing it. Structure:

```json
{
  "candidates": [
    {
      "id": "original-source-id",
      "name": "Original reference name",
      "sequence": "GAGA",
      "chemical_form": "linear_free_termini",
      "modifications": [],
      "source": "Original source database",
      "source_url": "https://source.example/record",
      "descriptors": {
        "charge": -0.25,
        "hydropathy": 0.7,
        "ph": 7.4,
        "method": "Descriptor calculation and version supplied by chemistry owner",
        "provenance": "calculated"
      }
    }
  ],
  "goals": {
    "ph": 7.4,
    "target_charge": 0,
    "target_hydropathy": 0,
    "charge_weight": 0.5,
    "hydropathy_weight": 0.5,
    "diversity_weight": 0.3
  },
  "selection_count": 3,
  "pair_terms": null,
  "layers": 1,
  "max_iterations": 60,
  "shots": 2048,
  "seed": 42
}
```

This compact schema illustration has **one illustrative candidate and placeholder
values; it is not an executable eight-candidate experiment or scientific data**.
Use the eight real records in the saved `input.json` for execution/replay.
For standard selections use 8 candidates, k=3; the general contract supports
2-8 candidates and 1<=k<n. Unknown fields, missing descriptors, nonfinite numbers,
unsupported residues/modifications, duplicate IDs, and pH mismatches fail validation.
`chemical_form` is a required **model assumption supplied by the caller**, not
independent verification of the reference's form. Optional `mass_da` must be
positive and is not scored. Hydropathy must use the Kyte-Doolittle GRAVY scale;
the caller's descriptor method/provenance is preserved and not independently
validated. `published` provenance is allowed but is not automatically trusted.

An explicit `pair_terms` entry has `first_id`, `second_id`, `penalty`, and
`method`, either `sequence_bigram_jaccard` or `researcher_supplied_redundancy`.
An eight-candidate explicit matrix must have all 28 pairs. `null` computes the
documented Jaccard proxy instead. An empty array does not silently mean zero.

Response contract (additive to the existing `contract_version: "1.0"`):

| Field | Meaning |
| --- | --- |
| experiment_id, created_at | UUID and UTC timestamp of this calculation |
| candidate_ids, candidates | Original IDs in qubit order, sequences, sources, descriptors, normalized component scores |
| goals | Validated targets, weights, k as blend_size, seed, layers, shots, evaluation budget |
| selected_blend | Best feasible **observed** sample: bitstring, IDs, raw objective and score/pair components; null if none |
| classical_reference | Exact feasible optimum under the identical objective |
| classical_feasible_selections | Every feasible subset, bitstring, IDs and raw objective (56 for 8 choose 3) |
| qubo | Upper-triangle full matrix, split coefficients, constant, pair values/method, lambda and convention |
| ising | Offset, fields and upper-triangle couplings |
| circuit_metadata, circuit_depth, parameters | Existing implementation, gates, qubits, scale, layers, fitted parameters and conventions |
| history, evaluations, converged, optimizer_message | Actual COBYLA evaluations and termination, not an invented trend |
| probabilities | Full ideal statevector distribution; not empirical frequencies |
| counts | Seeded simulated shot counts, not hardware measurements |
| sampling | Feasible/infeasible counts and shot totals separately; observed_frequencies=count/shots |
| benchmark | Feasibility rates, optimum probability, uniform baselines, sampled_objective_gap=sampled raw-exact raw |
| validation | Every-state direct/QUBO/matrix/Ising checks, numerical errors and cardinality separation |
| provenance, execution_backend | simulated, qiskit_statevector |
| status | completed or no_feasible_sample; never a substituted classical result |
| scoring_method, limitations | Normalization, method versions and scientific limits |
| circuit_qasm | Numerically fitted OpenQASM 2 circuit, RZZ expanded to CX/RZ/CX |

## Actual execution and reproduction

The saved real-catalog experiment selected:

| ID | Name |
| --- | --- |
| dbaasp:11246 | Stylisin 2 |
| dbaasp:15524 | JEV Ep (401-428) |
| dbaasp:19458 | SARS-CoV S (668-679), SP-10 |

Both the best observed QAOA sample and exact reference score were
**-2.8235836244068135**, with raw-objective gap **0**. The sampled bitstring
was **00000111**, and **711 / 2048** simulated shots were feasible. The actual
ideal probability of an optimal selection was **0.006409995154894129**, not 100%.
COBYLA used all **60** evaluations and **did not converge** within that budget.
Qiskit executed the 8-qubit H/RZ/RZZ/RX circuit. Maximum all-state QUBO/Ising
discrepancy was **1.4210854715202004e-13**. The saved native PNG and expanded
QASM describe the fitted circuit, not an illustrative diagram.

The analysis assumes a linear free-termini model; source modifications may be
incompletely annotated. These source records and model descriptors are not
evidence of biological compatibility or an experimentally validated blend.
Shortlisting is classical and may exclude a better blend outside this pool.

From the repository root with the environment active:

```powershell
$env:MPLBACKEND = 'Agg'
python -m pytest backend -q
python -m backend.blends.experiment --output experiments/peptide_blend_new_run
```

To reproduce the saved run independent of future catalog imports, replay its
captured descriptor values and candidate order:

```powershell
python -m backend.blends.experiment --input experiments/peptide_blend_verified/input.json --output experiments/peptide_blend_replay
```

An existing output directory with experiment files is never overwritten. UUID,
timestamp, elapsed time and provenance metadata may differ on replay; identical
software, numeric inputs, seed and evaluation budget reproduce the mathematical
objective, fitted circuit distribution and sampled counts. Other platforms or
versions may change floating-point optimizer trajectories. Diagram export uses
Matplotlib and pylatexenc, already used by the existing Qiskit diagram workflow;
if absent install `python -m pip install matplotlib pylatexenc`.

Files added: `qubo.py`, `validation.py`, `experiment.py`, `test_qubo_contract.py`,
this contract, and `experiments/peptide_blend_verified/` artifacts. Files modified:
`solver.py`, `scoring.py`, and `README.md`, all within `backend/blends/`.
No commits or branch changes were made. Work on main was explicitly authorized.

Method references: [Biopython ProtParam](https://biopython.org/docs/latest/api/Bio.SeqUtils.ProtParam.html)
and [Biopython Bjellqvist charge model](https://biopython.org/docs/latest/api/Bio.SeqUtils.IsoelectricPoint.html).

## Verification results

The complete backend suite passed: **91 tests**. Coverage includes all-state
coefficient/matrix/Ising equivalence, no double counting, cardinality enforcement,
the analytical top-three fixture, invalid and missing scores/descriptors,
unsupported forms, pH mismatch, incomplete/duplicate pair terms, original-ID bit
ordering, exact feasible enumeration, actual QAOA simulation, circuit export,
and a deliberately forced suboptimal sample whose gap is correctly reported
as 1.5 rather than zero. A forced no-feasible-sample test confirms that the
classical reference is not substituted. The existing API tests still pass.

Independent replay of the saved real descriptor snapshot produced identical
fitted parameters and all simulated counts. Simulating the saved expanded QASM
reproduced all 256 ideal probabilities within absolute tolerance 1e-12. The
PNG was opened and visually checked. The only test warning is the pre-existing
Starlette/httpx TestClient deprecation. No hardware run or quantum advantage
has been claimed. Mathematical validation does not validate biological effects.
