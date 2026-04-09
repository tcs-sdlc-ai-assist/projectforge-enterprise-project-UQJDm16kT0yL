import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import require_login, require_role, get_session_user, set_flash_message, get_flash_messages, clear_flash_messages
from models.user import User
from models.project import Project
from models.label import Label
from models.ticket import ticket_labels
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

SUGGESTED_LABELS = [
    {"name": "bug", "color": "#dc2626"},
    {"name": "feature", "color": "#2563eb"},
    {"name": "enhancement", "color": "#7c3aed"},
    {"name": "documentation", "color": "#0891b2"},
    {"name": "design", "color": "#db2777"},
    {"name": "testing", "color": "#ea580c"},
    {"name": "refactor", "color": "#65a30d"},
    {"name": "performance", "color": "#ca8a04"},
    {"name": "security", "color": "#dc2626"},
    {"name": "infrastructure", "color": "#475569"},
    {"name": "accessibility", "color": "#0d9488"},
    {"name": "urgent", "color": "#b91c1c"},
    {"name": "good first issue", "color": "#16a34a"},
    {"name": "help wanted", "color": "#9333ea"},
    {"name": "wontfix", "color": "#6b7280"},
    {"name": "duplicate", "color": "#9ca3af"},
    {"name": "blocked", "color": "#ef4444"},
    {"name": "tech debt", "color": "#f59e0b"},
]


@router.get("/projects/{project_id}/labels")
async def list_labels(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_session_user),
):
    if user is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.labels))
    )
    project = result.scalars().first()

    if project is None:
        return RedirectResponse(url="/projects", status_code=303)

    result = await db.execute(
        select(Label)
        .where(Label.project_id == project_id)
        .options(selectinload(Label.tickets))
    )
    labels = result.scalars().all()

    labels_with_counts = []
    for label in labels:
        label.ticket_count = len(label.tickets) if label.tickets else 0
        labels_with_counts.append(label)

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "labels/list.html",
        context={
            "user": user,
            "project": project,
            "labels": labels_with_counts,
            "suggested_labels": SUGGESTED_LABELS,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/labels")
async def create_label(
    request: Request,
    project_id: str,
    name: str = Form(...),
    color: str = Form("#3b82f6"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()

    if project is None:
        return RedirectResponse(url="/projects", status_code=303)

    name = name.strip()
    if not name:
        response = RedirectResponse(
            url=f"/projects/{project_id}/labels",
            status_code=303,
        )
        set_flash_message(response, "Label name is required.", "error")
        return response

    if len(name) > 100:
        response = RedirectResponse(
            url=f"/projects/{project_id}/labels",
            status_code=303,
        )
        set_flash_message(response, "Label name must be 100 characters or less.", "error")
        return response

    result = await db.execute(
        select(Label)
        .where(Label.project_id == project_id)
        .where(func.lower(Label.name) == name.lower())
    )
    existing = result.scalars().first()

    if existing is not None:
        response = RedirectResponse(
            url=f"/projects/{project_id}/labels",
            status_code=303,
        )
        set_flash_message(response, f"A label named '{name}' already exists in this project.", "error")
        return response

    color = color.strip()
    if not color or len(color) != 7 or not color.startswith("#"):
        color = "#3b82f6"

    label = Label(
        name=name,
        color=color,
        project_id=project_id,
    )
    db.add(label)
    await db.flush()

    audit_log = AuditLog(
        entity_type="Label",
        entity_id=label.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({
            "name": name,
            "color": color,
            "project_id": project_id,
        }),
    )
    db.add(audit_log)
    await db.flush()

    logger.info("User %s created label '%s' in project %s", user.username, name, project_id)

    response = RedirectResponse(
        url=f"/projects/{project_id}/labels",
        status_code=303,
    )
    set_flash_message(response, f"Label '{name}' created successfully.", "success")
    return response


@router.get("/projects/{project_id}/labels/{label_id}/edit")
async def edit_label_form(
    request: Request,
    project_id: str,
    label_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()

    if project is None:
        return RedirectResponse(url="/projects", status_code=303)

    result = await db.execute(
        select(Label)
        .where(Label.id == label_id)
        .where(Label.project_id == project_id)
    )
    label = result.scalars().first()

    if label is None:
        response = RedirectResponse(
            url=f"/projects/{project_id}/labels",
            status_code=303,
        )
        set_flash_message(response, "Label not found.", "error")
        return response

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "labels/list.html",
        context={
            "user": user,
            "project": project,
            "labels": [],
            "suggested_labels": SUGGESTED_LABELS,
            "messages": messages,
            "edit_label": label,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/labels/{label_id}/delete")
async def delete_label(
    request: Request,
    project_id: str,
    label_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()

    if project is None:
        return RedirectResponse(url="/projects", status_code=303)

    result = await db.execute(
        select(Label)
        .where(Label.id == label_id)
        .where(Label.project_id == project_id)
    )
    label = result.scalars().first()

    if label is None:
        response = RedirectResponse(
            url=f"/projects/{project_id}/labels",
            status_code=303,
        )
        set_flash_message(response, "Label not found.", "error")
        return response

    label_name = label.name

    audit_log = AuditLog(
        entity_type="Label",
        entity_id=label.id,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({
            "name": label.name,
            "color": label.color,
            "project_id": project_id,
        }),
    )
    db.add(audit_log)
    await db.flush()

    await db.delete(label)
    await db.flush()

    logger.info("User %s deleted label '%s' from project %s", user.username, label_name, project_id)

    response = RedirectResponse(
        url=f"/projects/{project_id}/labels",
        status_code=303,
    )
    set_flash_message(response, f"Label '{label_name}' deleted successfully.", "success")
    return response