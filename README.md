# PepperQ

**Quantum-assisted peptide sequence design and optimization**

Built for USC × IBM Qiskit Fall Fest 2026.

PepperQ is a research platform that explores how quantum optimization can be applied to peptide sequence design. Users can configure amino-acid sequences, define chemical constraints, and run quantum optimization experiments using Qiskit.

The project also compares quantum results with classical methods to evaluate how well each approach performs.

**Tech stack:** Python, Qiskit, FastAPI, React, TypeScript, Vite, RDKit, Biopython

## Overview

Peptides are chains of amino acids whose sequences influence properties such as charge and hydrophobicity. Designing a sequence around specific chemical goals creates a search problem that grows as more positions and amino-acid choices are introduced.

PepperQ explores this problem using the Quantum Approximate Optimization Algorithm (QAOA), a hybrid quantum-classical optimization method.

Our original idea focused on selecting combinations of existing peptides. After comparing that approach against classical optimization, we shifted toward designing the sequences themselves.

The project is an exploration of quantum optimization, not a claim of quantum advantage or experimentally validated peptide discovery.

## Features

**Peptide Sequence Designer**

- Configure peptide length and amino-acid options.
- Select fixed and editable sequence positions.
- Define target charge and hydrophobicity ranges.
- Preview chemical constraints and the search space.
- Run QAOA optimization through a Python backend.
- Compare generated sequences with classical results.

**Scalable QPU Lab**

- Explore larger sequence-design problems.
- Examine how the number of qubits grows with the search space.
- Generate and inspect quantum circuits.
- Experiment with approximate simulation and circuit preparation.
- Explore optional IBM Quantum hardware workflows.

**Peptide Research Tools**

- Browse peptide reference information.
- Examine calculated molecular properties.
- Explore molecular structure representations.
- Review earlier peptide-blend optimization experiments.

## Getting Started

### Requirements

Install the following before starting:

- [Git](https://git-scm.com/downloads)
- [Python 3.12](https://www.python.org/downloads/)
- [Node.js](https://nodejs.org/) (recent LTS version)
- A code editor such as [Visual Studio Code](https://code.visualstudio.com/)

You will need two terminals: one for the backend and one for the frontend.

### 1. Download the project

Clone the repository:

```bash
git clone https://github.com/NihalK321/Peptide-Project.git
cd Peptide-Project
```

Alternatively, click **Code → Download ZIP** on GitHub and extract the project.

All commands below should initially be run from the main project directory.

### 2. Start the backend

Open a terminal in the project directory.

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Once running, the backend is available at:

**http://127.0.0.1:8000**

API documentation:

**http://127.0.0.1:8000/docs**

To confirm the server is working, visit:

**http://127.0.0.1:8000/health**

The expected response is:

```json
{"status":"ok"}
```

Leave this terminal running.

### 3. Start the frontend

Open a second terminal in the main project directory.

```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Vite will display a local development URL, typically:

**http://localhost:5173**

Open this address in your browser.

The frontend communicates with the Python backend, so both servers must remain running for optimization features to work.

For macOS/Linux instructions and troubleshooting, see [Local Setup](docs/LOCAL_SETUP.md).

## Running an Experiment

Once both services are running:

1. Open the [Peptide Designer](http://localhost:5173/designer).
2. Load an example sequence or configure your own design.
3. Choose the editable positions and allowed amino acids.
4. Set the desired chemical properties and constraints.
5. Preview the search space.
6. Run QAOA optimization.
7. Examine the candidate sequences, optimization scores, and classical comparison.

For larger problems, open the [Scalable QPU Lab](http://localhost:5173/sequence-qpu).

Start with the smaller examples before attempting larger quantum circuits, which may require additional dependencies or computing resources.

## How It Works

PepperQ follows a hybrid quantum-classical workflow.

1. **Sequence configuration:** A user specifies amino-acid choices, fixed positions, and chemical goals.
2. **Chemical scoring:** Python evaluates estimated peptide properties and constructs an optimization objective.
3. **Quantum optimization:** Qiskit implements QAOA to search for low-cost solutions.
4. **Classical comparison:** Exact enumeration or classical heuristics provide benchmarks, depending on the problem size.
5. **Results:** The frontend displays candidate sequences, scores, optimization details, and circuit information.

Standard QAOA experiments run through local quantum simulation on a classical computer. Preparing a circuit for quantum hardware is different from executing it on a physical quantum processor.

## Project Structure

```text
Peptide-Project/
├── backend/
│   ├── api.py
│   ├── requirements.txt
│   ├── sequence_design/
│   ├── blends/
│   └── quantum.py
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
├── data/
├── experiments/
├── research/
├── docs/
└── README.md
```

The backend contains the API, optimization algorithms, molecular modeling code, and benchmarking utilities. The frontend contains the web interface and API integration.

## Testing

To run the sequence-design tests from the project root on Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/sequence_design/test_sequence_design.py -q
```

To build the frontend:

```powershell
cd frontend
npm run build
```

Some larger simulation workflows require additional dependencies. These are documented in the [Sequence Design module](backend/sequence_design/README.md).

## Project Limitations

PepperQ is a computational research prototype.

- Chemical properties are calculated estimates, not experimental measurements.
- Generated sequences have not been validated for biological activity, safety, or therapeutic effectiveness.
- Quantum simulations do not establish an advantage over classical algorithms.
- Larger simulated quantum circuits can require substantial computational resources.
- Physical quantum hardware execution is optional and separate from the standard local simulation workflow.

The goal of the project is to explore the methods, challenges, and potential applications of quantum optimization in peptide research.

## Team

Developed by Neeshan Syed, Nihal Katta, and Sawyer Wade.

**USC × IBM Qiskit Fall Fest 2026**

## Additional Documentation

- [Local installation and troubleshooting](docs/LOCAL_SETUP.md)
- [Sequence design implementation](backend/sequence_design/README.md)
- [Large-circuit experiments](backend/sequence_design/LARGE_CIRCUITS.md)
- [Scalable QPU documentation](backend/sequence_design/SCALABLE_QPU.md)
