import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

from app.api import final_videos, inbox, assistant, auth, contractors, finance, intake, operations, phones, plaques, projects, system, imports, shopify, undo
from app.config import get_settings
from app.integrations.drive.base import DriveError
from app.integrations.sheets.base import SheetsError

# register job handlers
import app.services.sheets_sync  # noqa: F401,E402
import app.services.intake  # noqa: F401,E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="HAYAH AI – Operations API", version="0.5.0",
                  docs_url="/api/docs" if s.env != "production" else None, openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        if s.env == "production":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    @app.exception_handler(StaleDataError)
    async def stale(_, __):
        return JSONResponse({"detail": "This record was changed by someone else. Reload and try again."}, status_code=409)

    @app.exception_handler(DriveError)
    async def drive_down(_, exc):
        return JSONResponse({"detail": f"Google Drive is unavailable, nothing was saved. Try again. ({exc})"}, status_code=502)

    @app.exception_handler(SheetsError)
    async def sheets_down(_, exc):
        return JSONResponse({"detail": f"Google Sheets is unavailable. ({exc})"}, status_code=502)

    for r in (auth.router, auth.users, contractors.router, projects.router, operations.delivery, operations.maintenance,
              operations.media, operations.review, intake.router, system.router, final_videos.router, inbox.router, inbox.settings_router, finance.router, finance.sacrifices,
              assistant.router, imports.router, undo.router, shopify.router, plaques.router, phones.router):
        app.include_router(r)
    return app


app = create_app()
