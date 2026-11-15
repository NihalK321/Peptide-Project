# React + TypeScript + Vite

## New peptide sequence-design workflow

Open **Sequence Design** (`/sequence-design`), the first navigation item.
All existing library, blend, chemistry, results, and VQE pages remain available.

Use an existing template and choose which positions can vary, or select a length
and specify fixed/variable residues. Apply changed templates/lengths before using
the position editor. Each variable position has two distinct choices; this
prototype supports up to eight variable positions within a 2-50-residue chain.
For 9-50 variable positions, select the new bounded MPS or circuit-preparation
execution mode, or click **Load 50-qubit example**. Large mode has stricter
quadratic-objective constraints and shows a classical heuristic rather than a
claimed exact optimum. Its CPU simulation timings are not QPU speedup figures;
see [large-circuit documentation](../backend/sequence_design/LARGE_CIRCUITS.md).
Allowed residues are not required to appear; list required residues separately.

Set solution pH, target estimated charge, hydropathy range, and optional mutation
budget and adjacent-repeat design preference. **Validate and preview** calculates
the restricted space and template descriptors without executing QAOA. **Run
Sequence QAOA** performs actual local Qiskit simulation through the new versioned
backend endpoints. The page shows observed feasible candidate sequences, raw
scores, exact reference, gap, counts, fitted circuit and history, model limits,
and JSON/QASM exports. It can request an RDKit 2D connectivity drawing of the
proposed sequence; this is not a 3D fold. Original 3D tools remain on Molecular
Analysis. Valid submitted inputs and results are saved in this browser when
storage is available. Changed inputs mark prior results as snapshots.

Start the same FastAPI and Vite servers as below; no new dependency is required.
No IBM QPU is contacted. See
[`backend/sequence_design/README.md`](../backend/sequence_design/README.md)
for the exact cost, constraints, encoding and scientific limits.

## Live blend optimization

Start FastAPI from the repository root with
`python -m uvicorn backend.api:app --reload`, and start Vite from `frontend/`
with `npm run dev`.

1. Open **Peptide Designer** (`/designer`), set chemical targets, and select
   up to eight supported peptides or click **Auto-shortlist 8**.
2. Set how many whole peptides to select (initial experiment: three of eight).
3. Click **Continue to Blend Optimization** (`/optimization`).
4. Set QAOA layers (1-2), objective evaluation budget (10-120), simulated shots
   (128-8192), and seed, then click **Run Quantum Optimization**.
5. Inspect the real simulated selection, exact classical reference, feasibility,
   objective gap, and actual optimization history. Expand the details for QUBO
   coefficients, fitted angles, all candidate descriptors, and shot counts.
   Download the full result JSON or the Composer-compatible OpenQASM circuit.

The existing `POST /api/v1/blends/optimize` contract is reused. Peptide
selection and targets live in Designer; QAOA submission lives in Optimization.
The draft survives navigation and refresh via browser local storage. If storage
is blocked, the draft still transfers between pages during the visit and the UI
explains the persistence limitation. The latest completed result is separately
saved for the dashboard. Results are marked as a previous-run snapshot whenever
candidate IDs, sequences, goals, cardinality, or execution settings differ.

No request runs on page load or on a settings change. Runs are local ideal
Qiskit simulations with simulated shot sampling; no IBM QPU job is submitted.
There are no fabricated fallback candidates, convergence traces, or results.
The older Designer panels below the demo notice remain separate display fixtures.

Verified with the real local catalog/backend: eight-candidate route handoff,
two-layer QAOA and custom settings, reload persistence, result exports, stale
result labeling, invalid-input prevention, failed request/retry, blocked storage,
dashboard propagation, and desktop/mobile rendering. Build and lint also pass.

## Automatic molecular structure viewer

The Molecular Analysis page (`/chemistry`) automatically requests a generated
PDB model and displays it under Structure Stats with 3Dmol. No download or file
upload is required. It initially models `GAGA`; enter another 2–8-residue
standard sequence and click **Show structure** to update it. The modeled sequence
is independent of the page's demonstration candidate and descriptor fixtures.

Start the backend from the repository root in one terminal:

```powershell
python -m uvicorn backend.api:app --reload
```

Start the frontend from `frontend/` in another:

```powershell
npm ci
npm run dev
```

The adapter in `src/services/molecularStructure.ts` uses the existing FastAPI
0.2.0 `POST /optimize` contract and reads `best_structure_pdb`. Its default
backend URL is `http://127.0.0.1:8000`; set `VITE_STRUCTURE_API_BASE_URL` in
`.env.local` and restart Vite to change it. This URL is separate from the
proposed `/api/v1` APIs elsewhere in the UI. The backend allows localhost ports
5173 and 3000 by default; configure `PEPTIDE_CORS_ORIGINS` if using another origin.

Models use classical MMFF94 evaluation, seed 42, and up to three supported
backbone torsions with two angles each. The UI displays the actual modeled
sequence and provenance. These are generated conformers, not experimentally
verified structures, quantum electronic-structure results, or activity predictions.
If the backend is unavailable, the viewer displays an error and can be retried
using **Show structure**; it never substitutes a fabricated model. WebGL is
required. Local PDB/SDF/MOL loading remains available after a model is loaded.

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.


Sequence Design also offers **Multi-choice sequence design** (the default for a
new browser). Click **Load 20-amino-acid example**, or select that execution method,
then check up to two editable positions. Choose each position's allowed amino
acids using its checkboxes; **Select all globally allowed** applies the current
global allowed/excluded alphabet to that position. Fixed positions retain their
fixed residue. Two positions with all 20 choices use 10 qubits and represent 400
valid sequences in 1,024 binary states. Unused codes receive a cost penalty and
cannot become proposed peptides. Validate, then run QAOA; results include an exact
classical reference and the circuit download. Existing binary and 50-qubit modes
are still available through the execution-method selector. This mode uses local
ideal simulation, not IBM hardware, and does not claim a quantum speedup.


The Sequence Design page links to **Scalable QPU Lab** at `/sequence-qpu`. It supports ten editable sites, up to twenty amino acids each, an algebraic cost compiler, categorical classical search, bounded local MPS fitting, and explicit IBM Runtime preparation/submission/status/recovery. See [backend setup and limits](../backend/sequence_design/SCALABLE_QPU.md). Nothing submits automatically or consumes hardware runtime during local fitting.


Active quantum workflows share a **Use IBM quantum computer (QPU)** checkbox. After one-time server account setup, enter a backend name, check the box and press the page Run button. Settings are reused across pages. Supported routes are sequence, scalable sequence, blend, torsion-grid and selected-geometry HeH+ energy estimation. Existing small solvers use local parameter fitting followed by hardware verification; this is not all-hardware adaptive training. Checking the box alone never submits. Quick jobs use `/api/v1/hardware/run`; recoverable UUIDs are saved before networking. Demo-only comparison/noise pages remain fixtures. See [setup and execution boundaries](../backend/sequence_design/SCALABLE_QPU.md).
