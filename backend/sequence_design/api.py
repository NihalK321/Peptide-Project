"""New versioned sequence endpoints; no existing blend or VQE route is changed."""

from fastapi import APIRouter, HTTPException
from .models import SequenceDesignRequest, StructureRequest
from .solver import optimize, preview

router = APIRouter(prefix="/sequence-design", tags=["Sequence design v1"])


@router.post("/preview")
def preview_design(request: SequenceDesignRequest):
    try:
        return preview(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/optimize")
def optimize_design(request: SequenceDesignRequest):
    try:
        return optimize(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/structure")
def sequence_structure(request: StructureRequest):
    from rdkit import Chem
    from rdkit.Chem import rdDepictor
    from rdkit.Chem.Draw import rdMolDraw2D
    molecule = Chem.MolFromFASTA(request.sequence)
    if molecule is None:
        raise HTTPException(status_code=422, detail="Unable to construct this standard peptide.")
    rdDepictor.Compute2DCoords(molecule)
    drawer = rdMolDraw2D.MolDraw2DSVG(1200, 450)
    drawer.DrawMolecule(molecule)
    drawer.FinishDrawing()
    return {"sequence": request.sequence, "svg": drawer.GetDrawingText(), "provenance": "calculated",
            "model": "RDKit 2D connectivity depiction; not a 3D fold, conformer, or quantum chemistry calculation"}
