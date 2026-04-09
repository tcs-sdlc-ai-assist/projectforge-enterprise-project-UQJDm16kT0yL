import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import logging
from typing import Optional, List

from fastapi import Request, Response, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from config import settings
from database import get_db
from models.user import User
from models.project import ProjectMember

logger = logging.getLogger(__name__)

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

COOKIE_NAME = "session"
FLASH_COOKIE_NAME = "flash_messages"


def create_session_cookie(user_id: str) -> str:
    return serializer.dumps({"user_id": user_id})


def decode_session_cookie(cookie_value: str) -> Optional[dict]:
    try:
        data = serializer.loads(cookie_value, max_age=settings.TOKEN_EXPIRY_SECONDS)
        return data
    except SignatureExpired:
        logger.warning("Session cookie expired")
        return None
    except BadSignature:
        logger.warning("Invalid session cookie signature")
        return None
    except Exception:
        logger.warning("Failed to decode session cookie")
        return None


async def get_session_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    cookie_value = request.cookies.get(COOKIE_NAME)
    if not cookie_value:
        return None

    session_data = decode_session_cookie(cookie_value)
    if not session_data or "user_id" not in session_data:
        return None

    user_id = session_data["user_id"]

    try:
        result = await db.execute(
            select(User)
            .where(User.id == user_id)
            .where(User.is_active == True)
            .options(selectinload(User.department))
        )
        user = result.scalars().first()
        return user
    except Exception:
        logger.exception("Error loading user from session")
        return None


async def require_login(
    request: Request,
    user: Optional[User] = Depends(get_session_user),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
        )
    return user


def require_role(allowed_roles: List[str]):
    async def role_dependency(
        request: Request,
        user: User = Depends(require_login),
    ) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )
        return user

    return role_dependency


async def require_super_admin(
    request: Request,
    user: User = Depends(require_login),
) -> User:
    if user.role != "Super Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required.",
        )
    return user


async def require_project_manager_or_above(
    request: Request,
    user: User = Depends(require_login),
) -> User:
    if user.role not in ["Super Admin", "Project Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project Manager or Super Admin access required.",
        )
    return user


async def require_project_member(
    request: Request,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db),
) -> User:
    project_id = request.path_params.get("project_id")
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project ID is required.",
        )

    if user.role == "Super Admin":
        return user

    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .where(ProjectMember.user_id == user.id)
    )
    membership = result.scalars().first()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this project.",
        )

    return user


def set_flash_message(response: Response, message: str, category: str = "info") -> None:
    flash_data = [{"text": message, "category": category}]
    try:
        encoded = json.dumps(flash_data)
        response.set_cookie(
            key=FLASH_COOKIE_NAME,
            value=encoded,
            max_age=60,
            httponly=True,
            samesite="lax",
            path="/",
        )
    except Exception:
        logger.exception("Failed to set flash message cookie")


def add_flash_message(request: Request, response: Response, message: str, category: str = "info") -> None:
    existing_messages = get_flash_messages(request, consume=False)
    existing_messages.append({"text": message, "category": category})
    try:
        encoded = json.dumps(existing_messages)
        response.set_cookie(
            key=FLASH_COOKIE_NAME,
            value=encoded,
            max_age=60,
            httponly=True,
            samesite="lax",
            path="/",
        )
    except Exception:
        logger.exception("Failed to add flash message cookie")


def get_flash_messages(request: Request, consume: bool = True) -> list:
    cookie_value = request.cookies.get(FLASH_COOKIE_NAME)
    if not cookie_value:
        return []

    try:
        messages = json.loads(cookie_value)
        if not isinstance(messages, list):
            return []
        return messages
    except (json.JSONDecodeError, Exception):
        return []


def clear_flash_messages(response: Response) -> None:
    response.delete_cookie(
        key=FLASH_COOKIE_NAME,
        path="/",
    )


def set_session(response: Response, user_id: str) -> None:
    cookie_value = create_session_cookie(user_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        max_age=settings.TOKEN_EXPIRY_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
    )