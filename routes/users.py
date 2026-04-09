import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import json
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import (
    require_super_admin,
    get_session_user,
    set_flash_message,
    get_flash_messages,
    clear_flash_messages,
)
from models.user import User
from models.department import Department
from models.audit_log import AuditLog
from passlib.context import CryptContext
from jinja2 import Environment, FileSystemLoader
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/users")
async def list_users(
    request: Request,
    search: Optional[str] = None,
    role: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = 1,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    per_page = 20

    query = select(User).options(selectinload(User.department))

    if search:
        search_term = f"%{search}%"
        query = query.where(
            (User.username.ilike(search_term)) | (User.email.ilike(search_term))
        )

    if role:
        query = query.where(User.role == role)

    if status_filter == "active":
        query = query.where(User.is_active == True)
    elif status_filter == "inactive":
        query = query.where(User.is_active == False)

    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_users = count_result.scalar() or 0

    total_pages = max(1, (total_users + per_page - 1) // per_page)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    query = query.order_by(User.created_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    users = result.scalars().all()

    dept_result = await db.execute(
        select(Department).options(selectinload(Department.head)).order_by(Department.name)
    )
    departments = dept_result.scalars().all()

    filters = {
        "search": search or "",
        "role": role or "",
        "status": status_filter or "",
    }

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "users/list.html",
        context={
            "user": user,
            "users": users,
            "departments": departments,
            "filters": filters,
            "page": page,
            "per_page": per_page,
            "total_users": total_users,
            "total_pages": total_pages,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/users/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    role: str = Form("Developer"),
    department_id: str = Form(""),
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    errors = []

    if not username or len(username.strip()) < 3:
        errors.append("Username must be at least 3 characters.")

    if not password or len(password) < 6:
        errors.append("Password must be at least 6 characters.")

    valid_roles = ["Super Admin", "Project Manager", "Developer", "QA", "Viewer"]
    if role not in valid_roles:
        errors.append(f"Invalid role. Must be one of: {', '.join(valid_roles)}")

    username_clean = username.strip()

    existing_result = await db.execute(
        select(User).where(User.username == username_clean)
    )
    existing_user = existing_result.scalars().first()
    if existing_user:
        errors.append(f"Username '{username_clean}' already exists.")

    if email and email.strip():
        email_clean = email.strip()
        existing_email_result = await db.execute(
            select(User).where(User.email == email_clean)
        )
        existing_email_user = existing_email_result.scalars().first()
        if existing_email_user:
            errors.append(f"Email '{email_clean}' is already in use.")
    else:
        email_clean = None

    if errors:
        response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
        set_flash_message(response, "; ".join(errors), "error")
        return response

    password_hash = pwd_context.hash(password)

    dept_id = department_id.strip() if department_id and department_id.strip() else None

    new_user = User(
        username=username_clean,
        email=email_clean,
        password_hash=password_hash,
        role=role,
        department_id=dept_id,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    audit_log = AuditLog(
        entity_type="User",
        entity_id=new_user.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({
            "username": username_clean,
            "email": email_clean,
            "role": role,
            "department_id": dept_id,
        }),
    )
    db.add(audit_log)
    await db.flush()

    logger.info("User '%s' created by '%s'", username_clean, user.username)

    response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
    set_flash_message(response, f"User '{username_clean}' created successfully.", "success")
    return response


@router.get("/users/{user_id}/edit")
async def edit_user_form(
    request: Request,
    user_id: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.department))
    )
    target_user = result.scalars().first()

    if not target_user:
        response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
        set_flash_message(response, "User not found.", "error")
        return response

    dept_result = await db.execute(
        select(Department).order_by(Department.name)
    )
    departments = dept_result.scalars().all()

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "users/edit.html",
        context={
            "user": user,
            "target_user": target_user,
            "departments": departments,
            "messages": messages,
            "errors": [],
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/users/{user_id}/edit")
async def edit_user(
    request: Request,
    user_id: str,
    role: str = Form(""),
    department_id: str = Form(""),
    display_name: str = Form(""),
    email: str = Form(""),
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.department))
    )
    target_user = result.scalars().first()

    if not target_user:
        response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
        set_flash_message(response, "User not found.", "error")
        return response

    errors = []
    valid_roles = ["Super Admin", "Project Manager", "Developer", "QA", "Viewer"]
    if role and role not in valid_roles:
        errors.append(f"Invalid role. Must be one of: {', '.join(valid_roles)}")

    if email and email.strip():
        email_clean = email.strip()
        existing_email_result = await db.execute(
            select(User).where(User.email == email_clean).where(User.id != user_id)
        )
        existing_email_user = existing_email_result.scalars().first()
        if existing_email_user:
            errors.append(f"Email '{email_clean}' is already in use by another user.")
    else:
        email_clean = target_user.email

    if errors:
        dept_result = await db.execute(
            select(Department).order_by(Department.name)
        )
        departments = dept_result.scalars().all()

        messages = get_flash_messages(request)
        resp = templates.TemplateResponse(
            request,
            "users/edit.html",
            context={
                "user": user,
                "target_user": target_user,
                "departments": departments,
                "messages": messages,
                "errors": errors,
            },
        )
        clear_flash_messages(resp)
        return resp

    changes = {}

    if role and role != target_user.role:
        changes["role"] = {"from": target_user.role, "to": role}
        target_user.role = role

    dept_id = department_id.strip() if department_id and department_id.strip() else None
    if dept_id != target_user.department_id:
        changes["department_id"] = {"from": target_user.department_id, "to": dept_id}
        target_user.department_id = dept_id

    display_name_clean = display_name.strip() if display_name else None
    if display_name_clean != target_user.display_name:
        changes["display_name"] = {"from": target_user.display_name, "to": display_name_clean}
        target_user.display_name = display_name_clean

    if email_clean != target_user.email:
        changes["email"] = {"from": target_user.email, "to": email_clean}
        target_user.email = email_clean

    if changes:
        audit_log = AuditLog(
            entity_type="User",
            entity_id=target_user.id,
            action="UPDATE",
            user_id=user.id,
            details=json.dumps(changes),
        )
        db.add(audit_log)
        await db.flush()

        logger.info(
            "User '%s' updated by '%s': %s",
            target_user.username,
            user.username,
            json.dumps(changes),
        )

    response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
    if changes:
        set_flash_message(response, f"User '{target_user.username}' updated successfully.", "success")
    else:
        set_flash_message(response, "No changes were made.", "info")
    return response


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    request: Request,
    user_id: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    target_user = result.scalars().first()

    if not target_user:
        response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
        set_flash_message(response, "User not found.", "error")
        return response

    if target_user.id == user.id:
        response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
        set_flash_message(response, "You cannot deactivate your own account.", "error")
        return response

    old_status = target_user.is_active
    target_user.is_active = not old_status
    new_status = target_user.is_active

    audit_log = AuditLog(
        entity_type="User",
        entity_id=target_user.id,
        action="UPDATE",
        user_id=user.id,
        details=json.dumps({
            "is_active": {"from": old_status, "to": new_status},
        }),
    )
    db.add(audit_log)
    await db.flush()

    action_word = "activated" if new_status else "deactivated"
    logger.info(
        "User '%s' %s by '%s'",
        target_user.username,
        action_word,
        user.username,
    )

    response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
    set_flash_message(
        response,
        f"User '{target_user.username}' has been {action_word}.",
        "success",
    )
    return response