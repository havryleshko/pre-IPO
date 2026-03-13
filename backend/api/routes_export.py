from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.database.queries import get_analysis_by_id

router = APIRouter(prefix="/analyses", tags=["export"])


class ExportLockResponse(BaseModel):
    analysis_id: str
    export_locked: bool


@router.get("/{analysis_id}/export/lock", response_model=ExportLockResponse)
async def get_export_lock(analysis_id: str) -> ExportLockResponse:
    analysis = await get_analysis_by_id(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    record = dict(analysis)
    return ExportLockResponse(
        analysis_id=analysis_id,
        export_locked=record.get("export_locked", True),
    )


async def _check_export_allowed(analysis_id: str) -> dict:
    analysis = await get_analysis_by_id(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    record = dict(analysis)
    if record.get("export_locked", True):
        raise HTTPException(
            status_code=403,
            detail="Export locked. Confirm all flags before exporting.",
        )
    return record


@router.get("/{analysis_id}/export/summary")
async def export_summary_pdf(analysis_id: str) -> Response:
    record = await _check_export_allowed(analysis_id)
    try:
        from backend.export.pdf_summary import generate_summary_pdf

        pdf_bytes = await generate_summary_pdf(record)
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="PDF export not yet implemented",
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{record.get("company_name", "summary")}_ipo_summary.pdf"'
        },
    )


@router.get("/{analysis_id}/export/full")
async def export_full_report_pdf(analysis_id: str) -> Response:
    record = await _check_export_allowed(analysis_id)
    try:
        from backend.export.pdf_full_report import generate_full_report_pdf

        pdf_bytes = await generate_full_report_pdf(record)
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="PDF export not yet implemented",
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{record.get("company_name", "report")}_ipo_full_report.pdf"'
        },
    )
