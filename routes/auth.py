import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from database import get_db
from dependencies import (
    get_session_user,
    set_session,
    clear_session,
    set_flash_message,
    get_flash_messages,
    clear_flash_messages,
)
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get("/login")
async def login_page(
    request: Request,
    user: Optional[User] = Depends(get_session_user),
):
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=303)

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "auth/login.html",
        context={
            "user": None,
            "error": None,
            "errors": None,
            "username": "",
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    errors = []

    if not username or not username.strip():
        errors.append("Username is required.")
    if not password:
        errors.append("Password is required.")

    if errors:
        messages = get_flash_messages(request)
        response = templates.TemplateResponse(
            request,
            "auth/login.html",
            context={
                "user": None,
                "error": None,
                "errors": errors,
                "username": username,
                "messages": messages,
            },
        )
        clear_flash_messages(response)
        return response

    username = username.strip()

    try:
        result = await db.execute(
            select(User).where(User.username == username)
        )
        db_user = result.scalars().first()
    except Exception:
        logger.exception("Database error during login lookup")
        db_user = None

    if db_user is None or not pwd_context.verify(password, db_user.password_hash):
        messages = get_flash_messages(request)
        response = templates.TemplateResponse(
            request,
            "auth/login.html",
            context={
                "user": None,
                "error": "Invalid username or password.",
                "errors": None,
                "username": username,
                "messages": messages,
            },
        )
        clear_flash_messages(response)
        return response

    if not db_user.is_active:
        messages = get_flash_messages(request)
        response = templates.TemplateResponse(
            request,
            "auth/login.html",
            context={
                "user": None,
                "error": "Your account has been deactivated. Please contact an administrator.",
                "errors": None,
                "username": username,
                "messages": messages,
            },
        )
        clear_flash_messages(response)
        return response

    response = RedirectResponse(url="/dashboard", status_code=303)
    set_session(response, db_user.id)
    set_flash_message(response, f"Welcome back, {db_user.username}!", "success")
    logger.info("User '%s' logged in successfully", db_user.username)
    return response


@router.get("/register")
async def register_page(
    request: Request,
    user: Optional[User] = Depends(get_session_user),
):
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=303)

    messages = get_flash_messages(request)
    response = templates.TemplateResponse(
        request,
        "auth/register.html",
        context={
            "user": None,
            "errors": None,
            "form_data": None,
            "messages": messages,
        },
    )
    clear_flash_messages(response)
    return response


@router.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    errors = []
    form_data = {
        "username": username,
    }

    username_stripped = username.strip() if username else ""

    if not username_stripped:
        errors.append("Username is required.")
    elif len(username_stripped) < 3:
        errors.append("Username must be at least 3 characters long.")
    elif len(username_stripped) > 150:
        errors.append("Username must be at most 150 characters long.")

    if not password:
        errors.append("Password is required.")
    elif len(password) < 6:
        errors.append("Password must be at least 6 characters long.")

    if password and confirm_password != password:
        errors.append("Passwords do not match.")

    if not errors and username_stripped:
        try:
            result = await db.execute(
                select(User).where(User.username == username_stripped)
            )
            existing_user = result.scalars().first()
            if existing_user is not None:
                errors.append("Username already exists. Please choose a different one.")
        except Exception:
            logger.exception("Database error during registration uniqueness check")
            errors.append("An unexpected error occurred. Please try again.")

    if errors:
        messages = get_flash_messages(request)
        response = templates.TemplateResponse(
            request,
            "auth/register.html",
            context={
                "user": None,
                "errors": errors,
                "form_data": form_data,
                "messages": messages,
            },
        )
        clear_flash_messages(response)
        return response

    try:
        password_hash = pwd_context.hash(password)
        new_user = User(
            username=username_stripped,
            password_hash=password_hash,
            role="Viewer",
            is_active=True,
        )
        db.add(new_user)
        await db.flush()

        response = RedirectResponse(url="/dashboard", status_code=303)
        set_session(response, new_user.id)
        set_flash_message(response, "Account created successfully! Welcome to ProjectForge.", "success")
        logger.info("New user '%s' registered successfully with role 'Viewer'", username_stripped)
        return response

    except Exception:
        logger.exception("Error creating user during registration")
        await db.rollback()
        messages = get_flash_messages(request)
        response = templates.TemplateResponse(
            request,
            "auth/register.html",
            context={
                "user": None,
                "errors": ["An unexpected error occurred during registration. Please try again."],
                "form_data": form_data,
                "messages": messages,
            },
        )
        clear_flash_messages(response)
        return response


@router.post("/logout")
async def logout(
    request: Request,
):
    response = RedirectResponse(url="/", status_code=303)
    clear_session(response)
    set_flash_message(response, "You have been logged out successfully.", "info")
    return response