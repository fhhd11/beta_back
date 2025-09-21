#!/usr/bin/env python3
"""
Development server runner for AI Agent Platform API Gateway.
"""

import uvicorn
from src.config.settings import get_settings

if __name__ == "__main__":
    settings = get_settings()
    
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_config=None,  # Use our custom logging
        access_log=False,  # We handle access logging in middleware
        workers=1 if settings.is_development else settings.workers
    )
