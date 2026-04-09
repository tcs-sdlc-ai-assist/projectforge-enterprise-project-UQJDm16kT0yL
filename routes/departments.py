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
from dependencies import (
    get_session_user,
    require_super_admin,
    set_flash_message,
    get_flash_messages,
    clear_flash_messages,
)
from models.user import User
from models.department import Department
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/departments")
async def list_departments(
    request: Request,
    user: Optional[User] = Depends(get_session_user),
    db: AsyncSession = Depends(get_db),
):
    if user is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    result = await db.execute(
        select(Department)
        .options(
            selectinload(Department.head),
            selectinload(Department.members),
            selectinload(Department.projects),
        )
        .order_by(Department.name)
    )
    departments = result.scalars().all()

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "departments/list.html",
        context={
            "user": user,
            "departments": departments,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/departments/create")
async def create_department(
    request: Request,
    response: Response,
    name: str = Form(...),
    code: str = Form(...),
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    errors = []

    name = name.strip()
    code = code.strip().upper()

    if not name:
        errors.append("Department name is required.")
    if not code:
        errors.append("Department code is required.")
    if len(code) > 10:
        errors.append("Department code must be 10 characters or fewer.")

    if not errors:
        existing_name = await db.execute(
            select(Department).where(func.lower(Department.name) == name.lower())
        )
        if existing_name.scalars().first() is not None:
            errors.append(f"A department with the name '{name}' already exists.")

        existing_code = await db.execute(
            select(Department).where(func.lower(Department.code) == code.lower())
        )
        if existing_code.scalars().first() is not None:
            errors.append(f"A department with the code '{code}' already exists.")

    if errors:
        result = await db.execute(
            select(Department)
            .options(
                selectinload(Department.head),
                selectinload(Department.members),
                selectinload(Department.projects),
            )
            .order_by(Department.name)
        )
        departments = result.scalars().all()

        messages = [{"text": err, "category": "error"} for err in errors]
        return templates.TemplateResponse(
            request,
            "departments/list.html",
            context={
                "user": user,
                "departments": departments,
                "messages": messages,
            },
        )

    department = Department(
        name=name,
        code=code,
    )
    db.add(department)
    await db.flush()

    audit_log = AuditLog(
        entity_type="Department",
        entity_id=department.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({"name": name, "code": code}),
    )
    db.add(audit_log)
    await db.flush()

    logger.info("Department '%s' (code=%s) created by user '%s'", name, code, user.username)

    redirect = RedirectResponse(url="/departments", status_code=303)
    set_flash_message(redirect, f"Department '{name}' created successfully.", "success")
    return redirect


@router.get("/departments/{department_id}")
async def department_detail(
    request: Request,
    department_id: str,
    user: Optional[User] = Depends(get_session_user),
    db: AsyncSession = Depends(get_db),
):
    if user is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    result = await db.execute(
        select(Department)
        .where(Department.id == department_id)
        .options(
            selectinload(Department.head),
            selectinload(Department.members),
            selectinload(Department.projects),
        )
    )
    department = result.scalars().first()

    if department is None:
        redirect = RedirectResponse(url="/departments", status_code=303)
        set_flash_message(redirect, "Department not found.", "error")
        return redirect

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "departments/list.html",
        context={
            "user": user,
            "departments": [department],
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.get("/departments/{department_id}/edit")
async def edit_department_form(
    request: Request,
    department_id: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Department)
        .where(Department.id == department_id)
        .options(
            selectinload(Department.head),
            selectinload(Department.members),
            selectinload(Department.projects),
        )
    )
    department = result.scalars().first()

    if department is None:
        redirect = RedirectResponse(url="/departments", status_code=303)
        set_flash_message(redirect, "Department not found.", "error")
        return redirect

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.username)
    )
    all_users = users_result.scalars().all()

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "departments/list.html",
        context={
            "user": user,
            "departments": [department],
            "department": department,
            "all_users": all_users,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/departments/{department_id}/edit")
async def edit_department(
    request: Request,
    department_id: str,
    name: str = Form(...),
    code: str = Form(...),
    head_id: Optional[str] = Form(None),
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Department)
        .where(Department.id == department_id)
        .options(
            selectinload(Department.head),
            selectinload(Department.members),
        )
    )
    department = result.scalars().first()

    if department is None:
        redirect = RedirectResponse(url="/departments", status_code=303)
        set_flash_message(redirect, "Department not found.", "error")
        return redirect

    errors = []
    name = name.strip()
    code = code.strip().upper()

    if not name:
        errors.append("Department name is required.")
    if not code:
        errors.append("Department code is required.")
    if len(code) > 10:
        errors.append("Department code must be 10 characters or fewer.")

    if not errors:
        existing_name = await db.execute(
            select(Department)
            .where(func.lower(Department.name) == name.lower())
            .where(Department.id != department_id)
        )
        if existing_name.scalars().first() is not None:
            errors.append(f"A department with the name '{name}' already exists.")

        existing_code = await db.execute(
            select(Department)
            .where(func.lower(Department.code) == code.lower())
            .where(Department.id != department_id)
        )
        if existing_code.scalars().first() is not None:
            errors.append(f"A department with the code '{code}' already exists.")

    if errors:
        redirect = RedirectResponse(url=f"/departments/{department_id}/edit", status_code=303)
        set_flash_message(redirect, " ".join(errors), "error")
        return redirect

    changes = {}
    if department.name != name:
        changes["name"] = {"old": department.name, "new": name}
        department.name = name
    if department.code != code:
        changes["code"] = {"old": department.code, "new": code}
        department.code = code

    if head_id and head_id.strip():
        if department.head_id != head_id:
            changes["head_id"] = {"old": department.head_id, "new": head_id}
            department.head_id = head_id
    else:
        if department.head_id is not None:
            changes["head_id"] = {"old": department.head_id, "new": None}
            department.head_id = None

    await db.flush()

    if changes:
        audit_log = AuditLog(
            entity_type="Department",
            entity_id=department.id,
            action="UPDATE",
            user_id=user.id,
            details=json.dumps(changes),
        )
        db.add(audit_log)
        await db.flush()

    logger.info("Department '%s' updated by user '%s'", department.name, user.username)

    redirect = RedirectResponse(url="/departments", status_code=303)
    set_flash_message(redirect, f"Department '{department.name}' updated successfully.", "success")
    return redirect


@router.post("/departments/{department_id}/delete")
async def delete_department(
    request: Request,
    department_id: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Department)
        .where(Department.id == department_id)
        .options(
            selectinload(Department.members),
        )
    )
    department = result.scalars().first()

    if department is None:
        redirect = RedirectResponse(url="/departments", status_code=303)
        set_flash_message(redirect, "Department not found.", "error")
        return redirect

    member_count = await db.execute(
        select(func.count(User.id)).where(User.department_id == department_id)
    )
    count = member_count.scalar() or 0

    if count > 0:
        redirect = RedirectResponse(url="/departments", status_code=303)
        set_flash_message(
            redirect,
            f"Cannot delete department '{department.name}' because it has {count} assigned user(s). "
            f"Please reassign or remove all users from this department first.",
            "error",
        )
        return redirect

    department_name = department.name
    department_id_str = department.id

    audit_log = AuditLog(
        entity_type="Department",
        entity_id=department_id_str,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({"name": department_name, "code": department.code}),
    )
    db.add(audit_log)
    await db.flush()

    await db.delete(department)
    await db.flush()

    logger.info("Department '%s' deleted by user '%s'", department_name, user.username)

    redirect = RedirectResponse(url="/departments", status_code=303)
    set_flash_message(redirect, f"Department '{department_name}' deleted successfully.", "success")
    return redirect


@router.post("/departments/{department_id}/set-head")
async def set_department_head(
    request: Request,
    department_id: str,
    head_id: str = Form(...),
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Department)
        .where(Department.id == department_id)
        .options(
            selectinload(Department.head),
            selectinload(Department.members),
        )
    )
    department = result.scalars().first()

    if department is None:
        redirect = RedirectResponse(url="/departments", status_code=303)
        set_flash_message(redirect, "Department not found.", "error")
        return redirect

    if not head_id or not head_id.strip():
        redirect = RedirectResponse(url="/departments", status_code=303)
        set_flash_message(redirect, "Please select a user to set as department head.", "error")
        return redirect

    head_user_result = await db.execute(
        select(User).where(User.id == head_id).where(User.is_active == True)
    )
    head_user = head_user_result.scalars().first()

    if head_user is None:
        redirect = RedirectResponse(url="/departments", status_code=303)
        set_flash_message(redirect, "Selected user not found or is inactive.", "error")
        return redirect

    old_head_id = department.head_id
    department.head_id = head_id
    await db.flush()

    audit_log = AuditLog(
        entity_type="Department",
        entity_id=department.id,
        action="UPDATE",
        user_id=user.id,
        details=json.dumps({
            "action": "set_head",
            "head_id": {"old": old_head_id, "new": head_id},
            "head_username": head_user.username,
        }),
    )
    db.add(audit_log)
    await db.flush()

    logger.info(
        "Department '%s' head set to '%s' by user '%s'",
        department.name,
        head_user.username,
        user.username,
    )

    redirect = RedirectResponse(url="/departments", status_code=303)
    set_flash_message(
        redirect,
        f"'{head_user.username}' has been set as head of '{department.name}'.",
        "success",
    )
    return redirect