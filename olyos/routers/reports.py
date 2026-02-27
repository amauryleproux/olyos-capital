"""Reports API Router - PDF report generation."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from olyos.dependencies import get_pdf_report_service
from olyos.services.pdf_report import PDFReportService
from olyos.logger import get_logger

log = get_logger('router.reports')
router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/generate")
def generate_report(
    month: int = Query(None),
    year: int = Query(None),
    service: PDFReportService = Depends(get_pdf_report_service),
):
    """Generate PDF monthly report."""
    try:
        m = month or datetime.now().month
        y = year or datetime.now().year
        pdf_bytes, filename = service.generate_report(m, y)
        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        log.error(f"Error generating report: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/latest")
def get_latest_report(
    service: PDFReportService = Depends(get_pdf_report_service),
):
    """Get the most recent report."""
    try:
        pdf_bytes, filename = service.get_latest_report()
        if pdf_bytes and filename:
            return Response(
                content=pdf_bytes,
                media_type='application/pdf',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'},
            )
        return JSONResponse(status_code=404, content={'success': False, 'error': 'No reports found'})
    except Exception as e:
        log.error(f"Error getting latest report: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/list")
def list_reports(
    service: PDFReportService = Depends(get_pdf_report_service),
):
    """List all available reports."""
    try:
        reports = service.list_reports()
        return {'success': True, 'data': reports}
    except Exception as e:
        log.error(f"Error listing reports: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})
