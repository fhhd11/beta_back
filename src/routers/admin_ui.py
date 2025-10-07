"""
Admin UI router - serves HTML pages for admin panel.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import structlog

from src.dependencies.admin_auth import verify_admin_auth

logger = structlog.get_logger(__name__)

router = APIRouter()

# Setup Jinja2 templates
templates = Jinja2Templates(directory="src/templates")


@router.get(
    "/",
    response_class=HTMLResponse,
    summary="Admin Dashboard",
    description="Main admin panel dashboard"
)
async def admin_dashboard(
    request: Request,
    admin_username: str = Depends(verify_admin_auth)
):
    """
    Render admin dashboard.
    Requires HTTP Basic Auth with admin secret key.
    """
    logger.info("Admin accessing dashboard", admin=admin_username)
    
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "admin_username": admin_username
        }
    )

