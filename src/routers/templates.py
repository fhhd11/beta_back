"""
Template management endpoints (AMS proxy).
"""

from typing import Optional, List
from fastapi import APIRouter, Request, Depends, Header
import structlog

from src.dependencies.auth import get_current_user_id
from src.middleware.auth import require_admin
from src.services.ams_client import get_ams_client
from src.models.requests import TemplateValidationRequest, PublishTemplateRequest
from src.models.responses import ValidationResult

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/validate",
    response_model=ValidationResult,
    summary="Validate Template",
    description="Validate template content in YAML or JSON format"
)
async def validate_template(
    request: Request,
    validation_request: TemplateValidationRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Validate template content.
    
    Features:
    - Support for YAML and JSON formats
    - Strict validation mode
    - Content size limits (1MB)
    - Schema validation
    """
    logger.info(
        "Validating template",
        user_id=user_id,
        format=validation_request.template_format,
        content_length=len(str(validation_request.template_content)),
        strict=validation_request.strict_validation
    )
    
    # Get AMS client
    ams_client = await get_ams_client()
    
    # Validate template
    result = await ams_client.validate_template(
        template_content=str(validation_request.template_content),
        template_format=validation_request.template_format
    )
    
    # Convert to ValidationResult model
    validation_result = ValidationResult(
        is_valid=result.get("is_valid", False),
        errors=result.get("errors", []),
        warnings=result.get("warnings", []),
        schema_version=result.get("schema_version")
    )
    
    logger.info(
        "Template validation completed",
        user_id=user_id,
        is_valid=validation_result.is_valid,
        errors_count=len(validation_result.errors),
        warnings_count=len(validation_result.warnings)
    )
    
    return validation_result


@router.post(
    "/publish",
    summary="Publish Template",
    description="Publish a template (admin users only)"
)
async def publish_template(
    request: Request,
    publish_request: PublishTemplateRequest,
    user_id: str = Depends(get_current_user_id),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key")
):
    """
    Publish a template.
    
    Features:
    - Role-based access control (admin only)
    - Version management
    - Public/private visibility
    - Changelog support
    - Tag support
    - Idempotency support
    
    Note: This endpoint requires admin role.
    """
    # Apply admin role check
    await require_admin(request)
    
    logger.info(
        "Publishing template",
        user_id=user_id,
        template_id=publish_request.template_id,
        version=publish_request.version,
        is_public=publish_request.is_public,
        idempotency_key=x_idempotency_key
    )
    
    # Get AMS client
    ams_client = await get_ams_client()
    
    # Publish template
    result = await ams_client.publish_template(
        user_id=user_id,
        template_id=publish_request.template_id,
        version=publish_request.version,
        is_public=publish_request.is_public,
        changelog=publish_request.changelog,
        tags=publish_request.tags,
        idempotency_key=x_idempotency_key
    )
    
    logger.info(
        "Template published successfully",
        user_id=user_id,
        template_id=publish_request.template_id,
        version=publish_request.version
    )
    
    return result
