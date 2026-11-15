# Whole-peptide blend research, contract 1.0

For the validated matrix derivation, descriptor handoff, response contract,
presentation exports, and reproduction commands, see [QUBO_CONTRACT.md](QUBO_CONTRACT.md).

This module is independent of the existing bond-angle optimizer. Here each bit
selects a **whole peptide**, with the rightmost bit selecting candidate 0.
The initial experiment is 8 candidates, select 3: 256 bitstrings, 56 feasible
subsets. No compound mixing, dose, therapeutic action, or synergy is modeled.

## Run the website

With the virtual environment activated, start the backend from the repository
root (the folder containing `backend` and `frontend`):

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.api:app --reload
```

In another terminal, start the frontend:

```powershell
cd frontend
npm run dev
```

Open the printed frontend address and choose **Peptide Designer**. Set chemical
targets, click **Auto-shortlist 8**, and then **Optimize blend with QAOA**.
Alternatively, search and select database entries manually. Live results
appear above the marked legacy demo controls. The dashboard displays
the latest run saved in this browser, including its original targets.

Vite proxies `/api` to `http://127.0.0.1:8000`; change
`VITE_PEPPERQ_BACKEND_URL` before starting Vite to use another backend address.
The generated circuit is downloadable as OpenQASM 2 for IBM Composer.
This workflow uses `backend/blends/quantum.py`; the existing
`backend/quantum.py` still belongs to the separate bond-angle experiment.

For validation from the repository root:

```powershell
$env:MPLBACKEND = 'Agg'
python -m pytest backend -q
```

## Workflow and API

1. `GET /api/v1/blends/catalog?search=...&page=1`: browse authentic local records.
2. `POST /api/v1/blends/shortlist`: classically score the filtered local catalog
   and retain the 8 highest individual property scores. Returns source counts,
   scored count, target settings, descriptor methods, and the scope limitation.
3. `POST /api/v1/blends/optimize`: use those candidate IDs, or a manually chosen
   pool of 2–8 source IDs, and run actual Qiskit QAOA plus an exact reference.

Goals: `ph` (default 7.4), `target_charge` (0 e), `target_hydropathy` (0),
`charge_weight` (0.5), `hydropathy_weight` (0.5), `diversity_weight` (0.3).
At least one property weight must be positive. Targets apply to **individual
candidate descriptors**, not a mixture-level quantity. Shortlisting also accepts
`search`, `min_length` (2), `max_length` (60), and `pool_size` (8).
Optimization adds `candidate_ids`, `blend_size` (3), `layers` (1, max 2),
`max_iterations` (60, max 120), `shots` (2048), and `seed` (42).

The read-only catalog adapter combines the existing provenance-rich peptide
library with the earlier DBAASP SQLite catalog, deduplicating identical sequences.
Documented modified/unsupported records are excluded rather than substituting
residues. Standard-letter sequences without annotations still have **unknown**
chemical form. Descriptor calculations explicitly assume linear free termini.
No network import or fabricated fallback occurs during a request.

## Research scoring contract: sequence-research-v1

This is an explicit, configurable research proxy chosen for the user-requested
charge/hydropathy/diversity experiment, not a validated biological objective.

- Charge: Biopython `ProteinAnalysis.charge_at_pH`, Bjellqvist pKa model, e.
- Hydropathy: Biopython `gravy`, Kyte-Doolittle residue mean, dimensionless.
- Mass: average isotopic molecular mass, Da, free-termini linear chain.
- Charge score: `1 / (1 + abs(charge-target_charge)/2)`, tolerance 2 e.
- Hydropathy score: `1 / (1 + abs(GRAVY-target_hydropathy))`, tolerance 1.
- Individual score S: weighted mean of the two scores, in [0,1].
- Pair term P: Jaccard overlap of the sets of adjacent residue pairs, in [0,1].
  It discourages sequence-motif redundancy; it is not an interaction energy.

Minimize `-sum(S_i*x_i) + diversity_weight*sum(P_ij*x_i*x_j) + lambda*(sum(x)-k)^2`.
The code expands the square into QUBO coefficients and uses `x=(1-Z)/2` to map
to an Ising operator. Lambda is `sum(S) + diversity_weight*sum(P) + 1`, greater
than the full unpenalized objective range, so infeasible bitstrings cannot beat
feasible ones at the exact global minimum. Finite-depth QAOA may still sample
infeasible strings. Feasibility is always reported.

The Qiskit circuit uses H preparation, native RZ/RZZ cost gates and RX mixing.
SciPy COBYLA minimizes the ideal expected penalized cost; finite-shot counts are
sampled afterward. The best **feasible sampled** blend is reported separately
from the exact optimum. If no feasible sample exists, the result is explicitly
`no_feasible_sample`; no classical result is substituted as a quantum result.
The response includes all coefficients, mappings, actual evaluation history,
feasibility/optimum probabilities, seeds, convergence, QASM, and limitations.

The classical shortlist is not a proof of the globally best blend over the full
database. The exact guarantee applies only to the small supplied pool under this
score. The model does not predict compatibility, solubility, safety, or efficacy.

References:
- [Biopython ProtParam](https://biopython.org/docs/latest/api/Bio.SeqUtils.ProtParam.html)
- [Biopython charge model](https://biopython.org/docs/latest/api/Bio.SeqUtils.IsoelectricPoint.html)
- [IBM QAOA / Ising mapping](https://quantum.cloud.ibm.com/learning/en/courses/quantum-computing-in-practice/utility-scale-qaoa)
- [DBAASP attribution](https://doi.org/10.1093/nar/gkaa991)
