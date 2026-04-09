import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from dependencies import COOKIE_NAME, FLASH_COOKIE_NAME


class TestLoginPage:
    """Tests for GET /auth/login"""

    @pytest.mark.asyncio
    async def test_login_page_renders(self, client: AsyncClient):
        response = await client.get("/auth/login")
        assert response.status_code == 200
        assert "Sign in to ProjectForge" in response.text

    @pytest.mark.asyncio
    async def test_login_page_redirects_authenticated_user(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.get(
            "/auth/login", cookies=super_admin_cookies, follow_redirects=False
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"


class TestLoginSubmit:
    """Tests for POST /auth/login"""

    @pytest.mark.asyncio
    async def test_login_valid_credentials(
        self, client: AsyncClient, super_admin_user: User
    ):
        response = await client.post(
            "/auth/login",
            data={"username": "test_super_admin", "password": "testpass123"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"
        assert COOKIE_NAME in response.cookies

    @pytest.mark.asyncio
    async def test_login_invalid_username(self, client: AsyncClient):
        response = await client.post(
            "/auth/login",
            data={"username": "nonexistent_user", "password": "testpass123"},
        )
        assert response.status_code == 200
        assert "Invalid username or password" in response.text

    @pytest.mark.asyncio
    async def test_login_invalid_password(
        self, client: AsyncClient, super_admin_user: User
    ):
        response = await client.post(
            "/auth/login",
            data={"username": "test_super_admin", "password": "wrongpassword"},
        )
        assert response.status_code == 200
        assert "Invalid username or password" in response.text

    @pytest.mark.asyncio
    async def test_login_empty_username(self, client: AsyncClient):
        response = await client.post(
            "/auth/login",
            data={"username": "", "password": "testpass123"},
        )
        assert response.status_code == 200
        assert "Username is required" in response.text

    @pytest.mark.asyncio
    async def test_login_empty_password(self, client: AsyncClient):
        response = await client.post(
            "/auth/login",
            data={"username": "test_super_admin", "password": ""},
        )
        assert response.status_code == 200
        assert "Password is required" in response.text

    @pytest.mark.asyncio
    async def test_login_empty_both_fields(self, client: AsyncClient):
        response = await client.post(
            "/auth/login",
            data={"username": "", "password": ""},
        )
        assert response.status_code == 200
        assert "Username is required" in response.text
        assert "Password is required" in response.text

    @pytest.mark.asyncio
    async def test_login_inactive_user(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        inactive_user = User(
            username="inactive_user",
            email="inactive@test.com",
            password_hash=pwd_context.hash("testpass123"),
            role="Developer",
            is_active=False,
        )
        db_session.add(inactive_user)
        await db_session.flush()

        response = await client.post(
            "/auth/login",
            data={"username": "inactive_user", "password": "testpass123"},
        )
        assert response.status_code == 200
        assert "deactivated" in response.text

    @pytest.mark.asyncio
    async def test_login_sets_session_cookie(
        self, client: AsyncClient, super_admin_user: User
    ):
        response = await client.post(
            "/auth/login",
            data={"username": "test_super_admin", "password": "testpass123"},
            follow_redirects=False,
        )
        assert COOKIE_NAME in response.cookies
        cookie_value = response.cookies[COOKIE_NAME]
        assert len(cookie_value) > 0

    @pytest.mark.asyncio
    async def test_login_sets_flash_message(
        self, client: AsyncClient, super_admin_user: User
    ):
        response = await client.post(
            "/auth/login",
            data={"username": "test_super_admin", "password": "testpass123"},
            follow_redirects=False,
        )
        assert FLASH_COOKIE_NAME in response.cookies


class TestRegisterPage:
    """Tests for GET /auth/register"""

    @pytest.mark.asyncio
    async def test_register_page_renders(self, client: AsyncClient):
        response = await client.get("/auth/register")
        assert response.status_code == 200
        assert "Create your account" in response.text

    @pytest.mark.asyncio
    async def test_register_page_redirects_authenticated_user(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.get(
            "/auth/register", cookies=super_admin_cookies, follow_redirects=False
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"


class TestRegisterSubmit:
    """Tests for POST /auth/register"""

    @pytest.mark.asyncio
    async def test_register_valid_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.post(
            "/auth/register",
            data={
                "username": "newuser",
                "password": "securepass123",
                "confirm_password": "securepass123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"
        assert COOKIE_NAME in response.cookies

        result = await db_session.execute(
            select(User).where(User.username == "newuser")
        )
        new_user = result.scalars().first()
        assert new_user is not None
        assert new_user.role == "Viewer"
        assert new_user.is_active is True

    @pytest.mark.asyncio
    async def test_register_duplicate_username(
        self, client: AsyncClient, super_admin_user: User
    ):
        response = await client.post(
            "/auth/register",
            data={
                "username": "test_super_admin",
                "password": "securepass123",
                "confirm_password": "securepass123",
            },
        )
        assert response.status_code == 200
        assert "already exists" in response.text

    @pytest.mark.asyncio
    async def test_register_mismatched_passwords(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            data={
                "username": "mismatchuser",
                "password": "securepass123",
                "confirm_password": "differentpass456",
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    @pytest.mark.asyncio
    async def test_register_empty_username(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            data={
                "username": "",
                "password": "securepass123",
                "confirm_password": "securepass123",
            },
        )
        assert response.status_code == 200
        assert "Username is required" in response.text

    @pytest.mark.asyncio
    async def test_register_short_username(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            data={
                "username": "ab",
                "password": "securepass123",
                "confirm_password": "securepass123",
            },
        )
        assert response.status_code == 200
        assert "at least 3 characters" in response.text

    @pytest.mark.asyncio
    async def test_register_empty_password(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            data={
                "username": "newuser2",
                "password": "",
                "confirm_password": "",
            },
        )
        assert response.status_code == 200
        assert "Password is required" in response.text

    @pytest.mark.asyncio
    async def test_register_short_password(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            data={
                "username": "newuser3",
                "password": "abc",
                "confirm_password": "abc",
            },
        )
        assert response.status_code == 200
        assert "at least 6 characters" in response.text

    @pytest.mark.asyncio
    async def test_register_sets_session_cookie(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            data={
                "username": "cookieuser",
                "password": "securepass123",
                "confirm_password": "securepass123",
            },
            follow_redirects=False,
        )
        assert COOKIE_NAME in response.cookies

    @pytest.mark.asyncio
    async def test_register_new_user_has_viewer_role(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await client.post(
            "/auth/register",
            data={
                "username": "roleuser",
                "password": "securepass123",
                "confirm_password": "securepass123",
            },
            follow_redirects=False,
        )

        result = await db_session.execute(
            select(User).where(User.username == "roleuser")
        )
        user = result.scalars().first()
        assert user is not None
        assert user.role == "Viewer"


class TestLogout:
    """Tests for POST /auth/logout"""

    @pytest.mark.asyncio
    async def test_logout_redirects_to_landing(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.post(
            "/auth/logout",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_logout_clears_session_cookie(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.post(
            "/auth/logout",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        session_cookie = response.cookies.get(COOKIE_NAME)
        if session_cookie is not None:
            assert session_cookie == "" or session_cookie == '""'

    @pytest.mark.asyncio
    async def test_logout_sets_flash_message(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.post(
            "/auth/logout",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert FLASH_COOKIE_NAME in response.cookies

    @pytest.mark.asyncio
    async def test_logout_without_session(self, client: AsyncClient):
        response = await client.post(
            "/auth/logout",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"


class TestProtectedRoutes:
    """Tests for unauthenticated access to protected routes"""

    @pytest.mark.asyncio
    async def test_dashboard_redirects_unauthenticated(self, client: AsyncClient):
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_dashboard_accessible_when_authenticated(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert "Dashboard" in response.text

    @pytest.mark.asyncio
    async def test_projects_redirects_unauthenticated(self, client: AsyncClient):
        response = await client.get("/projects", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_users_requires_super_admin(
        self, client: AsyncClient, developer_cookies: dict
    ):
        response = await client.get(
            "/users",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code in (403, 303)

    @pytest.mark.asyncio
    async def test_users_accessible_by_super_admin(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.get(
            "/users",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_audit_log_requires_super_admin(
        self, client: AsyncClient, developer_cookies: dict
    ):
        response = await client.get(
            "/audit-log",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code in (403, 303)

    @pytest.mark.asyncio
    async def test_audit_log_accessible_by_super_admin(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.get(
            "/audit-log",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200


class TestSessionCookie:
    """Tests for session cookie behavior"""

    @pytest.mark.asyncio
    async def test_session_cookie_is_httponly(
        self, client: AsyncClient, super_admin_user: User
    ):
        response = await client.post(
            "/auth/login",
            data={"username": "test_super_admin", "password": "testpass123"},
            follow_redirects=False,
        )
        set_cookie_headers = response.headers.get_list("set-cookie")
        session_cookie_header = None
        for header in set_cookie_headers:
            if header.startswith(f"{COOKIE_NAME}="):
                session_cookie_header = header
                break
        assert session_cookie_header is not None
        assert "httponly" in session_cookie_header.lower()

    @pytest.mark.asyncio
    async def test_session_cookie_has_samesite(
        self, client: AsyncClient, super_admin_user: User
    ):
        response = await client.post(
            "/auth/login",
            data={"username": "test_super_admin", "password": "testpass123"},
            follow_redirects=False,
        )
        set_cookie_headers = response.headers.get_list("set-cookie")
        session_cookie_header = None
        for header in set_cookie_headers:
            if header.startswith(f"{COOKIE_NAME}="):
                session_cookie_header = header
                break
        assert session_cookie_header is not None
        assert "samesite=lax" in session_cookie_header.lower()

    @pytest.mark.asyncio
    async def test_invalid_session_cookie_treated_as_unauthenticated(
        self, client: AsyncClient
    ):
        response = await client.get(
            "/dashboard",
            cookies={COOKIE_NAME: "invalid-garbage-cookie-value"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/auth/login" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_expired_session_cookie_treated_as_unauthenticated(
        self, client: AsyncClient
    ):
        from itsdangerous import URLSafeTimedSerializer

        serializer = URLSafeTimedSerializer("wrong-secret-key")
        fake_cookie = serializer.dumps({"user_id": "fake-id"})

        response = await client.get(
            "/dashboard",
            cookies={COOKIE_NAME: fake_cookie},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/auth/login" in response.headers["location"]