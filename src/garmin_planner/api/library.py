"""Rutas de library."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from garmin_planner.api.schemas import (
    EnabledBody,
)
from garmin_planner.library import MAX_UPLOAD


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()

    @router.get("/api/library", dependencies=[Depends(authenticated)])
    def library_state():
        return app.state.library.listing()

    @router.post("/api/library/upload", dependencies=[Depends(authenticated)])
    async def library_upload(
        request: Request,
        filename: str = Query(min_length=1, max_length=250),
        title: str = Query(default="", max_length=200),
        author: str = Query(default="", max_length=200),
        document_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{32}$"),
    ):
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "El archivo supera el límite de 40 MB.")
            content.extend(chunk)
        return await asyncio.to_thread(
            app.state.library.upload, content, filename, title, author, document_id
        )

    @router.post("/api/library/{identifier}/process", dependencies=[Depends(authenticated)])
    def library_process(identifier: str):
        return {
            "job_id": app.state.jobs.start(
                "library", lambda job: app.state.library.process(identifier)
            )
        }

    @router.post("/api/library/{identifier}/enabled", dependencies=[Depends(authenticated)])
    def library_enabled(identifier: str, body: EnabledBody):
        return app.state.library.enable(identifier, body.enabled)

    @router.get("/api/library/{identifier}/preview", dependencies=[Depends(authenticated)])
    def library_preview(identifier: str):
        return app.state.library.preview(identifier)

    return router
