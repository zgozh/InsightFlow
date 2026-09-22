"""Analytics API 窄出口（Phase 2C2）。"""

from app.analytics.api.router import admin_router, install_request_error_handler, router

__all__ = ["admin_router", "install_request_error_handler", "router"]
