import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import math
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import require_super_admin, get_flash_messages, clear_flash_messages
from models.user import User
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-log")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

PAGE_SIZE = 50


@router.get("")
async def list_audit_logs(
    request: Request,
    entity_type: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_super_admin),
):
    filters = {
        "entity_type": entity_type or "",
        "action_type": action_type or "",
        "user_id": user_id or "",
    }

    query = select(AuditLog).options(selectinload(AuditLog.actor))

    count_query = select(func.count(AuditLog.id))

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
        count_query = count_query.where(AuditLog.entity_type == entity_type)

    if action_type:
        query = query.where(AuditLog.action == action_type)
        count_query = count_query.where(AuditLog.action == action_type)

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)

    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    total_pages = max(1, math.ceil(total_count / PAGE_SIZE))

    if page > total_pages:
        page = total_pages

    offset = (page - 1) * PAGE_SIZE

    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(PAGE_SIZE)

    result = await db.execute(query)
    audit_logs = result.scalars().all()

    entity_types_result = await db.execute(
        select(distinct(AuditLog.entity_type)).where(AuditLog.entity_type.isnot(None)).order_by(AuditLog.entity_type)
    )
    entity_types = [row[0] for row in entity_types_result.all() if row[0]]

    action_types_result = await db.execute(
        select(distinct(AuditLog.action)).where(AuditLog.action.isnot(None)).order_by(AuditLog.action)
    )
    action_types = [row[0] for row in action_types_result.all() if row[0]]

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.username)
    )
    users = users_result.scalars().all()

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "audit/list.html",
        context={
            "user": user,
            "audit_logs": audit_logs,
            "filters": filters,
            "entity_types": entity_types,
            "action_types": action_types,
            "users": users,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response