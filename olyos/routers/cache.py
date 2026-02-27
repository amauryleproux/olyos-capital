"""Cache API Router - Cache statistics and management."""

import os
import shutil

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from olyos.logger import get_logger

log = get_logger('router.cache')
router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.get("/stats")
def cache_stats():
    """Get cache statistics."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        stats = app.get_cache_stats()
        return stats
    except Exception as e:
        log.error(f"Error getting cache stats: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.post("/clear")
def clear_cache():
    """Clear all cached data."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        if hasattr(app, 'CACHE_DIR') and os.path.exists(app.CACHE_DIR):
            shutil.rmtree(app.CACHE_DIR)
        if hasattr(app, 'ensure_cache_dir'):
            app.ensure_cache_dir()
        return {'message': 'Cache cleared successfully'}
    except Exception as e:
        log.error(f"Clear cache error: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})
