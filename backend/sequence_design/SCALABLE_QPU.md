# Scalable sequence QAOA and explicit IBM hardware jobs

## Quick checkbox workflow across the app

Active quantum workflows now have **Use IBM quantum computer (QPU)**:

- Sequence Design: binary exact, multi-choice, and large binary modes.
- Scalable QPU Lab: the specified bounded angle sweep.
- Blend Optimization: whole-peptide subset QAOA.
- Molecular Analysis / Structure Stats: the short-peptide torsion-grid QAOA.
- HeH+ Quantum Chemistry: an energy estimate at the selected geometry.

Configure the backend IBM account once using the instructions below. Check the
box, enter a backend name once, then press that page's **Run** button. Backend
name, hardware shots and execution cap are reused across pages. Checking the
box itself never connects or submits. Clicking Run explicitly consumes runtime;
the quick route performs preparation and submission without the advanced
prepare/confirm steps. The earlier advanced workflow remains available in QPU Lab.

Small sequence, blend and torsion solvers fit parameters using their existing
local ideal simulator, then send the fitted circuit for hardware measurements.
This is a hardware verification of local fitting, **not all-hardware adaptive
QAOA training**. Large binary mode measures user-specified initial angles;
scalable mode measures the displayed angle sets. Chemistry, geometry generation,
classical baselines and parameter optimization remain CPU work.

HeH+ runs the existing local VQE to fit the UCCSD state, builds the same
Hamiltonian and measures its electronic energy with Runtime **EstimatorV2**.
The observable is transformed using the transpiled circuit's physical layout.
Total energy includes the same nuclear repulsion; reported uncertainty is
retained. This requires the optional Qiskit Nature/Algorithms/PySCF dependencies
from `backend/quantum_chemistry/requirements.txt`; PySCF may require Linux/WSL.
It measures one selected geometry, not an adaptive hardware VQE/PES scan. Saved
local scan charts are left unchanged and retain their simulation labels.

Sampler workflows report hardware counts, feasible samples, objective values
and actual job usage. Ideal probabilities are not relabeled as hardware
probabilities. If every sample is infeasible, no classical answer is substituted.
Hardware shots apply per Sampler circuit; for Estimator they are the requested
shots per measurement basis, not a promise of total job shots or account usage.

Every quick run saves a recovery UUID before sending the request. Use
**Refresh / recover hardware run** on that page after interruption or restart.
Quick-run records live in ignored `.cache/pepperq-hardware/`. Retrying the same
UUID is idempotent, with an atomic per-ID claim to prevent duplicate submissions
across API workers. If the submission response is uncertain, inspect IBM
workloads before starting a *new* run; a fresh UUID deliberately means a new job.
Cancellation is explicit. No backend connection or hardware workload is started
when importing modules, loading a page, checking the checkbox or refreshing a
saved local chart. Status refresh retrieves only an existing job.

Comparison and Noise Study currently display fixtures and have no executable
quantum experiment. The checkbox does not turn those fixtures into calculations.
Ordinary Python functions, molecular drawings and database lookups remain local.

Quick-route API: `POST /api/v1/hardware/run` with `workflow`, `settings`,
`backend_name`, `shots`, `max_execution_seconds`, a UUID `request_id`, and
`use_qpu: true`. Status and cancellation use `/api/v1/hardware/jobs/{request_id}`
and `/api/v1/hardware/jobs/{request_id}/cancel`. Credentials are server-side only.

Estimator reference: [IBM Estimator inputs and outputs](https://quantum.cloud.ibm.com/docs/en/guides/estimator-input-output).

Open **Sequence Design → Open Scalable QPU Lab**, or visit
`http://localhost:5173/sequence-qpu` with the frontend and backend running.
All earlier sequence, blend and HeH+ pages remain available.

## What changed

- Up to ten editable sites, with 2–20 standard amino-acid options at each;
  fixed sites may extend the total template to 50 residues.
- Compact binary blocks need `ceil(log2(choices))` qubits per editable site.
  Ten sites with twenty choices use 50 qubits and represent 10.24 trillion
  valid sequences. Ten sites with four choices use 20 qubits and represent
  1,048,576 valid sequences. This count is metadata, not a generated table.
- The compiler transforms position-local tables of at most 32 values, plus
  adjacent-position tables of at most 1,024 values. Walsh coefficients give
  Pauli-Z products. Squaring the additive charge and hydropathy expressions
  uses algebraic Pauli multiplication (`Z_mask_a * Z_mask_b = Z_(a XOR b)`).
  No global `2^qubits` array, dense unitary or exhaustive candidate scan is
  used to construct the Hamiltonian.
- Parameterized cost gates are parity ladders of CX, RZ, CX; RX mixes amplitudes.
  Terms involving two sites may act on up to ten qubits. This is an exact
  higher-order diagonal Hamiltonian, not necessarily a QUBO.
- Invalid local codes use the site's baseline residue for descriptors and
  add a penalty for each invalid site. The penalty exceeds an analytic upper
  bound on every valid objective. Invalid codes are never proposed as peptides.

Charge and GRAVY retain the existing Biopython conventions, including terminal
contributions. Exact local-cost/Pauli checks and direct chemistry checks are
performed on deterministic/seeded assignments. Small tests exhaustively check
the mapping and compare circuit probabilities against direct diagonal evolution.
Random checks on a large instance are not an exhaustive proof.

## Accepted goals and constraints

The page uses a point target for hydropathy. The API also accepts ranges that
contain the whole attainable range, or for which the entire range is on one
side of a boundary. Ranges crossing cost branches are rejected.

Length, allowed options and fixed sites are encoded directly. Required residues
must already occur at fixed sites. Mutation budgets must be nonbinding. Other
requirements are rejected, never silently discarded. Use the earlier small
exact designer when you need its more general hard constraints.

No objective here predicts binding, folding, efficacy, peptide interactions or
clinical effects. The neighboring-repeat term remains an explicit researcher
preference. No new biological interaction model has been invented.

## Local experiment

Start with **10 positions × 4 choices**, preview, and run the bounded local
comparison. Local QAOA uses Aer MPS, a 256 MB memory setting, at most 16 bond
dimension, 32–128 training shots, 10–30 COBYLA evaluations, and 128–1,024 final
shots. It is approximate, not hardware. Circuits over 15,000 logical gates are
rejected for local fitting. Export remains available for larger circuits.

The classical baseline searches valid categorical assignments directly using
multistart coordinate descent and two-position simulated annealing, under a
0.1–5 second wall-clock budget. It does not enumerate a large space or waste
work on invalid binary codes. Spaces of at most 4,096 valid sequences instead
receive an exact classical reference. The search reports its algorithm,
evaluations, seed, elapsed time and improvement history. A heuristic best score
is not labeled a global optimum.

Reports compare sampled objective quality and elapsed time, plus feasible-shot
frequency and frequency of matching/beating the classical score. Binomial Wilson
intervals assume independent shots; they do not model hardware drift,
correlations or parameter-selection bias. Runs with no feasible samples return
no proposed sequence. No classical result is inserted into the quantum samples.

The saved example in `experiments/scalable_sequence_10_positions/` contains an
actual local 20-qubit run, input, outputs and executable circuit. Its classical
and quantum-sampled best objectives matched; it does not establish speedup.

## IBM account setup (backend terminal only)

From `Peptide-Project`, with `qiskit-env` active:

```powershell
python -m pip install -r backend/sequence_design/requirements-qpu.txt
```

If Qiskit already has your default account saved, it is used by
`QiskitRuntimeService()` when no environment token is supplied. Otherwise, set
credentials **in the terminal that launches the backend**, using secure input:

```powershell
$env:QISKIT_IBM_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'IBM API key' -AsSecureString)).Password
$env:QISKIT_IBM_INSTANCE = Read-Host 'IBM service instance CRN'
```

Enable the hardware adapter, then start/restart the backend:

```powershell
$env:PEPPERQ_ENABLE_QPU = '1'
python -m uvicorn backend.api:app --reload
```

Credentials are never sent to the browser, written to experiment JSON, printed,
or accepted as API request fields. Keep them out of Git. These environment
variables apply only to that terminal/process tree. No account was configured
and no live hardware job was submitted during implementation or tests.

## Hardware workflow

1. Preview a modest design. Enter the name of an operational physical backend
   that your IBM account can access. Choose shots per angle set and a 10–180
   second job execution cap. The cap is not an estimated usage or remaining
   account allowance, and is not a reservation of that allowance.
2. Either edit the explicit gamma/beta sets (one to eight), or transfer the
   locally fitted angles using **Use local fitted angles for hardware
   verification**. A fresh preparation is required when inputs change.
3. **Prepare hardware circuit — no submission** connects read-only and runs a
   device-specific preset pass manager. It checks qubit capacity and operational
   status. Preparations over 15,000 logical gates, 20,000 routed two-qubit gates
   or routed depth 20,000 are rejected. Even circuits below these software limits
   may be too noisy to be useful. Inspect the displayed routed circuit statistics.
4. Review the preparation and explicitly select runtime consumption, then click
   **Submit prepared job to QPU**. One `SamplerV2` job broadcasts the one ISA
   circuit across the specified parameter sets. Total requested shots are
   `number_of_angle_sets * shots_per_set`, at most 8,192. No adaptive hardware
   optimization loop or hidden repeated submission runs.
5. Refresh status manually. Status polling does not submit a new job. Completed
   measurements are decoded from the logical `meas` register; transpilation's
   physical layout does not change the logical bit-order contract. The selected
   angle set minimizes sampled mean penalized cost. Selection can overfit shot
   noise; the report explicitly states that there is no independent holdout.
6. Download the complete job/result JSON. It includes all angle sets, counts,
   shots, selected result, classical baseline, mapping checks, compilation stats,
   submission timestamp, job ID, reported QPU usage and submission-to-retrieval
   wall time. The latter includes queue and manual polling delay. QPU usage alone
   is not end-to-end runtime or a speedup claim.

Prepared circuits/requests and job IDs persist under `.cache/pepperq-qpu/`
(already excluded by `.gitignore`). Save the preparation ID to recover status
after a backend restart, even if browser storage is unavailable. The page stores
only that ID in local storage. Preparations expire after one hour. Submission
intent is recorded before the SDK call and duplicate submission is blocked. If
submission fails without a job ID, **check IBM's workload dashboard before
creating another preparation**; the service might have received the job. Cancel
is explicit and cannot refund already consumed runtime. If the process crashes
during submission, it likewise cannot safely retry automatically.

## Why the 50-qubit full alphabet is not a first hardware benchmark

The 10-by-20 example compiles quickly without global enumeration, but currently
has roughly 43,500 Pauli terms and 405,000 logical gates per layer before device
routing (goal-dependent). Its uniform valid-code probability is only
`(20/32)^10`, about 0.91%. This prototype therefore permits preview/export but
rejects hardware preparation/local simulation of that circuit under the stated
budgets. Reduce choices/positions for actual runs. More efficient arithmetic,
constraint-preserving mixers or alternative encodings would be separate work,
not something increasing the qubit cap solves.

This infrastructure makes a real experiment possible. It does not promise that
QAOA beats capable classical optimization, and the current descriptor objective
may remain straightforward for classical methods.

## API

All endpoints below are under `/api/v1/sequence-design/scalable`:

- `POST /preview`, `/optimize`, `/export`: `ScalableChoiceRequest`.
- `POST /qpu/prepare`: `{design, backend_name, max_execution_seconds}`.
- `POST /qpu/submit`: `{prepared_id, confirm_runtime: true}`.
- `GET /qpu/jobs/{prepared_id}`: status and completed result.
- `POST /qpu/jobs/{prepared_id}/cancel`: explicit cancellation.

These are additive version-2 contracts. Earlier sequence endpoints are unchanged.

IBM references: [Sampler input/output and measurement counts](https://quantum.cloud.ibm.com/docs/en/guides/sampler-input-output),
[job execution caps](https://quantum.cloud.ibm.com/docs/en/guides/max-execution-time),
[workload usage](https://quantum.cloud.ibm.com/docs/en/ibm-quantum-compute/estimate-job-run-time).
