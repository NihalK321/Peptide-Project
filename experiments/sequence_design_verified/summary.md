# Actual restricted sequence-design experiment

Qiskit ideal-statevector simulation; shot counts are simulated, not hardware.
Illustrative template, not a therapeutic reference: GAGAGAGA
Variable-position mapping: [{'qubit': 0, 'position': 2, 'choices': ['A', 'K']}, {'qubit': 1, 'position': 4, 'choices': ['A', 'K']}, {'qubit': 2, 'position': 6, 'choices': ['A', 'K']}, {'qubit': 3, 'position': 8, 'choices': ['A', 'K']}]
Research goals: {'ph': 7.4, 'target_charge': 2, 'charge_weight': 1, 'hydropathy_min': -1.5, 'hydropathy_max': 0.5, 'hydropathy_weight': 0.5, 'adjacent_repeat_weight': 0}
Required residues: ['K']; maximum changes: 2

Best feasible observed sequence: GKGKGAGA
Observed raw objective: 0.03338474130049727
Exact classical reference: GKGKGAGA; raw objective 0.03338474130049727
Sampled objective gap: 0.0
Feasible simulated shots: 1398/2048
Ideal probability of an optimum: 0.5956668885353648
Tied exact optima: 6
Optimizer converged: True; 29 evaluations
Cost representation: higher_order_diagonal; polynomial degree 4
Validation: {'checked_states': 16, 'cost_reconstruction_max_error': 1.6653345369377348e-16, 'all_feasible_energies_below_all_infeasible': True}

The exact answer is never substituted as a quantum result. Matching its score
does not establish guaranteed success, biological efficacy or quantum advantage.
All cost states were enumerated classically for this bounded experiment.
