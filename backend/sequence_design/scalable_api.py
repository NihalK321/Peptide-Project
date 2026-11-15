"""Additive scalable and hardware routes; no changes to earlier contracts."""

from fastapi import APIRouter, HTTPException
from .scalable_choices import ScalableChoiceRequest, preview_scalable, run_scalable
from .qpu_sequence import PrepareQPU, SubmitQPU, prepare_qpu, submit_qpu, poll_qpu, cancel_qpu

router = APIRouter(prefix="/scalable", tags=["Scalable sequence QAOA v2"])


def invoke(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ImportError:
        raise HTTPException(status_code=503, detail="Install the optional sequence QPU requirements on the backend.") from None


@router.post('/preview')
def preview(request: ScalableChoiceRequest):
    return invoke(preview_scalable, request)


@router.post('/optimize')
def optimize(request: ScalableChoiceRequest):
    return invoke(run_scalable, request)


@router.post('/export')
def export(request: ScalableChoiceRequest):
    return invoke(run_scalable, request, export_only=True)


@router.post('/qpu/prepare')
def prepare(request: PrepareQPU):
    return invoke(prepare_qpu, request)


@router.post('/qpu/submit')
def submit(request: SubmitQPU):
    return invoke(submit_qpu, request)


@router.get('/qpu/jobs/{prepared_id}')
def status(prepared_id: str):
    return invoke(poll_qpu, prepared_id)


@router.post('/qpu/jobs/{prepared_id}/cancel')
def cancel(prepared_id: str):
    return invoke(cancel_qpu, prepared_id)
