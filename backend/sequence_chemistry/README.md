# PepperQ sequence-design chemistry prototype

**Status:** isolated chemistry-only research prototype, not QAOA, not experimental chemistry, and not automatically integrated into the running PepperQ website.

## MVP

8 variable positions, binary `0=L`/`1=K`, exactly 3 K required (56 feasible out of 256 states). Each sequence is evaluated under an *assumed* ideal alpha helix with 100 degrees of angular advance between residues. Hydropathy scale: Kyte-Doolittle (1982), `L = +3.8`, `K = -3.9`.

The hydrophobic moment squared is

`mu^2 = ((sum(h_i * cos(i*100 degrees))/8)^2 + (sum(h_i * sin(i*100 degrees))/8)^2)`.

It depends on residue order while average hydropathy and approximate side-chain charge do not, for fixed composition.

`chemistry_quadratic()` returns chemistry-only *minimization* coefficients for `-mu^2`, in an explicit **upper-triangular** coefficient convention. The quantum teammate independently adds a sufficiently large `lambda*(sum(x)-3)^2` selection penalty, forms the final QUBO and Ising Hamiltonian, maps bit-order, and verifies feasibility. No QAOA is executed by this package.

Approximate charge assumes standard free termini with pKa (N, C, K side chain) = (8.0, 3.1, 10.5). This is an educational Henderson-Hasselbalch estimate, not experimentally validated or sequence-environment-aware. Molecular mass is approximate average neutral, unmodified peptide mass.

**No experimental bioactivity, binding, folding, helix formation, safety or efficacy prediction.** Hydrophobic moment evaluates amphiphilic patterning only under the helical *assumption*.

## Run

From repository root:

```powershell
python -m backend.sequence_chemistry
python -m pytest backend/sequence_chemistry -q
```

Tests verify the quadratic expansion against direct calculation for **all 256** binary states, exactly 56 feasible sequences, positional ordering effects, and input validation.

## Contract for quantum teammate

`chemistry_quadratic()` returns:

- `constant`: one scalar
- `linear`: length 8, coefficient of each `x_i`
- `pairwise_upper_triangle`: 8x8; for `i<j`, coefficient used **once** for `x_i*x_j`
- `weight`: scalar used in `-weight * mu^2`
- `position_indexing`: N-to-C, zero-based

The QUBO teammate adds penalties and converts the combined model to the Ising operator. Do not multiply off-diagonals by two unless explicitly converting the coefficient convention to `x.T @ Q @ x` with symmetric `Q`.

`exact_reference()` computes the best feasible sequence by enumerating all 56 valid states, as well as the maximal algebraic-error check across all 256.

## Scientific sources

- Eisenberg, Weiss, Terwilliger (1982), *The helical hydrophobic moment: a measure of the amphiphilicity of a helix*, Nature 299, 371–374. https://doi.org/10.1038/299371a0
- Kyte & Doolittle (1982), *A simple method for displaying the hydropathic character of a protein*, Journal of Molecular Biology 157, 105–132. https://doi.org/10.1016/0022-2836(82)90515-0

Caution: the first source establishes the helical-moment idea; the hydropathy values here use the Kyte-Doolittle scale rather than claiming an Eisenberg-scale moment.
