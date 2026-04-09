import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_session_user, get_flash_messages, clear_flash_messages
from models.user import User
from models.project import Project
from models.sprint import Sprint
from models.ticket import Ticket
from models.time_entry import TimeEntry
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/dashboard")
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_session_user),
):
    if user is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    messages = get_flash_messages(request)

    try:
        # Total projects
        if user.role == "Super Admin":
            result = await db.execute(select(func.count(Project.id)))
        else:
            result = await db.execute(
                select(func.count(Project.id))
            )
        total_projects = result.scalar() or 0

        # Active sprints
        result = await db.execute(
            select(func.count(Sprint.id)).where(Sprint.status == "Active")
        )
        active_sprints = result.scalar() or 0

        # Open tickets (not Closed)
        result = await db.execute(
            select(func.count(Ticket.id)).where(Ticket.status != "Closed")
        )
        open_tickets = result.scalar() or 0

        # Overdue tickets
        today = date.today()
        result = await db.execute(
            select(func.count(Ticket.id)).where(
                and_(
                    Ticket.due_date < today,
                    Ticket.status != "Closed",
                    Ticket.due_date.isnot(None),
                )
            )
        )
        overdue_tickets = result.scalar() or 0

        # Total hours logged
        result = await db.execute(
            select(func.coalesce(func.sum(TimeEntry.hours), 0.0))
        )
        total_hours_logged = result.scalar() or 0.0

        # Tickets by status
        result = await db.execute(
            select(
                Ticket.status,
                func.count(Ticket.id).label("count"),
            )
            .group_by(Ticket.status)
            .order_by(func.count(Ticket.id).desc())
        )
        tickets_by_status_rows = result.all()
        tickets_by_status = []
        for row in tickets_by_status_rows:
            tickets_by_status.append(
                {"status": row[0], "count": row[1]}
            )

        # Top contributors (ranked by hours logged)
        result = await db.execute(
            select(
                User.id,
                User.username,
                User.role,
                func.coalesce(func.sum(TimeEntry.hours), 0.0).label("total_hours"),
            )
            .join(TimeEntry, TimeEntry.user_id == User.id)
            .group_by(User.id, User.username, User.role)
            .order_by(func.sum(TimeEntry.hours).desc())
            .limit(10)
        )
        top_contributors_rows = result.all()
        top_contributors = []
        for row in top_contributors_rows:
            top_contributors.append(
                {
                    "id": row[0],
                    "username": row[1],
                    "role": row[2],
                    "total_hours": float(row[3]),
                }
            )

        # Recent audit log entries
        recent_audit_logs = []
        if user.role in ["Super Admin", "Project Manager"]:
            result = await db.execute(
                select(AuditLog)
                .options(selectinload(AuditLog.actor))
                .order_by(AuditLog.created_at.desc())
                .limit(10)
            )
            recent_audit_logs = result.scalars().all()

    except Exception:
        logger.exception("Error loading dashboard data")
        total_projects = 0
        active_sprints = 0
        open_tickets = 0
        overdue_tickets = 0
        total_hours_logged = 0.0
        tickets_by_status = []
        top_contributors = []
        recent_audit_logs = []

    response = templates.TemplateResponse(
        request,
        "dashboard/index.html",
        context={
            "user": user,
            "messages": messages,
            "total_projects": total_projects,
            "active_sprints": active_sprints,
            "open_tickets": open_tickets,
            "overdue_tickets": overdue_tickets,
            "total_hours_logged": total_hours_logged,
            "tickets_by_status": tickets_by_status,
            "top_contributors": top_contributors,
            "recent_audit_logs": recent_audit_logs,
        },
    )

    clear_flash_messages(response)
    return response