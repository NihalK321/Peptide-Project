# Verified peptide QUBO / QAOA experiment

Experiment: 38ab8e00-e3f9-4458-8449-93daabc0b0e2, 2026-11-14T23:47:25.607460+00:00

Execution: actual Qiskit ideal-statevector simulation, with seeded simulated shots.
This is not a hardware run. No quantum advantage or biological outcome is claimed.

- Candidate IDs in qubit order: dbaasp:11246, dbaasp:15524, dbaasp:19458, dbaasp:3225, dbaasp:5994, dbaasp:4338, dbaasp:21999, dbaasp:15642.
- Whole-peptide selection: exactly 3 of 8.
- QAOA sampled selection: ['dbaasp:11246', 'dbaasp:15524', 'dbaasp:19458'].
- Sampled bitstring (rightmost bit = candidate 0): 00000111.
- QAOA sampled raw objective: -2.8235836244068135.
- Exact classical selection: ['dbaasp:11246', 'dbaasp:15524', 'dbaasp:19458'].
- Exact classical raw objective: -2.8235836244068135.
- Optimality gap: 0.0.
- Feasible shots: 711 / 2048.
- Ideal probability of an optimum: 0.006409995154894129.
- COBYLA evaluations: 60; converged: False.
- Exhaustive validation: {'passed': True, 'checked_binary_states': 256, 'checked_feasible_subsets': 56, 'cardinality_separation_verified': True, 'absolute_tolerance': 1e-09, 'direct_vs_qubo_max_error': 1.1368683772161603e-13, 'matrix_vs_qubo_max_error': 1.1368683772161603e-13, 'ising_vs_qubo_max_error': 1.4210854715202004e-13}.

The best feasible observed sample is reported; an exact classical result is never
silently substituted. A zero observed gap does not mean guaranteed success on a
future shot, and a limited optimizer budget need not reach convergence.

`input.json` captures candidate sequences, descriptors, source URLs, and settings.
`result.json` contains the full upper-triangular QUBO, Ising offset/fields/couplings,
all 56 feasible subsets, actual fitting history, and feasible/infeasible counts.
`circuit.png` shows the actual fitted native circuit; `circuit.qasm` is its
equivalent expanded H/RZ/RX/CX representation for Composer.
