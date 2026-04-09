import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_session_user, get_flash_messages, clear_flash_messages
from models.user import User
from models.project import Project, ProjectMember
from models.ticket import Ticket, ticket_labels
from models.sprint import Sprint
from models.label import Label

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/projects/{project_id}/board")
async def kanban_board(
    request: Request,
    project_id: str,
    sprint_id: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    label_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_session_user),
):
    if user is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Load project
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

    if project is None:
        return RedirectResponse(url="/projects", status_code=303)

    # Build ticket query with filters
    ticket_query = (
        select(Ticket)
        .where(Ticket.project_id == project_id)
        .options(
            selectinload(Ticket.assignee),
            selectinload(Ticket.reporter),
            selectinload(Ticket.sprint),
            selectinload(Ticket.labels),
            selectinload(Ticket.project),
        )
    )

    if sprint_id:
        ticket_query = ticket_query.where(Ticket.sprint_id == sprint_id)

    if assignee_id:
        ticket_query = ticket_query.where(Ticket.assignee_id == assignee_id)

    if priority:
        ticket_query = ticket_query.where(Ticket.priority == priority)

    if type:
        ticket_query = ticket_query.where(Ticket.type == type)

    if label_id:
        ticket_query = ticket_query.join(ticket_labels).where(ticket_labels.c.label_id == label_id)

    result = await db.execute(ticket_query)
    all_tickets = result.scalars().unique().all()

    # Group tickets by status into columns
    columns = {
        "open": [],
        "in_progress": [],
        "in_review": [],
        "qa_testing": [],
        "closed": [],
    }

    status_mapping = {
        "Open": "open",
        "In Progress": "in_progress",
        "In Review": "in_review",
        "QA Testing": "qa_testing",
        "Closed": "closed",
        "Reopened": "open",
    }

    for ticket in all_tickets:
        column_key = status_mapping.get(ticket.status, "open")
        columns[column_key].append(ticket)

    total_tickets = len(all_tickets)

    # Get members for assignee filter
    members = [pm.user for pm in project.project_members if pm.user is not None]

    # Get sprints for sprint filter
    sprints = project.sprints or []

    # Get labels for label filter
    labels = project.labels or []

    # Find current active sprint
    current_sprint = None
    for sprint in sprints:
        if sprint.status == "Active":
            current_sprint = sprint
            break

    filters = {
        "sprint_id": sprint_id or "",
        "assignee_id": assignee_id or "",
        "priority": priority or "",
        "type": type or "",
        "label_id": label_id or "",
    }

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "projects/board.html",
        context={
            "user": user,
            "project": project,
            "columns": columns,
            "total_tickets": total_tickets,
            "members": members,
            "sprints": sprints,
            "labels": labels,
            "current_sprint": current_sprint,
            "filters": filters,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/tickets/{ticket_id}/status")
async def update_ticket_status(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_session_user),
):
    if user is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    if user.role not in ["Super Admin", "Project Manager", "Developer", "QA"]:
        return RedirectResponse(url=f"/projects/{project_id}/board", status_code=303)

    form_data = await request.form()
    new_status = form_data.get("status", "")

    valid_statuses = ["Open", "In Progress", "In Review", "QA Testing", "Closed", "Reopened"]
    if new_status not in valid_statuses:
        return RedirectResponse(url=f"/projects/{project_id}/board", status_code=303)

    result = await db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .where(Ticket.project_id == project_id)
    )
    ticket = result.scalars().first()

    if ticket is None:
        return RedirectResponse(url=f"/projects/{project_id}/board", status_code=303)

    ticket.status = new_status
    await db.flush()

    return RedirectResponse(url=f"/projects/{project_id}/board", status_code=303)