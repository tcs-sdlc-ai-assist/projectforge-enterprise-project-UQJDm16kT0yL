import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import (
    require_login,
    require_project_manager_or_above,
    get_session_user,
    set_flash_message,
    get_flash_messages,
    clear_flash_messages,
)
from models.user import User
from models.project import Project
from models.sprint import Sprint
from models.ticket import Ticket
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/projects/{project_id}/sprints")
async def list_sprints(
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
        .options(selectinload(Project.department))
    )
    project = result.scalars().first()
    if project is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    result = await db.execute(
        select(Sprint)
        .where(Sprint.project_id == project_id)
        .options(selectinload(Sprint.tickets))
        .order_by(Sprint.created_at.desc())
    )
    sprints = result.scalars().all()

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "sprints/list.html",
        context={
            "user": user,
            "project": project,
            "sprints": sprints,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.get("/projects/{project_id}/sprints/create")
async def create_sprint_form(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    if user.role not in ["Super Admin", "Project Manager"]:
        return RedirectResponse(url=f"/projects/{project_id}/sprints", status_code=303)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.department))
    )
    project = result.scalars().first()
    if project is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "sprints/form.html",
        context={
            "user": user,
            "project": project,
            "sprint": None,
            "form_data": None,
            "errors": None,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/sprints/create")
async def create_sprint(
    request: Request,
    project_id: str,
    name: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    if user.role not in ["Super Admin", "Project Manager"]:
        return RedirectResponse(url=f"/projects/{project_id}/sprints", status_code=303)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.department))
    )
    project = result.scalars().first()
    if project is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    errors = []
    form_data = {
        "name": name,
        "start_date": start_date,
        "end_date": end_date,
    }

    name = name.strip()
    if not name:
        errors.append("Sprint name is required.")
    if len(name) > 200:
        errors.append("Sprint name must be 200 characters or fewer.")

    parsed_start_date = None
    parsed_end_date = None

    if not start_date:
        errors.append("Start date is required.")
    else:
        try:
            parsed_start_date = date.fromisoformat(start_date)
        except ValueError:
            errors.append("Start date is invalid.")

    if not end_date:
        errors.append("End date is required.")
    else:
        try:
            parsed_end_date = date.fromisoformat(end_date)
        except ValueError:
            errors.append("End date is invalid.")

    if parsed_start_date and parsed_end_date and parsed_end_date <= parsed_start_date:
        errors.append("End date must be after the start date.")

    if errors:
        messages = get_flash_messages(request)
        response = templates.TemplateResponse(
            request,
            "sprints/form.html",
            context={
                "user": user,
                "project": project,
                "sprint": None,
                "form_data": form_data,
                "errors": errors,
                "messages": messages,
            },
        )
        clear_flash_messages(response)
        return response

    sprint = Sprint(
        name=name,
        project_id=project_id,
        status="Planning",
        start_date=parsed_start_date,
        end_date=parsed_end_date,
    )
    db.add(sprint)
    await db.flush()

    audit_log = AuditLog(
        entity_type="Sprint",
        entity_id=sprint.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({
            "name": name,
            "project_id": project_id,
            "start_date": start_date,
            "end_date": end_date,
        }),
    )
    db.add(audit_log)
    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}/sprints", status_code=303
    )
    set_flash_message(response, f"Sprint '{name}' created successfully.", "success")
    return response


@router.get("/projects/{project_id}/sprints/{sprint_id}")
async def sprint_detail(
    request: Request,
    project_id: str,
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_session_user),
):
    if user is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.department))
    )
    project = result.scalars().first()
    if project is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    result = await db.execute(
        select(Sprint)
        .where(Sprint.id == sprint_id)
        .where(Sprint.project_id == project_id)
        .options(
            selectinload(Sprint.tickets).selectinload(Ticket.assignee),
            selectinload(Sprint.tickets).selectinload(Ticket.labels),
        )
    )
    sprint = result.scalars().first()
    if sprint is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "sprints/list.html",
        context={
            "user": user,
            "project": project,
            "sprints": [sprint],
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.get("/projects/{project_id}/sprints/{sprint_id}/edit")
async def edit_sprint_form(
    request: Request,
    project_id: str,
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    if user.role not in ["Super Admin", "Project Manager"]:
        return RedirectResponse(url=f"/projects/{project_id}/sprints", status_code=303)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.department))
    )
    project = result.scalars().first()
    if project is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    result = await db.execute(
        select(Sprint)
        .where(Sprint.id == sprint_id)
        .where(Sprint.project_id == project_id)
        .options(selectinload(Sprint.tickets))
    )
    sprint = result.scalars().first()
    if sprint is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "sprints/form.html",
        context={
            "user": user,
            "project": project,
            "sprint": sprint,
            "form_data": None,
            "errors": None,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/sprints/{sprint_id}/edit")
async def edit_sprint(
    request: Request,
    project_id: str,
    sprint_id: str,
    name: str = Form(""),
    status: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    if user.role not in ["Super Admin", "Project Manager"]:
        return RedirectResponse(url=f"/projects/{project_id}/sprints", status_code=303)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.department))
    )
    project = result.scalars().first()
    if project is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    result = await db.execute(
        select(Sprint)
        .where(Sprint.id == sprint_id)
        .where(Sprint.project_id == project_id)
        .options(selectinload(Sprint.tickets))
    )
    sprint = result.scalars().first()
    if sprint is None:
        return templates.TemplateResponse(
            request, "errors/404.html", context={"user": user}, status_code=404
        )

    errors = []
    form_data = {
        "name": name,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
    }

    name = name.strip()
    if not name:
        errors.append("Sprint name is required.")
    if len(name) > 200:
        errors.append("Sprint name must be 200 characters or fewer.")

    valid_statuses = ["Planning", "Active", "Completed"]
    if status and status not in valid_statuses:
        errors.append(f"Status must be one of: {', '.join(valid_statuses)}.")

    parsed_start_date = None
    parsed_end_date = None

    if not start_date:
        errors.append("Start date is required.")
    else:
        try:
            parsed_start_date = date.fromisoformat(start_date)
        except ValueError:
            errors.append("Start date is invalid.")

    if not end_date:
        errors.append("End date is required.")
    else:
        try:
            parsed_end_date = date.fromisoformat(end_date)
        except ValueError:
            errors.append("End date is invalid.")

    if parsed_start_date and parsed_end_date and parsed_end_date <= parsed_start_date:
        errors.append("End date must be after the start date.")

    if status == "Active" and sprint.status != "Active":
        active_result = await db.execute(
            select(Sprint)
            .where(Sprint.project_id == project_id)
            .where(Sprint.status == "Active")
            .where(Sprint.id != sprint_id)
        )
        active_sprint = active_result.scalars().first()
        if active_sprint:
            errors.append(
                f"Cannot set status to Active. Sprint '{active_sprint.name}' is already active."
            )

    if errors:
        messages = get_flash_messages(request)
        response = templates.TemplateResponse(
            request,
            "sprints/form.html",
            context={
                "user": user,
                "project": project,
                "sprint": sprint,
                "form_data": form_data,
                "errors": errors,
                "messages": messages,
            },
        )
        clear_flash_messages(response)
        return response

    old_values = {
        "name": sprint.name,
        "status": sprint.status,
        "start_date": sprint.start_date.isoformat() if sprint.start_date else None,
        "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
    }

    sprint.name = name
    if status:
        sprint.status = status
    sprint.start_date = parsed_start_date
    sprint.end_date = parsed_end_date

    new_values = {
        "name": sprint.name,
        "status": sprint.status,
        "start_date": sprint.start_date.isoformat() if sprint.start_date else None,
        "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
    }

    audit_log = AuditLog(
        entity_type="Sprint",
        entity_id=sprint.id,
        action="UPDATE",
        user_id=user.id,
        details=json.dumps({"old": old_values, "new": new_values}),
    )
    db.add(audit_log)
    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}/sprints", status_code=303
    )
    set_flash_message(response, f"Sprint '{name}' updated successfully.", "success")
    return response


@router.post("/projects/{project_id}/sprints/{sprint_id}/start")
async def start_sprint(
    request: Request,
    project_id: str,
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    if user.role not in ["Super Admin", "Project Manager"]:
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(response, "You do not have permission to start sprints.", "error")
        return response

    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if project is None:
        response = RedirectResponse(url="/projects", status_code=303)
        set_flash_message(response, "Project not found.", "error")
        return response

    result = await db.execute(
        select(Sprint)
        .where(Sprint.id == sprint_id)
        .where(Sprint.project_id == project_id)
        .options(selectinload(Sprint.tickets))
    )
    sprint = result.scalars().first()
    if sprint is None:
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(response, "Sprint not found.", "error")
        return response

    if sprint.status != "Planning":
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(
            response,
            f"Sprint '{sprint.name}' cannot be started because it is in '{sprint.status}' status. Only sprints in 'Planning' status can be started.",
            "error",
        )
        return response

    active_result = await db.execute(
        select(Sprint)
        .where(Sprint.project_id == project_id)
        .where(Sprint.status == "Active")
    )
    active_sprint = active_result.scalars().first()
    if active_sprint:
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(
            response,
            f"Cannot start sprint '{sprint.name}'. Sprint '{active_sprint.name}' is already active. Complete it first.",
            "error",
        )
        return response

    old_status = sprint.status
    sprint.status = "Active"

    if not sprint.start_date:
        sprint.start_date = date.today()

    audit_log = AuditLog(
        entity_type="Sprint",
        entity_id=sprint.id,
        action="UPDATE",
        user_id=user.id,
        details=json.dumps({
            "action": "start_sprint",
            "old_status": old_status,
            "new_status": "Active",
        }),
    )
    db.add(audit_log)
    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}/sprints", status_code=303
    )
    set_flash_message(response, f"Sprint '{sprint.name}' is now active.", "success")
    return response


@router.post("/projects/{project_id}/sprints/{sprint_id}/complete")
async def complete_sprint(
    request: Request,
    project_id: str,
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    if user.role not in ["Super Admin", "Project Manager"]:
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(response, "You do not have permission to complete sprints.", "error")
        return response

    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if project is None:
        response = RedirectResponse(url="/projects", status_code=303)
        set_flash_message(response, "Project not found.", "error")
        return response

    result = await db.execute(
        select(Sprint)
        .where(Sprint.id == sprint_id)
        .where(Sprint.project_id == project_id)
        .options(selectinload(Sprint.tickets))
    )
    sprint = result.scalars().first()
    if sprint is None:
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(response, "Sprint not found.", "error")
        return response

    if sprint.status != "Active":
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(
            response,
            f"Sprint '{sprint.name}' cannot be completed because it is in '{sprint.status}' status. Only active sprints can be completed.",
            "error",
        )
        return response

    old_status = sprint.status
    sprint.status = "Completed"

    if not sprint.end_date:
        sprint.end_date = date.today()

    audit_log = AuditLog(
        entity_type="Sprint",
        entity_id=sprint.id,
        action="UPDATE",
        user_id=user.id,
        details=json.dumps({
            "action": "complete_sprint",
            "old_status": old_status,
            "new_status": "Completed",
        }),
    )
    db.add(audit_log)
    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}/sprints", status_code=303
    )
    set_flash_message(response, f"Sprint '{sprint.name}' has been completed.", "success")
    return response


@router.post("/projects/{project_id}/sprints/{sprint_id}/delete")
async def delete_sprint(
    request: Request,
    project_id: str,
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    if user.role not in ["Super Admin", "Project Manager"]:
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(response, "You do not have permission to delete sprints.", "error")
        return response

    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if project is None:
        response = RedirectResponse(url="/projects", status_code=303)
        set_flash_message(response, "Project not found.", "error")
        return response

    result = await db.execute(
        select(Sprint)
        .where(Sprint.id == sprint_id)
        .where(Sprint.project_id == project_id)
        .options(selectinload(Sprint.tickets))
    )
    sprint = result.scalars().first()
    if sprint is None:
        response = RedirectResponse(
            url=f"/projects/{project_id}/sprints", status_code=303
        )
        set_flash_message(response, "Sprint not found.", "error")
        return response

    sprint_name = sprint.name

    # Unassign tickets from this sprint before deleting
    if sprint.tickets:
        for ticket in sprint.tickets:
            ticket.sprint_id = None

    audit_log = AuditLog(
        entity_type="Sprint",
        entity_id=sprint.id,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({
            "name": sprint_name,
            "project_id": project_id,
            "status": sprint.status,
        }),
    )
    db.add(audit_log)
    await db.flush()

    await db.delete(sprint)
    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}/sprints", status_code=303
    )
    set_flash_message(response, f"Sprint '{sprint_name}' has been deleted.", "success")
    return response