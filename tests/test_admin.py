import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from models.department import Department
from models.audit_log import AuditLog
from tests.conftest import _create_user, _auth_cookies


# ─── Department CRUD Tests ─────────────────────────────────────────────────────


class TestDepartmentList:
    """Test department listing."""

    @pytest.mark.asyncio
    async def test_list_departments_authenticated(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
    ):
        response = await client.get("/departments", cookies=super_admin_cookies)
        assert response.status_code == 200
        assert test_department.name in response.text

    @pytest.mark.asyncio
    async def test_list_departments_as_developer(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_department: Department,
    ):
        response = await client.get("/departments", cookies=developer_cookies)
        assert response.status_code == 200
        assert test_department.name in response.text

    @pytest.mark.asyncio
    async def test_list_departments_unauthenticated_redirects(
        self,
        client: AsyncClient,
    ):
        response = await client.get("/departments", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


class TestDepartmentCreate:
    """Test department creation (Super Admin only)."""

    @pytest.mark.asyncio
    async def test_create_department_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": "Marketing", "code": "MKT"},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/departments" in response.headers.get("location", "")

        result = await db_session.execute(
            select(Department).where(Department.code == "MKT")
        )
        department = result.scalars().first()
        assert department is not None
        assert department.name == "Marketing"

    @pytest.mark.asyncio
    async def test_create_department_creates_audit_log(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        await client.post(
            "/departments/create",
            data={"name": "Sales", "code": "SLS"},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )

        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "Department",
                AuditLog.action == "CREATE",
            )
        )
        audit_log = result.scalars().first()
        assert audit_log is not None
        assert audit_log.user_id == super_admin_user.id

    @pytest.mark.asyncio
    async def test_create_department_duplicate_name_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": test_department.name, "code": "DUP"},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "already exists" in response.text

    @pytest.mark.asyncio
    async def test_create_department_duplicate_code_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": "Unique Name", "code": test_department.code},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "already exists" in response.text

    @pytest.mark.asyncio
    async def test_create_department_empty_name_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": "", "code": "EMP"},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "required" in response.text.lower()

    @pytest.mark.asyncio
    async def test_create_department_as_project_manager_forbidden(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": "Forbidden Dept", "code": "FBD"},
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_department_as_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": "Dev Dept", "code": "DEV"},
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_department_as_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": "Viewer Dept", "code": "VWR"},
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403


class TestDepartmentEdit:
    """Test department editing (Super Admin only)."""

    @pytest.mark.asyncio
    async def test_edit_department_form_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
    ):
        response = await client.get(
            f"/departments/{test_department.id}/edit",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_edit_department_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/edit",
            data={"name": "Updated Engineering", "code": "UENG"},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        await db_session.refresh(test_department)
        assert test_department.name == "Updated Engineering"
        assert test_department.code == "UENG"

    @pytest.mark.asyncio
    async def test_edit_department_as_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_department: Department,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/edit",
            data={"name": "Hacked", "code": "HCK"},
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_nonexistent_department_redirects(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.post(
            "/departments/nonexistent-id/edit",
            data={"name": "Ghost", "code": "GHT"},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/departments" in response.headers.get("location", "")


class TestDepartmentDelete:
    """Test department deletion (Super Admin only)."""

    @pytest.mark.asyncio
    async def test_delete_empty_department_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        department = Department(name="Empty Dept", code="EMPT")
        db_session.add(department)
        await db_session.flush()
        dept_id = department.id

        response = await client.post(
            f"/departments/{dept_id}/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Department).where(Department.id == dept_id)
        )
        assert result.scalars().first() is None

    @pytest.mark.asyncio
    async def test_delete_department_with_members_blocked(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
        super_admin_user: User,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303
        location = response.headers.get("location", "")
        assert "/departments" in location

    @pytest.mark.asyncio
    async def test_delete_department_as_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_department: Department,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/delete",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_department_as_project_manager_forbidden(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        test_department: Department,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/delete",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_nonexistent_department_redirects(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.post(
            "/departments/nonexistent-id/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303


class TestDepartmentSetHead:
    """Test setting department head."""

    @pytest.mark.asyncio
    async def test_set_department_head_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
        developer_user: User,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/set-head",
            data={"head_id": developer_user.id},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        await db_session.refresh(test_department)
        assert test_department.head_id == developer_user.id

    @pytest.mark.asyncio
    async def test_set_department_head_as_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_department: Department,
        developer_user: User,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/set-head",
            data={"head_id": developer_user.id},
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_set_department_head_empty_id_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/set-head",
            data={"head_id": ""},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303


# ─── User Management Tests ─────────────────────────────────────────────────────


class TestUserList:
    """Test user listing."""

    @pytest.mark.asyncio
    async def test_list_users_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
    ):
        response = await client.get("/users", cookies=super_admin_cookies)
        assert response.status_code == 200
        assert super_admin_user.username in response.text

    @pytest.mark.asyncio
    async def test_list_users_as_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
    ):
        response = await client.get(
            "/users",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_as_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
    ):
        response = await client.get(
            "/users",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_as_qa_forbidden(
        self,
        client: AsyncClient,
        qa_cookies: dict,
    ):
        response = await client.get(
            "/users",
            cookies=qa_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_unauthenticated_redirects(
        self,
        client: AsyncClient,
    ):
        response = await client.get("/users", follow_redirects=False)
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_list_users_filter_by_role(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
    ):
        response = await client.get(
            "/users?role=Super+Admin",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert super_admin_user.username in response.text

    @pytest.mark.asyncio
    async def test_list_users_filter_by_search(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
    ):
        response = await client.get(
            f"/users?search={super_admin_user.username}",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert super_admin_user.username in response.text

    @pytest.mark.asyncio
    async def test_list_users_filter_by_active_status(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.get(
            "/users?status=active",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_users_filter_by_inactive_status(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.get(
            "/users?status=inactive",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200


class TestUserCreate:
    """Test user creation (Super Admin only)."""

    @pytest.mark.asyncio
    async def test_create_user_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": "new_user",
                "email": "new_user@test.com",
                "password": "password123",
                "role": "Developer",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/users" in response.headers.get("location", "")

        result = await db_session.execute(
            select(User).where(User.username == "new_user")
        )
        new_user = result.scalars().first()
        assert new_user is not None
        assert new_user.role == "Developer"
        assert new_user.is_active is True

    @pytest.mark.asyncio
    async def test_create_user_with_department(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": "dept_user",
                "email": "dept_user@test.com",
                "password": "password123",
                "role": "QA",
                "department_id": test_department.id,
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(User).where(User.username == "dept_user")
        )
        new_user = result.scalars().first()
        assert new_user is not None
        assert new_user.department_id == test_department.id
        assert new_user.role == "QA"

    @pytest.mark.asyncio
    async def test_create_user_creates_audit_log(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        await client.post(
            "/users/create",
            data={
                "username": "audit_user",
                "email": "audit_user@test.com",
                "password": "password123",
                "role": "Viewer",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )

        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "User",
                AuditLog.action == "CREATE",
            )
        )
        audit_logs = result.scalars().all()
        assert len(audit_logs) > 0
        latest = audit_logs[-1]
        assert latest.user_id == super_admin_user.id

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": super_admin_user.username,
                "email": "different@test.com",
                "password": "password123",
                "role": "Developer",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_create_user_short_username_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": "ab",
                "email": "short@test.com",
                "password": "password123",
                "role": "Developer",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_create_user_short_password_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": "shortpw_user",
                "email": "shortpw@test.com",
                "password": "12345",
                "role": "Developer",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_create_user_invalid_role_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": "badrole_user",
                "email": "badrole@test.com",
                "password": "password123",
                "role": "InvalidRole",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_create_user_as_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": "hacker_user",
                "email": "hacker@test.com",
                "password": "password123",
                "role": "Developer",
                "department_id": "",
            },
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_as_project_manager_forbidden(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": "pm_created_user",
                "email": "pm_created@test.com",
                "password": "password123",
                "role": "Developer",
                "department_id": "",
            },
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403


class TestUserEdit:
    """Test user editing (Super Admin only)."""

    @pytest.mark.asyncio
    async def test_edit_user_form_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        developer_user: User,
    ):
        response = await client.get(
            f"/users/{developer_user.id}/edit",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert developer_user.username in response.text

    @pytest.mark.asyncio
    async def test_edit_user_role_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        developer_user: User,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/edit",
            data={
                "role": "Project Manager",
                "department_id": "",
                "display_name": "",
                "email": developer_user.email or "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        await db_session.refresh(developer_user)
        assert developer_user.role == "Project Manager"

    @pytest.mark.asyncio
    async def test_edit_user_department_assignment(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        developer_user: User,
        test_department: Department,
        db_session: AsyncSession,
    ):
        new_dept = Department(name="New Dept", code="NDPT")
        db_session.add(new_dept)
        await db_session.flush()

        response = await client.post(
            f"/users/{developer_user.id}/edit",
            data={
                "role": developer_user.role,
                "department_id": new_dept.id,
                "display_name": "",
                "email": developer_user.email or "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        await db_session.refresh(developer_user)
        assert developer_user.department_id == new_dept.id

    @pytest.mark.asyncio
    async def test_edit_user_display_name(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        developer_user: User,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/edit",
            data={
                "role": developer_user.role,
                "department_id": "",
                "display_name": "John Developer",
                "email": developer_user.email or "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        await db_session.refresh(developer_user)
        assert developer_user.display_name == "John Developer"

    @pytest.mark.asyncio
    async def test_edit_user_creates_audit_log(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
        developer_user: User,
        db_session: AsyncSession,
    ):
        await client.post(
            f"/users/{developer_user.id}/edit",
            data={
                "role": "QA",
                "department_id": "",
                "display_name": "",
                "email": developer_user.email or "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )

        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "User",
                AuditLog.action == "UPDATE",
                AuditLog.entity_id == developer_user.id,
            )
        )
        audit_log = result.scalars().first()
        assert audit_log is not None
        assert audit_log.user_id == super_admin_user.id

    @pytest.mark.asyncio
    async def test_edit_user_no_changes(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        developer_user: User,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/edit",
            data={
                "role": developer_user.role,
                "department_id": developer_user.department_id or "",
                "display_name": developer_user.display_name or "",
                "email": developer_user.email or "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_edit_nonexistent_user_redirects(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.get(
            "/users/nonexistent-id/edit",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/users" in response.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_edit_user_as_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        super_admin_user: User,
    ):
        response = await client.post(
            f"/users/{super_admin_user.id}/edit",
            data={
                "role": "Viewer",
                "department_id": "",
                "display_name": "",
                "email": "",
            },
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_user_as_qa_forbidden(
        self,
        client: AsyncClient,
        qa_cookies: dict,
        developer_user: User,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/edit",
            data={
                "role": "Viewer",
                "department_id": "",
                "display_name": "",
                "email": "",
            },
            cookies=qa_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_user_duplicate_email_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        developer_user: User,
        super_admin_user: User,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/edit",
            data={
                "role": developer_user.role,
                "department_id": "",
                "display_name": "",
                "email": super_admin_user.email,
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "already in use" in response.text


class TestUserToggleActive:
    """Test user activation/deactivation (Super Admin only)."""

    @pytest.mark.asyncio
    async def test_deactivate_user_as_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        developer_user: User,
        db_session: AsyncSession,
    ):
        assert developer_user.is_active is True

        response = await client.post(
            f"/users/{developer_user.id}/toggle-active",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        await db_session.refresh(developer_user)
        assert developer_user.is_active is False

    @pytest.mark.asyncio
    async def test_activate_inactive_user(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        inactive_user = await _create_user(
            db_session,
            username="inactive_user",
            password="testpass123",
            role="Developer",
        )
        inactive_user.is_active = False
        await db_session.flush()

        response = await client.post(
            f"/users/{inactive_user.id}/toggle-active",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        await db_session.refresh(inactive_user)
        assert inactive_user.is_active is True

    @pytest.mark.asyncio
    async def test_toggle_creates_audit_log(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
        developer_user: User,
        db_session: AsyncSession,
    ):
        await client.post(
            f"/users/{developer_user.id}/toggle-active",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )

        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "User",
                AuditLog.action == "UPDATE",
                AuditLog.entity_id == developer_user.id,
            )
        )
        audit_logs = result.scalars().all()
        assert len(audit_logs) > 0

    @pytest.mark.asyncio
    async def test_cannot_deactivate_self(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
    ):
        response = await client.post(
            f"/users/{super_admin_user.id}/toggle-active",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_toggle_nonexistent_user_redirects(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.post(
            "/users/nonexistent-id/toggle-active",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_toggle_user_as_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        qa_user: User,
    ):
        response = await client.post(
            f"/users/{qa_user.id}/toggle-active",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_toggle_user_as_project_manager_forbidden(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        developer_user: User,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/toggle-active",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_toggle_user_as_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        developer_user: User,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/toggle-active",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403


# ─── Role Assignment Tests ──────────────────────────────────────────────────────


class TestRoleAssignment:
    """Test role assignment scenarios."""

    @pytest.mark.asyncio
    async def test_assign_all_valid_roles(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        valid_roles = ["Super Admin", "Project Manager", "Developer", "QA", "Viewer"]

        for i, role in enumerate(valid_roles):
            user = await _create_user(
                db_session,
                username=f"role_test_user_{i}",
                password="testpass123",
                role="Viewer",
            )

            response = await client.post(
                f"/users/{user.id}/edit",
                data={
                    "role": role,
                    "department_id": "",
                    "display_name": "",
                    "email": user.email or "",
                },
                cookies=super_admin_cookies,
                follow_redirects=False,
            )
            assert response.status_code == 303

            await db_session.refresh(user)
            assert user.role == role

    @pytest.mark.asyncio
    async def test_assign_invalid_role_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        developer_user: User,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/edit",
            data={
                "role": "NonExistentRole",
                "department_id": "",
                "display_name": "",
                "email": developer_user.email or "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Invalid role" in response.text


# ─── Unauthorized Access Tests ──────────────────────────────────────────────────


class TestUnauthorizedAccess:
    """Test that non-Super Admin roles cannot access admin routes."""

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_access_users(
        self,
        client: AsyncClient,
    ):
        response = await client.get("/users", follow_redirects=False)
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_create_user(
        self,
        client: AsyncClient,
    ):
        response = await client.post(
            "/users/create",
            data={
                "username": "anon_user",
                "email": "anon@test.com",
                "password": "password123",
                "role": "Developer",
                "department_id": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_create_department(
        self,
        client: AsyncClient,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": "Anon Dept", "code": "ANO"},
            follow_redirects=False,
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_viewer_cannot_access_user_management(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
    ):
        response = await client.get(
            "/users",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_qa_cannot_create_department(
        self,
        client: AsyncClient,
        qa_cookies: dict,
    ):
        response = await client.post(
            "/departments/create",
            data={"name": "QA Dept", "code": "QAD"},
            cookies=qa_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_edit_user(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        qa_user: User,
    ):
        response = await client.get(
            f"/users/{qa_user.id}/edit",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_project_manager_cannot_toggle_user_active(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        developer_user: User,
    ):
        response = await client.post(
            f"/users/{developer_user.id}/toggle-active",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_project_manager_cannot_delete_department(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        test_department: Department,
    ):
        response = await client.post(
            f"/departments/{test_department.id}/delete",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403