# PepperQ — Local Setup Guide

This guide explains how to install and run PepperQ locally.

The project has two components: a Python/FastAPI backend that runs the optimization algorithms and a React frontend that provides the interface.

Both need to run at the same time.

## Prerequisites

Make sure Git, Python 3.12, Node.js, and npm are installed.

To check on Windows:

```powershell
git --version
py -3.12 --version
node --version
npm --version
```

Python 3.12 is recommended for compatibility with the scientific computing dependencies.

## Step 1: Clone the Repository

```powershell
git clone https://github.com/NihalK321/Peptide-Project.git
cd Peptide-Project
```

The correct project folder should contain both `backend` and `frontend`.

## Step 2: Install Backend Dependencies

Open a PowerShell terminal in the main project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

The backend should now be running at:

http://127.0.0.1:8000

Check its status:

http://127.0.0.1:8000/health

API documentation:

http://127.0.0.1:8000/docs

Keep this terminal open.

## Step 3: Install Frontend Dependencies

Open a second terminal in the main project folder:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Open the address provided by Vite, usually:

http://localhost:5173

The main sequence-design interface is available at:

http://localhost:5173/designer

The Scalable QPU Lab is available at:

http://localhost:5173/sequence-qpu

## macOS and Linux

From the repository root, start the backend:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Open http://localhost:5173.

## Environment Configuration

The frontend includes a `.env.example` file.

For local development, the default configuration is:

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_PEPPERQ_BACKEND_URL=http://127.0.0.1:8000
VITE_STRUCTURE_API_BASE_URL=http://127.0.0.1:8000
```

The frontend uses a development proxy to send API requests to FastAPI.

If the backend port changes, update the corresponding URLs in `frontend/.env.local` and restart the frontend.

Do not commit `.env.local` or private credentials.

## Testing the Application

After starting both servers:

1. Open the Peptide Designer.
2. Load a demonstration configuration.
3. Preview the design constraints.
4. Run a small QAOA optimization.
5. Review the generated sequences and classical benchmark.

You can also test backend endpoints in the Swagger interface at http://127.0.0.1:8000/docs.

The main sequence-design endpoints include:

- `POST /api/v1/sequence-design/preview`
- `POST /api/v1/sequence-design/optimize`
- `POST /api/v1/sequence-design/structure`

## Troubleshooting

### Port 8000 is unavailable

If the backend reports a port or socket error, try port 8765:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8765
```

Change the frontend environment settings to:

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_PEPPERQ_BACKEND_URL=http://127.0.0.1:8765
VITE_STRUCTURE_API_BASE_URL=http://127.0.0.1:8765
```

Restart Vite after saving the changes.

### Vite is not recognized

Make sure you are inside the `frontend` folder and that npm finished installing successfully.

```powershell
npm ci
npm run dev
```

### Windows reports EPERM during npm installation

A running Node process or another application may be locking a dependency.

Stop Vite first, then run from the `frontend` directory:

```powershell
Stop-Process -Name node -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\node_modules
npm ci
npm run dev
```

This also closes other running Node.js processes.

### The frontend loads, but optimization returns Not Found

Check that the backend is running and that the API documentation contains the sequence-design endpoints.

Verify that the port in `.env.local` matches the port used by Uvicorn.

Restart the frontend after updating the environment settings.

### The wrong project opens

Confirm the repository URL:

```powershell
git remote get-url origin
```

It should point to:

```text
https://github.com/NihalK321/Peptide-Project.git
```

If it points to `HeHPlus-Quantum-Chemistry`, you have opened a different repository.

### Python dependencies fail to install

Use Python 3.12 rather than assuming the latest Python release will be compatible with every scientific computing library.

Create a fresh virtual environment with the correct interpreter if necessary.

## Optional Large-Circuit Simulation

Some larger experiments use Qiskit Aer, which is not included in the basic backend requirements.

From the repository root, install:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\sequence_design\requirements-large.txt
```

Large simulations may consume significant CPU and memory. Start with smaller examples before increasing the problem size.

Additional information is available in the sequence-design documentation.

## Notes

PepperQ uses simulated quantum computation for its standard experiments. Physical IBM Quantum execution requires additional setup and is not necessary to use the local application.

The project is intended for research and experimentation. Its results should not be treated as laboratory-validated peptide properties or evidence of quantum advantage.
