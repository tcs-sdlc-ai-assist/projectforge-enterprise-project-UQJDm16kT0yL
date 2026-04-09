import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from database import create_tables, get_db
from dependencies import get_session_user, get_flash_messages, clear_flash_messages
from models.user import User
from seed import seed_database

from routes.auth import router as auth_router
from routes.dashboard import router as dashboard_router
from routes.departments import router as departments_router
from routes.projects import router as projects_router
from routes.sprints import router as sprints_router
from routes.tickets import router as tickets_router
from routes.labels import router as labels_router
from routes.board import router as board_router
from routes.users import router as users_router
from routes.audit import router as audit_router

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ProjectForge application...")
    await create_tables()
    logger.info("Database tables created successfully")
    await seed_database()
    logger.info("Database seeding completed")
    yield
    logger.info("Shutting down ProjectForge application...")


app = FastAPI(
    title="ProjectForge",
    description="A comprehensive project management platform",
    version="1.0.0",
    lifespan=lifespan,
)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(departments_router)
app.include_router(projects_router)
app.include_router(sprints_router)
app.include_router(tickets_router)
app.include_router(labels_router)
app.include_router(board_router)
app.include_router(users_router)
app.include_router(audit_router)


@app.get("/")
async def landing_page(
    request: Request,
    user: Optional[User] = Depends(get_session_user),
):
    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "landing.html",
        context={
            "user": user,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        user = None
        try:
            from database import async_session
            async with async_session() as db:
                user = await get_session_user(request, db)
        except Exception:
            pass

        return templates.TemplateResponse(
            request,
            "errors/404.html",
            context={
                "user": user,
                "messages": [],
            },
            status_code=404,
        )

    if exc.status_code == 303:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=exc.headers.get("Location", "/auth/login"), status_code=303)

    return templates.TemplateResponse(
        request,
        "errors/404.html",
        context={
            "user": None,
            "messages": [{"text": str(exc.detail), "category": "error"}],
        },
        status_code=exc.status_code,
    )