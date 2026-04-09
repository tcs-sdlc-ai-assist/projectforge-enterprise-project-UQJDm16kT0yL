import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import logging
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import (
    get_session_user,
    require_login,
    require_role,
    set_flash_message,
    get_flash_messages,
    clear_flash_messages,
)
from models.user import User
from models.project import Project, ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket, ticket_labels
from models.label import Label
from models.comment import Comment
from models.time_entry import TimeEntry
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


async def _get_project_or_404(project_id: str, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.sprints),
            selectinload(Project.labels),
            selectinload(Project.project_members).selectinload(ProjectMember.user),
        )
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _get_ticket_or_404(ticket_id: str, db: AsyncSession) -> Ticket:
    result = await db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.project).selectinload(Project.department),
            selectinload(Ticket.sprint),
            selectinload(Ticket.assignee),
            selectinload(Ticket.reporter),
            selectinload(Ticket.labels),
            selectinload(Ticket.comments).selectinload(Comment.user),
            selectinload(Ticket.comments).selectinload(Comment.replies).selectinload(Comment.user),
            selectinload(Ticket.time_entries).selectinload(TimeEntry.user),
            selectinload(Ticket.parent),
            selectinload(Ticket.children),
        )
    )
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


async def _create_audit_log(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    action: str,
    user_id: str,
    details: Optional[str] = None,
) -> None:
    audit = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        details=details,
    )
    db.add(audit)


async def _get_project_members_as_users(project: Project, db: AsyncSession) -> list:
    user_ids = [pm.user_id for pm in project.project_members if pm.user_id]
    if not user_ids:
        return []
    result = await db.execute(
        select(User).where(User.id.in_(user_ids)).where(User.is_active == True)
    )
    return list(result.scalars().all())


# ─── Ticket List ───────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/tickets")
async def list_tickets(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    ticket_type: Optional[str] = None,
    priority: Optional[str] = None,
    assignee_id: Optional[str] = None,
    sprint_id: Optional[str] = None,
    label_id: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = 1,
):
    project = await _get_project_or_404(project_id, db)

    # Read status from query param named "status"
    status_val = request.query_params.get("status", status_filter or "")
    ticket_type_val = request.query_params.get("ticket_type", ticket_type or "")
    priority_val = request.query_params.get("priority", priority or "")
    assignee_id_val = request.query_params.get("assignee_id", assignee_id or "")
    sprint_id_val = request.query_params.get("sprint_id", sprint_id or "")
    label_id_val = request.query_params.get("label_id", label_id or "")
    search_val = request.query_params.get("search", search or "")
    sort_val = request.query_params.get("sort", sort or "created_desc")
    page_val = int(request.query_params.get("page", page))

    query = select(Ticket).where(Ticket.project_id == project_id).options(
        selectinload(Ticket.project),
        selectinload(Ticket.sprint),
        selectinload(Ticket.assignee),
        selectinload(Ticket.reporter),
        selectinload(Ticket.labels),
    )

    if search_val:
        query = query.where(
            or_(
                Ticket.title.ilike(f"%{search_val}%"),
                Ticket.description.ilike(f"%{search_val}%"),
            )
        )

    if status_val:
        query = query.where(Ticket.status == status_val)

    if ticket_type_val:
        query = query.where(
            or_(Ticket.type == ticket_type_val, Ticket.ticket_type == ticket_type_val)
        )

    if priority_val:
        query = query.where(Ticket.priority == priority_val)

    if assignee_id_val:
        query = query.where(Ticket.assignee_id == assignee_id_val)

    if sprint_id_val:
        query = query.where(Ticket.sprint_id == sprint_id_val)

    if label_id_val:
        query = query.join(ticket_labels).where(ticket_labels.c.label_id == label_id_val)

    # Sorting
    if sort_val == "created_asc":
        query = query.order_by(Ticket.created_at.asc())
    elif sort_val == "priority_desc":
        query = query.order_by(Ticket.priority.desc())
    elif sort_val == "priority_asc":
        query = query.order_by(Ticket.priority.asc())
    elif sort_val == "due_date_asc":
        query = query.order_by(Ticket.due_date.asc().nullslast())
    elif sort_val == "title_asc":
        query = query.order_by(Ticket.title.asc())
    else:
        query = query.order_by(Ticket.created_at.desc())

    # Count
    count_query = select(func.count()).select_from(
        select(Ticket.id).where(Ticket.project_id == project_id)
    )
    if search_val:
        count_query = select(func.count()).select_from(
            select(Ticket.id).where(Ticket.project_id == project_id).where(
                or_(
                    Ticket.title.ilike(f"%{search_val}%"),
                    Ticket.description.ilike(f"%{search_val}%"),
                )
            )
        )
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    page_size = 25
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    offset = (page_val - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    tickets = list(result.scalars().unique().all())

    # Set ticket_type for template compatibility
    for t in tickets:
        if not t.ticket_type:
            t.ticket_type = t.type

    # Get assignees and sprints for filter dropdowns
    members = await _get_project_members_as_users(project, db)

    sprints_result = await db.execute(
        select(Sprint).where(Sprint.project_id == project_id).order_by(Sprint.created_at.desc())
    )
    sprints = list(sprints_result.scalars().all())

    labels_result = await db.execute(
        select(Label).where(Label.project_id == project_id).order_by(Label.name)
    )
    labels = list(labels_result.scalars().all())

    filters = {
        "search": search_val,
        "status": status_val,
        "ticket_type": ticket_type_val,
        "priority": priority_val,
        "assignee_id": assignee_id_val,
        "sprint_id": sprint_id_val,
        "label_id": label_id_val,
        "sort": sort_val,
    }

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "tickets/list.html",
        context={
            "user": user,
            "project": project,
            "tickets": tickets,
            "filters": filters,
            "assignees": members,
            "sprints": sprints,
            "labels": labels,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": page_val,
            "page_size": page_size,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


# ─── Ticket Create ─────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/tickets/create")
async def create_ticket_form(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
):
    project = await _get_project_or_404(project_id, db)
    members = await _get_project_members_as_users(project, db)

    sprints_result = await db.execute(
        select(Sprint).where(Sprint.project_id == project_id).order_by(Sprint.created_at.desc())
    )
    sprints = list(sprints_result.scalars().all())

    labels_result = await db.execute(
        select(Label).where(Label.project_id == project_id).order_by(Label.name)
    )
    labels = list(labels_result.scalars().all())

    # Parent tickets for subtask linking
    parent_result = await db.execute(
        select(Ticket).where(Ticket.project_id == project_id).order_by(Ticket.title)
    )
    parent_tickets = list(parent_result.scalars().all())

    projects_result = await db.execute(select(Project).order_by(Project.name))
    projects = list(projects_result.scalars().all())

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "tickets/form.html",
        context={
            "user": user,
            "project": project,
            "projects": projects,
            "members": members,
            "sprints": sprints,
            "labels": labels,
            "parent_tickets": parent_tickets,
            "edit_mode": False,
            "ticket": None,
            "form_data": None,
            "errors": None,
            "field_errors": None,
            "ticket_label_ids": [],
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/tickets/create")
async def create_ticket(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    title: str = Form(""),
    description: str = Form(""),
    type: str = Form("Task"),
    priority: str = Form("Medium"),
    assignee_id: str = Form(""),
    sprint_id: str = Form(""),
    parent_id: str = Form(""),
    due_date: str = Form(""),
    project_id_form: str = Form("", alias="project_id"),
):
    project = await _get_project_or_404(project_id, db)

    form = await request.form()
    label_ids = form.getlist("label_ids")

    errors = []
    if not title.strip():
        errors.append("Title is required.")
    if not type.strip():
        errors.append("Type is required.")
    if not priority.strip():
        errors.append("Priority is required.")

    form_data = {
        "title": title,
        "description": description,
        "type": type,
        "priority": priority,
        "assignee_id": assignee_id,
        "sprint_id": sprint_id,
        "parent_id": parent_id,
        "due_date": due_date,
        "project_id": project_id,
        "label_ids": label_ids,
    }

    if errors:
        members = await _get_project_members_as_users(project, db)
        sprints_result = await db.execute(
            select(Sprint).where(Sprint.project_id == project_id)
        )
        sprints = list(sprints_result.scalars().all())
        labels_result = await db.execute(
            select(Label).where(Label.project_id == project_id)
        )
        labels = list(labels_result.scalars().all())
        parent_result = await db.execute(
            select(Ticket).where(Ticket.project_id == project_id)
        )
        parent_tickets = list(parent_result.scalars().all())
        projects_result = await db.execute(select(Project).order_by(Project.name))
        projects = list(projects_result.scalars().all())

        return templates.TemplateResponse(
            request,
            "tickets/form.html",
            context={
                "user": user,
                "project": project,
                "projects": projects,
                "members": members,
                "sprints": sprints,
                "labels": labels,
                "parent_tickets": parent_tickets,
                "edit_mode": False,
                "ticket": None,
                "form_data": form_data,
                "errors": errors,
                "field_errors": None,
                "ticket_label_ids": label_ids,
                "messages": [],
            },
        )

    # Generate ticket key
    ticket_count_result = await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.project_id == project_id)
    )
    ticket_count = (ticket_count_result.scalar() or 0) + 1
    ticket_key = f"{project.key}-{ticket_count}"

    parsed_due_date = None
    if due_date.strip():
        try:
            parsed_due_date = date.fromisoformat(due_date.strip())
        except ValueError:
            pass

    ticket = Ticket(
        title=title.strip(),
        description=description.strip() if description.strip() else None,
        project_id=project_id,
        ticket_key=ticket_key,
        type=type,
        ticket_type=type,
        priority=priority,
        status="Open",
        assignee_id=assignee_id if assignee_id else None,
        reporter_id=user.id,
        sprint_id=sprint_id if sprint_id else None,
        parent_id=parent_id if parent_id else None,
        due_date=parsed_due_date,
    )
    db.add(ticket)
    await db.flush()

    # Assign labels
    if label_ids:
        for lid in label_ids:
            if lid:
                await db.execute(
                    ticket_labels.insert().values(ticket_id=ticket.id, label_id=lid)
                )

    await _create_audit_log(
        db,
        entity_type="Ticket",
        entity_id=ticket.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({"title": ticket.title, "type": type, "priority": priority}),
    )

    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Ticket created successfully.", "success")
    return response


# ─── Ticket Detail ─────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/tickets/{ticket_id}")
async def ticket_detail(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    ticket = await _get_ticket_or_404(ticket_id, db)

    if ticket.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found in this project")

    # Get top-level comments only (parent_id is None)
    top_level_comments = [c for c in (ticket.comments or []) if c.parent_id is None]

    # Get subtasks
    subtasks_result = await db.execute(
        select(Ticket)
        .where(Ticket.parent_id == ticket_id)
        .options(selectinload(Ticket.assignee))
        .order_by(Ticket.created_at.asc())
    )
    subtasks = list(subtasks_result.scalars().all())

    # Calculate total hours
    total_hours = sum(te.hours for te in (ticket.time_entries or []))

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "tickets/detail.html",
        context={
            "user": user,
            "ticket": ticket,
            "comments": top_level_comments,
            "time_entries": ticket.time_entries or [],
            "subtasks": subtasks,
            "total_hours": total_hours,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


# ─── Ticket Detail (shortcut without project prefix) ──────────────────────────

@router.get("/tickets/{ticket_id}")
async def ticket_detail_shortcut(
    request: Request,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    ticket = await _get_ticket_or_404(ticket_id, db)
    return RedirectResponse(
        url=f"/projects/{ticket.project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ─── Ticket Edit ───────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/tickets/{ticket_id}/edit")
async def edit_ticket_form(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
):
    project = await _get_project_or_404(project_id, db)
    ticket = await _get_ticket_or_404(ticket_id, db)

    if ticket.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found in this project")

    members = await _get_project_members_as_users(project, db)

    sprints_result = await db.execute(
        select(Sprint).where(Sprint.project_id == project_id).order_by(Sprint.created_at.desc())
    )
    sprints = list(sprints_result.scalars().all())

    labels_result = await db.execute(
        select(Label).where(Label.project_id == project_id).order_by(Label.name)
    )
    labels = list(labels_result.scalars().all())

    parent_result = await db.execute(
        select(Ticket)
        .where(Ticket.project_id == project_id)
        .where(Ticket.id != ticket_id)
        .order_by(Ticket.title)
    )
    parent_tickets = list(parent_result.scalars().all())

    ticket_label_ids = [l.id for l in (ticket.labels or [])]

    projects_result = await db.execute(select(Project).order_by(Project.name))
    projects = list(projects_result.scalars().all())

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "tickets/form.html",
        context={
            "user": user,
            "project": project,
            "projects": projects,
            "ticket": ticket,
            "members": members,
            "sprints": sprints,
            "labels": labels,
            "parent_tickets": parent_tickets,
            "edit_mode": True,
            "form_data": None,
            "errors": None,
            "field_errors": None,
            "ticket_label_ids": ticket_label_ids,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.get("/tickets/{ticket_id}/edit")
async def edit_ticket_form_shortcut(
    request: Request,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
):
    ticket = await _get_ticket_or_404(ticket_id, db)
    return RedirectResponse(
        url=f"/projects/{ticket.project_id}/tickets/{ticket_id}/edit",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/projects/{project_id}/tickets/{ticket_id}/edit")
async def edit_ticket(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    title: str = Form(""),
    description: str = Form(""),
    type: str = Form("Task"),
    priority: str = Form("Medium"),
    status_field: str = Form("Open", alias="status"),
    assignee_id: str = Form(""),
    sprint_id: str = Form(""),
    parent_id: str = Form(""),
    due_date: str = Form(""),
):
    project = await _get_project_or_404(project_id, db)
    ticket = await _get_ticket_or_404(ticket_id, db)

    if ticket.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found in this project")

    form = await request.form()
    label_ids = form.getlist("label_ids")
    status_val = form.get("status", status_field)

    errors = []
    if not title.strip():
        errors.append("Title is required.")

    form_data = {
        "title": title,
        "description": description,
        "type": type,
        "priority": priority,
        "status": status_val,
        "assignee_id": assignee_id,
        "sprint_id": sprint_id,
        "parent_id": parent_id,
        "due_date": due_date,
        "label_ids": label_ids,
    }

    if errors:
        members = await _get_project_members_as_users(project, db)
        sprints_result = await db.execute(
            select(Sprint).where(Sprint.project_id == project_id)
        )
        sprints = list(sprints_result.scalars().all())
        labels_result = await db.execute(
            select(Label).where(Label.project_id == project_id)
        )
        labels = list(labels_result.scalars().all())
        parent_result = await db.execute(
            select(Ticket).where(Ticket.project_id == project_id).where(Ticket.id != ticket_id)
        )
        parent_tickets = list(parent_result.scalars().all())
        projects_result = await db.execute(select(Project).order_by(Project.name))
        projects = list(projects_result.scalars().all())

        return templates.TemplateResponse(
            request,
            "tickets/form.html",
            context={
                "user": user,
                "project": project,
                "projects": projects,
                "ticket": ticket,
                "members": members,
                "sprints": sprints,
                "labels": labels,
                "parent_tickets": parent_tickets,
                "edit_mode": True,
                "form_data": form_data,
                "errors": errors,
                "field_errors": None,
                "ticket_label_ids": label_ids,
                "messages": [],
            },
        )

    old_values = {
        "title": ticket.title,
        "status": ticket.status,
        "type": ticket.type,
        "priority": ticket.priority,
        "assignee_id": ticket.assignee_id,
        "sprint_id": ticket.sprint_id,
    }

    ticket.title = title.strip()
    ticket.description = description.strip() if description.strip() else None
    ticket.type = type
    ticket.ticket_type = type
    ticket.priority = priority
    ticket.status = status_val
    ticket.assignee_id = assignee_id if assignee_id else None
    ticket.sprint_id = sprint_id if sprint_id else None
    ticket.parent_id = parent_id if parent_id else None

    parsed_due_date = None
    if due_date.strip():
        try:
            parsed_due_date = date.fromisoformat(due_date.strip())
        except ValueError:
            pass
    ticket.due_date = parsed_due_date

    if status_val == "Closed" and ticket.closed_date is None:
        ticket.closed_date = date.today()
    elif status_val != "Closed":
        ticket.closed_date = None

    # Update labels
    await db.execute(
        ticket_labels.delete().where(ticket_labels.c.ticket_id == ticket_id)
    )
    if label_ids:
        for lid in label_ids:
            if lid:
                await db.execute(
                    ticket_labels.insert().values(ticket_id=ticket.id, label_id=lid)
                )

    new_values = {
        "title": ticket.title,
        "status": ticket.status,
        "type": ticket.type,
        "priority": ticket.priority,
        "assignee_id": ticket.assignee_id,
        "sprint_id": ticket.sprint_id,
    }

    await _create_audit_log(
        db,
        entity_type="Ticket",
        entity_id=ticket.id,
        action="UPDATE",
        user_id=user.id,
        details=json.dumps({"old": old_values, "new": new_values}),
    )

    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Ticket updated successfully.", "success")
    return response


@router.post("/tickets/{ticket_id}/edit")
async def edit_ticket_shortcut(
    request: Request,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
):
    ticket = await _get_ticket_or_404(ticket_id, db)
    # Re-read form and forward
    form = await request.form()
    title = form.get("title", "")
    description = form.get("description", "")
    type_val = form.get("type", "Task")
    priority = form.get("priority", "Medium")
    status_val = form.get("status", "Open")
    assignee_id = form.get("assignee_id", "")
    sprint_id = form.get("sprint_id", "")
    parent_id = form.get("parent_id", "")
    due_date = form.get("due_date", "")
    label_ids = form.getlist("label_ids")

    project = await _get_project_or_404(ticket.project_id, db)

    errors = []
    if not str(title).strip():
        errors.append("Title is required.")

    if errors:
        members = await _get_project_members_as_users(project, db)
        sprints_result = await db.execute(select(Sprint).where(Sprint.project_id == ticket.project_id))
        sprints = list(sprints_result.scalars().all())
        labels_result = await db.execute(select(Label).where(Label.project_id == ticket.project_id))
        labels = list(labels_result.scalars().all())
        parent_result = await db.execute(
            select(Ticket).where(Ticket.project_id == ticket.project_id).where(Ticket.id != ticket_id)
        )
        parent_tickets = list(parent_result.scalars().all())
        projects_result = await db.execute(select(Project).order_by(Project.name))
        projects = list(projects_result.scalars().all())

        form_data = {
            "title": title, "description": description, "type": type_val,
            "priority": priority, "status": status_val, "assignee_id": assignee_id,
            "sprint_id": sprint_id, "parent_id": parent_id, "due_date": due_date,
            "label_ids": label_ids,
        }

        return templates.TemplateResponse(
            request,
            "tickets/form.html",
            context={
                "user": user, "project": project, "projects": projects,
                "ticket": ticket, "members": members, "sprints": sprints,
                "labels": labels, "parent_tickets": parent_tickets,
                "edit_mode": True, "form_data": form_data, "errors": errors,
                "field_errors": None, "ticket_label_ids": label_ids, "messages": [],
            },
        )

    old_values = {"title": ticket.title, "status": ticket.status, "type": ticket.type, "priority": ticket.priority}

    ticket.title = str(title).strip()
    ticket.description = str(description).strip() if str(description).strip() else None
    ticket.type = str(type_val)
    ticket.ticket_type = str(type_val)
    ticket.priority = str(priority)
    ticket.status = str(status_val)
    ticket.assignee_id = str(assignee_id) if assignee_id else None
    ticket.sprint_id = str(sprint_id) if sprint_id else None
    ticket.parent_id = str(parent_id) if parent_id else None

    parsed_due_date = None
    if str(due_date).strip():
        try:
            parsed_due_date = date.fromisoformat(str(due_date).strip())
        except ValueError:
            pass
    ticket.due_date = parsed_due_date

    if str(status_val) == "Closed" and ticket.closed_date is None:
        ticket.closed_date = date.today()
    elif str(status_val) != "Closed":
        ticket.closed_date = None

    await db.execute(ticket_labels.delete().where(ticket_labels.c.ticket_id == ticket_id))
    if label_ids:
        for lid in label_ids:
            if lid:
                await db.execute(ticket_labels.insert().values(ticket_id=ticket.id, label_id=lid))

    await _create_audit_log(
        db, entity_type="Ticket", entity_id=ticket.id, action="UPDATE",
        user_id=user.id, details=json.dumps({"old": old_values, "new": {"title": ticket.title, "status": ticket.status}}),
    )
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{ticket.project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Ticket updated successfully.", "success")
    return response


# ─── Ticket Delete ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/tickets/{ticket_id}/delete")
async def delete_ticket(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager"])),
):
    ticket = await _get_ticket_or_404(ticket_id, db)

    if ticket.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found in this project")

    await _create_audit_log(
        db,
        entity_type="Ticket",
        entity_id=ticket.id,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({"title": ticket.title}),
    )

    # Remove label associations
    await db.execute(
        ticket_labels.delete().where(ticket_labels.c.ticket_id == ticket_id)
    )

    # Unlink subtasks
    subtasks_result = await db.execute(
        select(Ticket).where(Ticket.parent_id == ticket_id)
    )
    for subtask in subtasks_result.scalars().all():
        subtask.parent_id = None

    await db.delete(ticket)
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Ticket deleted successfully.", "success")
    return response


@router.post("/tickets/{ticket_id}/delete")
async def delete_ticket_shortcut(
    request: Request,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager"])),
):
    ticket = await _get_ticket_or_404(ticket_id, db)
    project_id = ticket.project_id

    await _create_audit_log(
        db, entity_type="Ticket", entity_id=ticket.id, action="DELETE",
        user_id=user.id, details=json.dumps({"title": ticket.title}),
    )
    await db.execute(ticket_labels.delete().where(ticket_labels.c.ticket_id == ticket_id))
    subtasks_result = await db.execute(select(Ticket).where(Ticket.parent_id == ticket_id))
    for subtask in subtasks_result.scalars().all():
        subtask.parent_id = None
    await db.delete(ticket)
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Ticket deleted successfully.", "success")
    return response


# ─── Ticket Status Change ─────────────────────────────────────────────────────

@router.post("/projects/{project_id}/tickets/{ticket_id}/status")
async def change_ticket_status(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    status_field: str = Form("", alias="status"),
):
    form = await request.form()
    new_status = form.get("status", status_field)

    if not new_status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status is required")

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id).where(Ticket.project_id == project_id)
    )
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    old_status = ticket.status
    ticket.status = new_status

    if new_status == "Closed" and ticket.closed_date is None:
        ticket.closed_date = date.today()
    elif new_status != "Closed":
        ticket.closed_date = None

    await _create_audit_log(
        db,
        entity_type="Ticket",
        entity_id=ticket.id,
        action="UPDATE",
        user_id=user.id,
        details=json.dumps({"field": "status", "old": old_status, "new": new_status}),
    )

    await db.commit()

    # Check if this is an AJAX-style request (from Kanban board)
    accept = request.headers.get("accept", "")
    if "text/html" not in accept and "application/x-www-form-urlencoded" not in str(request.headers.get("content-type", "")):
        return Response(status_code=200)

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"Ticket status changed to {new_status}.", "success")
    return response


# ─── Comments ──────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/tickets/{ticket_id}/comments")
async def add_comment(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    content: str = Form(""),
    parent_id: str = Form(""),
    is_internal: str = Form(""),
):
    if not content.strip():
        response = RedirectResponse(
            url=f"/projects/{project_id}/tickets/{ticket_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, "Comment content is required.", "error")
        return response

    # Verify ticket exists in project
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id).where(Ticket.project_id == project_id)
    )
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    comment = Comment(
        content=content.strip(),
        ticket_id=ticket_id,
        user_id=user.id,
        parent_id=parent_id if parent_id else None,
        is_internal=is_internal in ("true", "on", "1", "True"),
    )
    db.add(comment)

    await _create_audit_log(
        db,
        entity_type="Comment",
        entity_id=comment.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({"ticket_id": ticket_id, "is_reply": bool(parent_id)}),
    )

    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket_id}#comment-{comment.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Comment added successfully.", "success")
    return response


@router.post("/tickets/{ticket_id}/comments")
async def add_comment_shortcut(
    request: Request,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    content: str = Form(""),
    parent_id: str = Form(""),
    is_internal: str = Form(""),
):
    ticket = await _get_ticket_or_404(ticket_id, db)

    if not content.strip():
        response = RedirectResponse(
            url=f"/projects/{ticket.project_id}/tickets/{ticket_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, "Comment content is required.", "error")
        return response

    comment = Comment(
        content=content.strip(),
        ticket_id=ticket_id,
        user_id=user.id,
        parent_id=parent_id if parent_id else None,
        is_internal=is_internal in ("true", "on", "1", "True"),
    )
    db.add(comment)

    await _create_audit_log(
        db, entity_type="Comment", entity_id=comment.id, action="CREATE",
        user_id=user.id, details=json.dumps({"ticket_id": ticket_id}),
    )
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{ticket.project_id}/tickets/{ticket_id}#comment-{comment.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Comment added successfully.", "success")
    return response


@router.post("/projects/{project_id}/tickets/{ticket_id}/comments/{comment_id}/delete")
async def delete_comment(
    request: Request,
    project_id: str,
    ticket_id: str,
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    result = await db.execute(
        select(Comment)
        .where(Comment.id == comment_id)
        .where(Comment.ticket_id == ticket_id)
        .options(selectinload(Comment.replies))
    )
    comment = result.scalars().first()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # Only comment owner, Super Admin, or Project Manager can delete
    if comment.user_id != user.id and user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot delete this comment")

    # Delete replies first
    if comment.replies:
        for reply in comment.replies:
            await db.delete(reply)

    await _create_audit_log(
        db,
        entity_type="Comment",
        entity_id=comment.id,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({"ticket_id": ticket_id}),
    )

    await db.delete(comment)
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Comment deleted.", "success")
    return response


@router.post("/tickets/{ticket_id}/comments/{comment_id}/delete")
async def delete_comment_shortcut(
    request: Request,
    ticket_id: str,
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    ticket = await _get_ticket_or_404(ticket_id, db)

    result = await db.execute(
        select(Comment)
        .where(Comment.id == comment_id)
        .where(Comment.ticket_id == ticket_id)
        .options(selectinload(Comment.replies))
    )
    comment = result.scalars().first()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    if comment.user_id != user.id and user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot delete this comment")

    if comment.replies:
        for reply in comment.replies:
            await db.delete(reply)

    await _create_audit_log(
        db, entity_type="Comment", entity_id=comment.id, action="DELETE",
        user_id=user.id, details=json.dumps({"ticket_id": ticket_id}),
    )
    await db.delete(comment)
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{ticket.project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Comment deleted.", "success")
    return response


# ─── Time Entries ──────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/tickets/{ticket_id}/time-entries")
async def add_time_entry(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    hours: str = Form(""),
    description: str = Form(""),
    entry_date: str = Form(""),
):
    # Verify ticket exists in project
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id).where(Ticket.project_id == project_id)
    )
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    errors = []
    parsed_hours = 0.0
    try:
        parsed_hours = float(hours)
        if parsed_hours <= 0:
            errors.append("Hours must be greater than 0.")
    except (ValueError, TypeError):
        errors.append("Valid hours value is required.")

    parsed_date = date.today()
    if entry_date.strip():
        try:
            parsed_date = date.fromisoformat(entry_date.strip())
        except ValueError:
            errors.append("Invalid date format.")
    else:
        errors.append("Date is required.")

    if errors:
        response = RedirectResponse(
            url=f"/projects/{project_id}/tickets/{ticket_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, " ".join(errors), "error")
        return response

    time_entry = TimeEntry(
        ticket_id=ticket_id,
        user_id=user.id,
        hours=parsed_hours,
        description=description.strip() if description.strip() else None,
        logged_date=parsed_date,
    )
    db.add(time_entry)

    await _create_audit_log(
        db,
        entity_type="TimeEntry",
        entity_id=time_entry.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({"ticket_id": ticket_id, "hours": parsed_hours}),
    )

    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"Logged {parsed_hours}h successfully.", "success")
    return response


@router.post("/tickets/{ticket_id}/time-entries")
async def add_time_entry_shortcut(
    request: Request,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    hours: str = Form(""),
    description: str = Form(""),
    entry_date: str = Form(""),
):
    ticket = await _get_ticket_or_404(ticket_id, db)

    errors = []
    parsed_hours = 0.0
    try:
        parsed_hours = float(hours)
        if parsed_hours <= 0:
            errors.append("Hours must be greater than 0.")
    except (ValueError, TypeError):
        errors.append("Valid hours value is required.")

    parsed_date = date.today()
    if entry_date.strip():
        try:
            parsed_date = date.fromisoformat(entry_date.strip())
        except ValueError:
            errors.append("Invalid date format.")
    else:
        errors.append("Date is required.")

    if errors:
        response = RedirectResponse(
            url=f"/projects/{ticket.project_id}/tickets/{ticket_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, " ".join(errors), "error")
        return response

    time_entry = TimeEntry(
        ticket_id=ticket_id,
        user_id=user.id,
        hours=parsed_hours,
        description=description.strip() if description.strip() else None,
        logged_date=parsed_date,
    )
    db.add(time_entry)

    await _create_audit_log(
        db, entity_type="TimeEntry", entity_id=time_entry.id, action="CREATE",
        user_id=user.id, details=json.dumps({"ticket_id": ticket_id, "hours": parsed_hours}),
    )
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{ticket.project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"Logged {parsed_hours}h successfully.", "success")
    return response


@router.post("/projects/{project_id}/tickets/{ticket_id}/time-entries/{entry_id}/delete")
async def delete_time_entry(
    request: Request,
    project_id: str,
    ticket_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    result = await db.execute(
        select(TimeEntry)
        .where(TimeEntry.id == entry_id)
        .where(TimeEntry.ticket_id == ticket_id)
    )
    entry = result.scalars().first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found")

    # Only entry owner, Super Admin, or Project Manager can delete
    if entry.user_id != user.id and user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot delete this time entry")

    await _create_audit_log(
        db,
        entity_type="TimeEntry",
        entity_id=entry.id,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({"ticket_id": ticket_id, "hours": entry.hours}),
    )

    await db.delete(entry)
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Time entry deleted.", "success")
    return response


@router.post("/tickets/{ticket_id}/time-entries/{entry_id}/delete")
async def delete_time_entry_shortcut(
    request: Request,
    ticket_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    ticket = await _get_ticket_or_404(ticket_id, db)

    result = await db.execute(
        select(TimeEntry)
        .where(TimeEntry.id == entry_id)
        .where(TimeEntry.ticket_id == ticket_id)
    )
    entry = result.scalars().first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found")

    if entry.user_id != user.id and user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot delete this time entry")

    await _create_audit_log(
        db, entity_type="TimeEntry", entity_id=entry.id, action="DELETE",
        user_id=user.id, details=json.dumps({"ticket_id": ticket_id, "hours": entry.hours}),
    )
    await db.delete(entry)
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{ticket.project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Time entry deleted.", "success")
    return response


# ─── Global ticket list (all projects) ─────────────────────────────────────────

@router.get("/tickets")
async def global_ticket_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_login),
):
    project_id = request.query_params.get("project_id", "")
    search_val = request.query_params.get("search", "")
    status_val = request.query_params.get("status", "")
    ticket_type_val = request.query_params.get("ticket_type", "")
    priority_val = request.query_params.get("priority", "")
    assignee_id_val = request.query_params.get("assignee_id", "")
    sprint_id_val = request.query_params.get("sprint_id", "")
    label_id_val = request.query_params.get("label_id", "")
    sort_val = request.query_params.get("sort", "created_desc")
    page_val = int(request.query_params.get("page", "1"))

    project = None
    if project_id:
        proj_result = await db.execute(
            select(Project).where(Project.id == project_id).options(
                selectinload(Project.sprints),
                selectinload(Project.labels),
                selectinload(Project.project_members).selectinload(ProjectMember.user),
            )
        )
        project = proj_result.scalars().first()

    query = select(Ticket).options(
        selectinload(Ticket.project),
        selectinload(Ticket.sprint),
        selectinload(Ticket.assignee),
        selectinload(Ticket.reporter),
        selectinload(Ticket.labels),
    )

    if project_id:
        query = query.where(Ticket.project_id == project_id)

    if search_val:
        query = query.where(
            or_(Ticket.title.ilike(f"%{search_val}%"), Ticket.description.ilike(f"%{search_val}%"))
        )
    if status_val:
        query = query.where(Ticket.status == status_val)
    if ticket_type_val:
        query = query.where(or_(Ticket.type == ticket_type_val, Ticket.ticket_type == ticket_type_val))
    if priority_val:
        query = query.where(Ticket.priority == priority_val)
    if assignee_id_val:
        query = query.where(Ticket.assignee_id == assignee_id_val)
    if sprint_id_val:
        query = query.where(Ticket.sprint_id == sprint_id_val)
    if label_id_val:
        query = query.join(ticket_labels).where(ticket_labels.c.label_id == label_id_val)

    if sort_val == "created_asc":
        query = query.order_by(Ticket.created_at.asc())
    elif sort_val == "priority_desc":
        query = query.order_by(Ticket.priority.desc())
    elif sort_val == "priority_asc":
        query = query.order_by(Ticket.priority.asc())
    elif sort_val == "due_date_asc":
        query = query.order_by(Ticket.due_date.asc().nullslast())
    elif sort_val == "title_asc":
        query = query.order_by(Ticket.title.asc())
    else:
        query = query.order_by(Ticket.created_at.desc())

    # Count
    count_base = select(func.count()).select_from(Ticket)
    if project_id:
        count_base = count_base.where(Ticket.project_id == project_id)
    count_result = await db.execute(count_base)
    total_count = count_result.scalar() or 0

    page_size = 25
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    offset = (page_val - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    tickets = list(result.scalars().unique().all())

    for t in tickets:
        if not t.ticket_type:
            t.ticket_type = t.type

    # Get filter options
    assignees = []
    sprints = []
    labels = []
    if project:
        assignees = await _get_project_members_as_users(project, db)
        sprints = list(project.sprints) if project.sprints else []
        labels = list(project.labels) if project.labels else []
    else:
        users_result = await db.execute(select(User).where(User.is_active == True).order_by(User.username))
        assignees = list(users_result.scalars().all())

    filters = {
        "search": search_val,
        "status": status_val,
        "ticket_type": ticket_type_val,
        "priority": priority_val,
        "assignee_id": assignee_id_val,
        "sprint_id": sprint_id_val,
        "label_id": label_id_val,
        "sort": sort_val,
    }

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "tickets/list.html",
        context={
            "user": user,
            "project": project,
            "tickets": tickets,
            "filters": filters,
            "assignees": assignees,
            "sprints": sprints,
            "labels": labels,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": page_val,
            "page_size": page_size,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


# ─── Global ticket create (redirect-based) ────────────────────────────────────

@router.get("/tickets/create")
async def global_create_ticket_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
):
    project_id = request.query_params.get("project_id", "")

    if project_id:
        return RedirectResponse(
            url=f"/projects/{project_id}/tickets/create",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    projects_result = await db.execute(select(Project).order_by(Project.name))
    projects = list(projects_result.scalars().all())

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "tickets/form.html",
        context={
            "user": user,
            "project": None,
            "projects": projects,
            "members": [],
            "sprints": [],
            "labels": [],
            "parent_tickets": [],
            "edit_mode": False,
            "ticket": None,
            "form_data": None,
            "errors": None,
            "field_errors": None,
            "ticket_label_ids": [],
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/tickets/create")
async def global_create_ticket(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    title: str = Form(""),
    description: str = Form(""),
    type: str = Form("Task"),
    priority: str = Form("Medium"),
    assignee_id: str = Form(""),
    sprint_id: str = Form(""),
    parent_id: str = Form(""),
    due_date: str = Form(""),
):
    form = await request.form()
    project_id = form.get("project_id", "")
    label_ids = form.getlist("label_ids")

    errors = []
    if not title.strip():
        errors.append("Title is required.")
    if not project_id:
        errors.append("Project is required.")

    form_data = {
        "title": title, "description": description, "type": type,
        "priority": priority, "assignee_id": assignee_id, "sprint_id": sprint_id,
        "parent_id": parent_id, "due_date": due_date, "project_id": project_id,
        "label_ids": label_ids,
    }

    if errors:
        projects_result = await db.execute(select(Project).order_by(Project.name))
        projects = list(projects_result.scalars().all())

        return templates.TemplateResponse(
            request,
            "tickets/form.html",
            context={
                "user": user, "project": None, "projects": projects,
                "members": [], "sprints": [], "labels": [],
                "parent_tickets": [], "edit_mode": False, "ticket": None,
                "form_data": form_data, "errors": errors, "field_errors": None,
                "ticket_label_ids": label_ids, "messages": [],
            },
        )

    project = await _get_project_or_404(str(project_id), db)

    ticket_count_result = await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.project_id == project_id)
    )
    ticket_count = (ticket_count_result.scalar() or 0) + 1
    ticket_key = f"{project.key}-{ticket_count}"

    parsed_due_date = None
    if due_date.strip():
        try:
            parsed_due_date = date.fromisoformat(due_date.strip())
        except ValueError:
            pass

    ticket = Ticket(
        title=title.strip(),
        description=description.strip() if description.strip() else None,
        project_id=str(project_id),
        ticket_key=ticket_key,
        type=type,
        ticket_type=type,
        priority=priority,
        status="Open",
        assignee_id=assignee_id if assignee_id else None,
        reporter_id=user.id,
        sprint_id=sprint_id if sprint_id else None,
        parent_id=parent_id if parent_id else None,
        due_date=parsed_due_date,
    )
    db.add(ticket)
    await db.flush()

    if label_ids:
        for lid in label_ids:
            if lid:
                await db.execute(ticket_labels.insert().values(ticket_id=ticket.id, label_id=lid))

    await _create_audit_log(
        db, entity_type="Ticket", entity_id=ticket.id, action="CREATE",
        user_id=user.id, details=json.dumps({"title": ticket.title, "type": type, "priority": priority}),
    )
    await db.commit()

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Ticket created successfully.", "success")
    return response


@router.post("/tickets/{ticket_id}/status")
async def change_ticket_status_shortcut(
    request: Request,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["Super Admin", "Project Manager", "Developer", "QA"])),
    status_field: str = Form("", alias="status"),
):
    form = await request.form()
    new_status = form.get("status", status_field)

    if not new_status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status is required")

    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    old_status = ticket.status
    ticket.status = new_status

    if new_status == "Closed" and ticket.closed_date is None:
        ticket.closed_date = date.today()
    elif new_status != "Closed":
        ticket.closed_date = None

    await _create_audit_log(
        db, entity_type="Ticket", entity_id=ticket.id, action="UPDATE",
        user_id=user.id, details=json.dumps({"field": "status", "old": old_status, "new": new_status}),
    )
    await db.commit()

    accept = request.headers.get("accept", "")
    if "text/html" not in accept:
        return Response(status_code=200)

    response = RedirectResponse(
        url=f"/projects/{ticket.project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"Ticket status changed to {new_status}.", "success")
    return response