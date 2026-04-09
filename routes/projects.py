import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import logging
import math
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import (
    get_session_user,
    require_login,
    require_project_manager_or_above,
    require_super_admin,
    set_flash_message,
    get_flash_messages,
    clear_flash_messages,
)
from models.audit_log import AuditLog
from models.department import Department
from models.project import Project, ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


async def _get_user_or_redirect(request: Request, db: AsyncSession):
    user = await get_session_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
        )
    return user


async def _create_audit_log(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    action: str,
    user_id: str,
    details: Optional[str] = None,
):
    audit = AuditLog(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        details=details,
        created_at=datetime.utcnow(),
    )
    db.add(audit)


@router.get("/projects")
async def list_projects(
    request: Request,
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    department: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = 1,
):
    user = await _get_user_or_redirect(request, db)

    status_param = request.query_params.get("status", "")
    department_param = request.query_params.get("department", "")
    search_param = request.query_params.get("search", "")
    sort_param = request.query_params.get("sort", "newest")

    query = select(Project).options(
        selectinload(Project.department),
        selectinload(Project.project_members).selectinload(ProjectMember.user),
        selectinload(Project.creator),
    )

    if search_param:
        search_term = f"%{search_param}%"
        query = query.where(
            or_(
                Project.name.ilike(search_term),
                Project.key.ilike(search_term),
            )
        )

    if status_param:
        query = query.where(Project.status == status_param)

    if department_param:
        query = query.where(Project.department_id == department_param)

    if sort_param == "oldest":
        query = query.order_by(Project.created_at.asc())
    elif sort_param == "name_asc":
        query = query.order_by(Project.name.asc())
    elif sort_param == "name_desc":
        query = query.order_by(Project.name.desc())
    elif sort_param == "status":
        query = query.order_by(Project.status.asc(), Project.name.asc())
    else:
        query = query.order_by(Project.created_at.desc())

    per_page = 20
    count_query = select(func.count()).select_from(Project)
    if search_param:
        search_term = f"%{search_param}%"
        count_query = count_query.where(
            or_(
                Project.name.ilike(search_term),
                Project.key.ilike(search_term),
            )
        )
    if status_param:
        count_query = count_query.where(Project.status == status_param)
    if department_param:
        count_query = count_query.where(Project.department_id == department_param)

    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0
    total_pages = max(1, math.ceil(total_count / per_page))

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    projects = result.scalars().unique().all()

    dept_result = await db.execute(select(Department).order_by(Department.name.asc()))
    departments = dept_result.scalars().all()

    filters = {
        "search": search_param,
        "status": status_param,
        "department": department_param,
        "sort": sort_param,
    }

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "projects/list.html",
        context={
            "user": user,
            "projects": projects,
            "departments": departments,
            "filters": filters,
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.get("/projects/create")
async def create_project_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create projects.",
        )

    dept_result = await db.execute(select(Department).order_by(Department.name.asc()))
    departments = dept_result.scalars().all()

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "projects/form.html",
        context={
            "user": user,
            "project": None,
            "departments": departments,
            "errors": [],
            "form_data": None,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/create")
async def create_project(
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(""),
    description: str = Form(""),
    status_field: str = Form("Planning"),
    department_id: str = Form(""),
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create projects.",
        )

    form_data_raw = await request.form()
    actual_status = form_data_raw.get("status", "Planning")
    actual_name = form_data_raw.get("name", "").strip()
    actual_description = form_data_raw.get("description", "").strip()
    actual_department_id = form_data_raw.get("department_id", "").strip()

    form_data = {
        "name": actual_name,
        "description": actual_description,
        "status": actual_status,
        "department_id": actual_department_id,
    }

    errors = []

    if not actual_name:
        errors.append("Project name is required.")
    elif len(actual_name) > 200:
        errors.append("Project name must be 200 characters or less.")

    if actual_name:
        existing = await db.execute(
            select(Project).where(func.lower(Project.name) == actual_name.lower())
        )
        if existing.scalars().first():
            errors.append("A project with this name already exists.")

    valid_statuses = ["Planning", "Active", "On Hold", "Completed", "Archived"]
    if actual_status not in valid_statuses:
        errors.append(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    if actual_department_id:
        dept_check = await db.execute(
            select(Department).where(Department.id == actual_department_id)
        )
        if not dept_check.scalars().first():
            errors.append("Selected department does not exist.")

    if errors:
        dept_result = await db.execute(select(Department).order_by(Department.name.asc()))
        departments = dept_result.scalars().all()

        return templates.TemplateResponse(
            request,
            "projects/form.html",
            context={
                "user": user,
                "project": None,
                "departments": departments,
                "errors": errors,
                "form_data": form_data,
                "messages": [],
            },
        )

    project_key = _generate_project_key(actual_name)

    key_exists = await db.execute(
        select(Project).where(Project.key == project_key)
    )
    if key_exists.scalars().first():
        suffix = 1
        while True:
            candidate = f"{project_key}{suffix}"
            check = await db.execute(
                select(Project).where(Project.key == candidate)
            )
            if not check.scalars().first():
                project_key = candidate
                break
            suffix += 1

    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        name=actual_name,
        key=project_key,
        description=actual_description if actual_description else None,
        status=actual_status,
        department_id=actual_department_id if actual_department_id else None,
        created_by=user.id,
    )
    db.add(project)

    member = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=project_id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)

    await _create_audit_log(
        db=db,
        entity_type="Project",
        entity_id=project_id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({"name": actual_name, "key": project_key, "status": actual_status}),
    )

    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Project created successfully.", "success")
    return response


@router.get("/projects/{project_id}")
async def project_detail(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.project_members).selectinload(ProjectMember.user),
            selectinload(Project.sprints),
            selectinload(Project.tickets).selectinload(Ticket.assignee),
            selectinload(Project.tickets).selectinload(Ticket.labels),
            selectinload(Project.labels),
            selectinload(Project.creator),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    sprints = sorted(project.sprints, key=lambda s: s.created_at if s.created_at else datetime.min, reverse=True) if project.sprints else []
    tickets = sorted(project.tickets, key=lambda t: t.created_at if t.created_at else datetime.min, reverse=True) if project.tickets else []
    members = project.members if project.members else []

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "projects/detail.html",
        context={
            "user": user,
            "project": project,
            "sprints": sprints,
            "tickets": tickets,
            "members": members,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.get("/projects/{project_id}/edit")
async def edit_project_form(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit projects.",
        )

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.project_members),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    dept_result = await db.execute(select(Department).order_by(Department.name.asc()))
    departments = dept_result.scalars().all()

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "projects/form.html",
        context={
            "user": user,
            "project": project,
            "departments": departments,
            "errors": [],
            "form_data": None,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/edit")
async def update_project(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit projects.",
        )

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.project_members),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    form_data_raw = await request.form()
    actual_name = form_data_raw.get("name", "").strip()
    actual_description = form_data_raw.get("description", "").strip()
    actual_status = form_data_raw.get("status", project.status)
    actual_department_id = form_data_raw.get("department_id", "").strip()

    form_data = {
        "name": actual_name,
        "description": actual_description,
        "status": actual_status,
        "department_id": actual_department_id,
    }

    errors = []

    if not actual_name:
        errors.append("Project name is required.")
    elif len(actual_name) > 200:
        errors.append("Project name must be 200 characters or less.")

    if actual_name and actual_name.lower() != project.name.lower():
        existing = await db.execute(
            select(Project).where(
                func.lower(Project.name) == actual_name.lower(),
                Project.id != project_id,
            )
        )
        if existing.scalars().first():
            errors.append("A project with this name already exists.")

    valid_statuses = ["Planning", "Active", "On Hold", "Completed", "Archived"]
    if actual_status not in valid_statuses:
        errors.append(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    if actual_department_id:
        dept_check = await db.execute(
            select(Department).where(Department.id == actual_department_id)
        )
        if not dept_check.scalars().first():
            errors.append("Selected department does not exist.")

    if errors:
        dept_result = await db.execute(select(Department).order_by(Department.name.asc()))
        departments = dept_result.scalars().all()

        return templates.TemplateResponse(
            request,
            "projects/form.html",
            context={
                "user": user,
                "project": project,
                "departments": departments,
                "errors": errors,
                "form_data": form_data,
                "messages": [],
            },
        )

    changes = {}
    if actual_name != project.name:
        changes["name"] = {"old": project.name, "new": actual_name}
        project.name = actual_name
    if actual_description != (project.description or ""):
        changes["description"] = {"old": project.description, "new": actual_description}
        project.description = actual_description if actual_description else None
    if actual_status != project.status:
        changes["status"] = {"old": project.status, "new": actual_status}
        project.status = actual_status

    new_dept_id = actual_department_id if actual_department_id else None
    if new_dept_id != project.department_id:
        changes["department_id"] = {"old": project.department_id, "new": new_dept_id}
        project.department_id = new_dept_id

    if changes:
        await _create_audit_log(
            db=db,
            entity_type="Project",
            entity_id=project_id,
            action="UPDATE",
            user_id=user.id,
            details=json.dumps(changes),
        )

    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, "Project updated successfully.", "success")
    return response


@router.post("/projects/{project_id}/delete")
async def delete_project(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete projects.",
        )

    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    project_name = project.name

    await _create_audit_log(
        db=db,
        entity_type="Project",
        entity_id=project_id,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({"name": project_name, "key": project.key}),
    )

    await db.delete(project)
    await db.flush()

    response = RedirectResponse(
        url="/projects",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"Project '{project_name}' deleted successfully.", "success")
    return response


@router.get("/projects/{project_id}/members")
async def project_members_page(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage project members.",
        )

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.project_members).selectinload(ProjectMember.user),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    member_user_ids = {pm.user_id for pm in project.project_members}

    all_users_result = await db.execute(
        select(User)
        .where(User.is_active == True)
        .order_by(User.username.asc())
    )
    all_users = all_users_result.scalars().all()

    available_users = [u for u in all_users if u.id not in member_user_ids]

    members = project.members if project.members else []

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "projects/members.html",
        context={
            "user": user,
            "project": project,
            "members": members,
            "available_users": available_users,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/members/add")
async def add_project_member(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Form(""),
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage project members.",
        )

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.project_members))
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    form_data_raw = await request.form()
    member_user_id = form_data_raw.get("user_id", "").strip()

    if not member_user_id:
        response = RedirectResponse(
            url=f"/projects/{project_id}/members",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, "Please select a user to add.", "error")
        return response

    target_user_result = await db.execute(
        select(User).where(User.id == member_user_id, User.is_active == True)
    )
    target_user = target_user_result.scalars().first()

    if not target_user:
        response = RedirectResponse(
            url=f"/projects/{project_id}/members",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, "Selected user not found or is inactive.", "error")
        return response

    existing_member = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == member_user_id,
        )
    )
    if existing_member.scalars().first():
        response = RedirectResponse(
            url=f"/projects/{project_id}/members",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, f"{target_user.username} is already a member of this project.", "warning")
        return response

    member = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=project_id,
        user_id=member_user_id,
        role="member",
    )
    db.add(member)

    await _create_audit_log(
        db=db,
        entity_type="ProjectMember",
        entity_id=member.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({
            "project_id": project_id,
            "added_user_id": member_user_id,
            "added_username": target_user.username,
        }),
    )

    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}/members",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"{target_user.username} added to the project.", "success")
    return response


@router.post("/projects/{project_id}/members/{member_id}/remove")
async def remove_project_member(
    request: Request,
    project_id: str,
    member_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage project members.",
        )

    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    member_result = await db.execute(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == member_id,
        )
        .options(selectinload(ProjectMember.user))
    )
    membership = member_result.scalars().first()

    if not membership:
        response = RedirectResponse(
            url=f"/projects/{project_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, "Member not found in this project.", "error")
        return response

    removed_username = membership.user.username if membership.user else "Unknown"

    await _create_audit_log(
        db=db,
        entity_type="ProjectMember",
        entity_id=membership.id,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({
            "project_id": project_id,
            "removed_user_id": member_id,
            "removed_username": removed_username,
        }),
    )

    await db.delete(membership)
    await db.flush()

    referer = request.headers.get("referer", "")
    if "/members" in referer:
        redirect_url = f"/projects/{project_id}/members"
    else:
        redirect_url = f"/projects/{project_id}"

    response = RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"{removed_username} removed from the project.", "success")
    return response


@router.get("/projects/{project_id}/tickets")
async def project_tickets(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.tickets).selectinload(Ticket.assignee),
            selectinload(Project.tickets).selectinload(Ticket.labels),
            selectinload(Project.tickets).selectinload(Ticket.sprint),
            selectinload(Project.sprints),
            selectinload(Project.labels),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    response = RedirectResponse(
        url=f"/tickets?project_id={project_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    return response


@router.get("/projects/{project_id}/tickets/create")
async def project_ticket_create_redirect(
    request: Request,
    project_id: str,
):
    return RedirectResponse(
        url=f"/tickets/create?project_id={project_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/projects/{project_id}/sprints")
async def project_sprints_redirect(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.sprints).selectinload(Sprint.tickets),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    sprints = sorted(
        project.sprints,
        key=lambda s: s.created_at if s.created_at else datetime.min,
        reverse=True,
    ) if project.sprints else []

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


@router.get("/projects/{project_id}/labels")
async def project_labels(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    from models.label import Label

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.labels).selectinload(Label.tickets),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    labels = project.labels if project.labels else []

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "labels/list.html",
        context={
            "user": user,
            "project": project,
            "labels": labels,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/projects/{project_id}/labels")
async def create_label(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    from models.label import Label

    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    form_data_raw = await request.form()
    label_name = form_data_raw.get("name", "").strip()
    label_color = form_data_raw.get("color", "#3b82f6").strip()

    if not label_name:
        response = RedirectResponse(
            url=f"/projects/{project_id}/labels",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, "Label name is required.", "error")
        return response

    existing = await db.execute(
        select(Label).where(
            Label.project_id == project_id,
            func.lower(Label.name) == label_name.lower(),
        )
    )
    if existing.scalars().first():
        response = RedirectResponse(
            url=f"/projects/{project_id}/labels",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        set_flash_message(response, f"Label '{label_name}' already exists in this project.", "error")
        return response

    label = Label(
        id=str(uuid.uuid4()),
        name=label_name,
        color=label_color,
        project_id=project_id,
    )
    db.add(label)

    await _create_audit_log(
        db=db,
        entity_type="Label",
        entity_id=label.id,
        action="CREATE",
        user_id=user.id,
        details=json.dumps({"name": label_name, "color": label_color, "project_id": project_id}),
    )

    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}/labels",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"Label '{label_name}' created successfully.", "success")
    return response


@router.post("/projects/{project_id}/labels/{label_id}/delete")
async def delete_label(
    request: Request,
    project_id: str,
    label_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    from models.label import Label

    result = await db.execute(
        select(Label).where(Label.id == label_id, Label.project_id == project_id)
    )
    label = result.scalars().first()

    if not label:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found.")

    label_name = label.name

    await _create_audit_log(
        db=db,
        entity_type="Label",
        entity_id=label_id,
        action="DELETE",
        user_id=user.id,
        details=json.dumps({"name": label_name, "project_id": project_id}),
    )

    await db.delete(label)
    await db.flush()

    response = RedirectResponse(
        url=f"/projects/{project_id}/labels",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"Label '{label_name}' deleted.", "success")
    return response


@router.get("/projects/{project_id}/analytics")
async def project_analytics(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.tickets).selectinload(Ticket.assignee),
            selectinload(Project.tickets).selectinload(Ticket.labels),
            selectinload(Project.sprints),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    tickets = project.tickets if project.tickets else []

    status_counts = {}
    for ticket in tickets:
        s = ticket.status or "Unknown"
        status_counts[s] = status_counts.get(s, 0) + 1

    tickets_by_status = [{"status": k, "count": v} for k, v in status_counts.items()]
    tickets_by_status.sort(key=lambda x: x["count"], reverse=True)

    priority_counts = {}
    for ticket in tickets:
        p = ticket.priority or "Unknown"
        priority_counts[p] = priority_counts.get(p, 0) + 1

    type_counts = {}
    for ticket in tickets:
        t = ticket.type or "Unknown"
        type_counts[t] = type_counts.get(t, 0) + 1

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "projects/analytics.html",
        context={
            "user": user,
            "project": project,
            "tickets_by_status": tickets_by_status,
            "priority_counts": priority_counts,
            "type_counts": type_counts,
            "total_tickets": len(tickets),
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.get("/projects/{project_id}/kanban")
async def project_kanban_redirect(
    request: Request,
    project_id: str,
):
    return RedirectResponse(
        url=f"/projects/{project_id}/board",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/projects/{project_id}/board")
async def project_board(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_redirect(request, db)

    from models.label import Label

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.department),
            selectinload(Project.sprints),
            selectinload(Project.project_members).selectinload(ProjectMember.user),
            selectinload(Project.labels),
        )
    )
    project = result.scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    sprint_id = request.query_params.get("sprint_id", "")
    assignee_id = request.query_params.get("assignee_id", "")
    priority = request.query_params.get("priority", "")
    ticket_type = request.query_params.get("type", "")
    label_id = request.query_params.get("label_id", "")

    ticket_query = (
        select(Ticket)
        .where(Ticket.project_id == project_id)
        .options(
            selectinload(Ticket.assignee),
            selectinload(Ticket.labels),
            selectinload(Ticket.sprint),
        )
    )

    if sprint_id:
        ticket_query = ticket_query.where(Ticket.sprint_id == sprint_id)
    if assignee_id:
        ticket_query = ticket_query.where(Ticket.assignee_id == assignee_id)
    if priority:
        ticket_query = ticket_query.where(Ticket.priority == priority)
    if ticket_type:
        ticket_query = ticket_query.where(Ticket.type == ticket_type)

    ticket_result = await db.execute(ticket_query)
    all_tickets = ticket_result.scalars().unique().all()

    if label_id:
        all_tickets = [t for t in all_tickets if any(l.id == label_id for l in (t.labels or []))]

    columns = {
        "open": [],
        "in_progress": [],
        "in_review": [],
        "qa_testing": [],
        "closed": [],
    }

    status_map = {
        "Open": "open",
        "In Progress": "in_progress",
        "In Review": "in_review",
        "QA Testing": "qa_testing",
        "Closed": "closed",
        "Reopened": "open",
    }

    for ticket in all_tickets:
        col_key = status_map.get(ticket.status, "open")
        columns[col_key].append(ticket)

    sprints = project.sprints if project.sprints else []
    members = project.members if project.members else []
    labels = project.labels if project.labels else []

    current_sprint = None
    for s in sprints:
        if s.status == "Active":
            current_sprint = s
            break

    filters = {
        "sprint_id": sprint_id,
        "assignee_id": assignee_id,
        "priority": priority,
        "type": ticket_type,
        "label_id": label_id,
    }

    total_tickets = len(all_tickets)

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "projects/board.html",
        context={
            "user": user,
            "project": project,
            "columns": columns,
            "sprints": sprints,
            "members": members,
            "labels": labels,
            "current_sprint": current_sprint,
            "filters": filters,
            "total_tickets": total_tickets,
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
):
    user = await _get_user_or_redirect(request, db)

    if user.role not in ["Super Admin", "Project Manager", "Developer", "QA"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update ticket status.",
        )

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalars().first()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    form_data_raw = await request.form()
    new_status = form_data_raw.get("status", "").strip()

    valid_statuses = ["Open", "In Progress", "In Review", "QA Testing", "Closed", "Reopened"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    old_status = ticket.status
    if old_status != new_status:
        ticket.status = new_status

        await _create_audit_log(
            db=db,
            entity_type="Ticket",
            entity_id=ticket_id,
            action="UPDATE",
            user_id=user.id,
            details=json.dumps({"status": {"old": old_status, "new": new_status}}),
        )

        await db.flush()

    referer = request.headers.get("referer", "")
    if "/board" in referer:
        return Response(status_code=status.HTTP_200_OK)

    response = RedirectResponse(
        url=f"/projects/{project_id}/tickets/{ticket_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_flash_message(response, f"Ticket status updated to '{new_status}'.", "success")
    return response


def _generate_project_key(name: str) -> str:
    words = name.strip().upper().split()
    if len(words) >= 2:
        key = "".join(w[0] for w in words[:4])
    else:
        key = name.strip().upper()[:4]
    key = key.replace(" ", "")
    return key[:10]