import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.project import Project, ProjectMember
from models.department import Department
from models.user import User
from tests.conftest import _create_user, _auth_cookies


@pytest.mark.asyncio
class TestProjectList:
    async def test_project_list_requires_login(self, client: AsyncClient):
        response = await client.get("/projects", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_project_list_authenticated(
        self, client: AsyncClient, super_admin_cookies: dict, test_project: Project
    ):
        response = await client.get("/projects", cookies=super_admin_cookies)
        assert response.status_code == 200
        assert "Test Project" in response.text

    async def test_project_list_search(
        self, client: AsyncClient, super_admin_cookies: dict, test_project: Project
    ):
        response = await client.get(
            "/projects?search=Test", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "Test Project" in response.text

    async def test_project_list_search_no_results(
        self, client: AsyncClient, super_admin_cookies: dict, test_project: Project
    ):
        response = await client.get(
            "/projects?search=NonExistentXYZ", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "No projects found" in response.text

    async def test_project_list_filter_by_status(
        self, client: AsyncClient, super_admin_cookies: dict, test_project: Project
    ):
        response = await client.get(
            "/projects?status=Active", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "Test Project" in response.text

    async def test_project_list_filter_by_status_no_match(
        self, client: AsyncClient, super_admin_cookies: dict, test_project: Project
    ):
        response = await client.get(
            "/projects?status=Archived", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "Test Project" not in response.text

    async def test_project_list_filter_by_department(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_department: Department,
    ):
        response = await client.get(
            f"/projects?department={test_department.id}",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert "Test Project" in response.text

    async def test_project_list_sort_by_name(
        self, client: AsyncClient, super_admin_cookies: dict, test_project: Project
    ):
        response = await client.get(
            "/projects?sort=name_asc", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "Test Project" in response.text

    async def test_project_list_sort_by_newest(
        self, client: AsyncClient, super_admin_cookies: dict, test_project: Project
    ):
        response = await client.get(
            "/projects?sort=newest", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "Test Project" in response.text


@pytest.mark.asyncio
class TestProjectCreate:
    async def test_create_project_form_requires_login(self, client: AsyncClient):
        response = await client.get("/projects/create", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_create_project_form_super_admin(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.get(
            "/projects/create", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "Create" in response.text

    async def test_create_project_form_project_manager(
        self, client: AsyncClient, project_manager_cookies: dict
    ):
        response = await client.get(
            "/projects/create", cookies=project_manager_cookies
        )
        assert response.status_code == 200

    async def test_create_project_form_developer_forbidden(
        self, client: AsyncClient, developer_cookies: dict
    ):
        response = await client.get(
            "/projects/create", cookies=developer_cookies, follow_redirects=False
        )
        assert response.status_code == 403

    async def test_create_project_form_viewer_forbidden(
        self, client: AsyncClient, viewer_cookies: dict
    ):
        response = await client.get(
            "/projects/create", cookies=viewer_cookies, follow_redirects=False
        )
        assert response.status_code == 403

    async def test_create_project_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_department: Department,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "New Test Project",
                "description": "A brand new project",
                "status": "Planning",
                "department_id": test_department.id,
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.name == "New Test Project")
        )
        project = result.scalars().first()
        assert project is not None
        assert project.description == "A brand new project"
        assert project.status == "Planning"
        assert project.department_id == test_department.id

    async def test_create_project_key_auto_generation(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "Alpha Beta Gamma",
                "description": "",
                "status": "Planning",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.name == "Alpha Beta Gamma")
        )
        project = result.scalars().first()
        assert project is not None
        assert project.key is not None
        assert len(project.key) > 0
        assert project.key == project.key.upper() or project.key[0].isalpha()

    async def test_create_project_key_single_word(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "Monolith",
                "description": "",
                "status": "Active",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.name == "Monolith")
        )
        project = result.scalars().first()
        assert project is not None
        assert project.key is not None
        assert len(project.key) > 0

    async def test_create_project_empty_name_fails(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "",
                "description": "No name project",
                "status": "Planning",
                "department_id": "",
            },
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert "required" in response.text.lower() or "error" in response.text.lower()

    async def test_create_project_duplicate_name_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "Test Project",
                "description": "Duplicate",
                "status": "Planning",
                "department_id": "",
            },
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert "already exists" in response.text.lower()

    async def test_create_project_invalid_status(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "Invalid Status Project",
                "description": "",
                "status": "InvalidStatus",
                "department_id": "",
            },
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert "invalid" in response.text.lower() or "error" in response.text.lower()

    async def test_create_project_developer_forbidden(
        self, client: AsyncClient, developer_cookies: dict
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "Dev Project",
                "description": "",
                "status": "Planning",
                "department_id": "",
            },
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_create_project_creates_owner_membership(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "Membership Test Project",
                "description": "",
                "status": "Planning",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.name == "Membership Test Project")
        )
        project = result.scalars().first()
        assert project is not None

        member_result = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == super_admin_user.id,
            )
        )
        membership = member_result.scalars().first()
        assert membership is not None
        assert membership.role == "owner"


@pytest.mark.asyncio
class TestProjectDetail:
    async def test_project_detail_requires_login(
        self, client: AsyncClient, test_project: Project
    ):
        response = await client.get(
            f"/projects/{test_project.id}", follow_redirects=False
        )
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_project_detail_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "Test Project" in response.text
        assert test_project.key in response.text

    async def test_project_detail_not_found(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.get(
            "/projects/nonexistent-id-12345",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 404

    async def test_project_detail_shows_description(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "A test project for unit tests" in response.text


@pytest.mark.asyncio
class TestProjectEdit:
    async def test_edit_project_form_requires_login(
        self, client: AsyncClient, test_project: Project
    ):
        response = await client.get(
            f"/projects/{test_project.id}/edit", follow_redirects=False
        )
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_edit_project_form_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/edit", cookies=super_admin_cookies
        )
        assert response.status_code == 200
        assert "Test Project" in response.text

    async def test_edit_project_form_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/edit",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_edit_project_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/edit",
            data={
                "name": "Updated Project Name",
                "description": "Updated description",
                "status": "On Hold",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        await db_session.refresh(test_project)
        assert test_project.name == "Updated Project Name"
        assert test_project.description == "Updated description"
        assert test_project.status == "On Hold"

    async def test_edit_project_empty_name_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/edit",
            data={
                "name": "",
                "description": "No name",
                "status": "Active",
                "department_id": "",
            },
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert "required" in response.text.lower() or "error" in response.text.lower()

    async def test_edit_project_not_found(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.post(
            "/projects/nonexistent-id-12345/edit",
            data={
                "name": "Ghost",
                "description": "",
                "status": "Active",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 404

    async def test_edit_project_project_manager_allowed(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/edit",
            cookies=project_manager_cookies,
        )
        assert response.status_code == 200

    async def test_edit_project_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/edit",
            data={
                "name": "Viewer Edit",
                "description": "",
                "status": "Active",
                "department_id": "",
            },
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestProjectDelete:
    async def test_delete_project_requires_login(
        self, client: AsyncClient, test_project: Project
    ):
        response = await client.post(
            f"/projects/{test_project.id}/delete", follow_redirects=False
        )
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_delete_project_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        db_session: AsyncSession,
    ):
        project_id = test_project.id
        response = await client.post(
            f"/projects/{project_id}/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.id == project_id)
        )
        deleted_project = result.scalars().first()
        assert deleted_project is None

    async def test_delete_project_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/delete",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_delete_project_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/delete",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_delete_project_not_found(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.post(
            "/projects/nonexistent-id-12345/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestProjectMembers:
    async def test_members_page_requires_login(
        self, client: AsyncClient, test_project: Project
    ):
        response = await client.get(
            f"/projects/{test_project.id}/members", follow_redirects=False
        )
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_members_page_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/members",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert "Members" in response.text or "members" in response.text.lower()

    async def test_members_page_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/members",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_add_member_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        developer_user: User,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/members/add",
            data={"user_id": developer_user.id},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == test_project.id,
                ProjectMember.user_id == developer_user.id,
            )
        )
        membership = result.scalars().first()
        assert membership is not None

    async def test_add_member_empty_user_id(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/members/add",
            data={"user_id": ""},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_add_member_duplicate(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        super_admin_user: User,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/members/add",
            data={"user_id": super_admin_user.id},
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_add_member_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_project: Project,
        qa_user: User,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/members/add",
            data={"user_id": qa_user.id},
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_remove_member_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        developer_user: User,
        db_session: AsyncSession,
    ):
        member = ProjectMember(
            project_id=test_project.id,
            user_id=developer_user.id,
            role="member",
        )
        db_session.add(member)
        await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/members/{developer_user.id}/remove",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == test_project.id,
                ProjectMember.user_id == developer_user.id,
            )
        )
        membership = result.scalars().first()
        assert membership is None

    async def test_remove_member_not_found(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/members/nonexistent-user-id/remove",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_remove_member_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_project: Project,
        super_admin_user: User,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/members/{super_admin_user.id}/remove",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestProjectKeyGeneration:
    async def test_key_multi_word_name(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "Customer Relationship Manager",
                "description": "",
                "status": "Planning",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.name == "Customer Relationship Manager")
        )
        project = result.scalars().first()
        assert project is not None
        assert project.key == "CRM"

    async def test_key_two_word_name(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "Data Pipeline",
                "description": "",
                "status": "Planning",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.name == "Data Pipeline")
        )
        project = result.scalars().first()
        assert project is not None
        assert project.key == "DP"

    async def test_key_uniqueness_with_suffix(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        db_session: AsyncSession,
    ):
        await client.post(
            "/projects/create",
            data={
                "name": "Quick App",
                "description": "",
                "status": "Planning",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )

        response = await client.post(
            "/projects/create",
            data={
                "name": "Quality Assurance",
                "description": "",
                "status": "Planning",
                "department_id": "",
            },
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.name == "Quick App")
        )
        project1 = result.scalars().first()

        result = await db_session.execute(
            select(Project).where(Project.name == "Quality Assurance")
        )
        project2 = result.scalars().first()

        assert project1 is not None
        assert project2 is not None
        assert project1.key != project2.key


@pytest.mark.asyncio
class TestProjectAnalytics:
    async def test_analytics_requires_login(
        self, client: AsyncClient, test_project: Project
    ):
        response = await client.get(
            f"/projects/{test_project.id}/analytics", follow_redirects=False
        )
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_analytics_page_loads(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/analytics",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200

    async def test_analytics_not_found(
        self, client: AsyncClient, super_admin_cookies: dict
    ):
        response = await client.get(
            "/projects/nonexistent-id-12345/analytics",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestProjectBoard:
    async def test_board_requires_login(
        self, client: AsyncClient, test_project: Project
    ):
        response = await client.get(
            f"/projects/{test_project.id}/board", follow_redirects=False
        )
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_board_page_loads(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/board",
            cookies=super_admin_cookies,
        )
        assert response.status_code == 200
        assert "Board" in response.text or "board" in response.text.lower()


@pytest.mark.asyncio
class TestProjectRoleAccess:
    async def test_qa_cannot_create_project(
        self, client: AsyncClient, qa_cookies: dict
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "QA Project",
                "description": "",
                "status": "Planning",
                "department_id": "",
            },
            cookies=qa_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_qa_cannot_edit_project(
        self,
        client: AsyncClient,
        qa_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/edit",
            data={
                "name": "QA Edit",
                "description": "",
                "status": "Active",
                "department_id": "",
            },
            cookies=qa_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_qa_cannot_delete_project(
        self,
        client: AsyncClient,
        qa_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/delete",
            cookies=qa_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_viewer_can_view_project_list(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
    ):
        response = await client.get("/projects", cookies=viewer_cookies)
        assert response.status_code == 200

    async def test_viewer_can_view_project_detail(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}", cookies=viewer_cookies
        )
        assert response.status_code == 200

    async def test_project_manager_can_create(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/projects/create",
            data={
                "name": "PM Created Project",
                "description": "Created by PM",
                "status": "Planning",
                "department_id": "",
            },
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.name == "PM Created Project")
        )
        project = result.scalars().first()
        assert project is not None

    async def test_project_manager_can_delete(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        project_manager_user: User,
        test_department: Department,
        db_session: AsyncSession,
    ):
        project = Project(
            name="PM Delete Target",
            key="PDT",
            description="To be deleted by PM",
            status="Planning",
            department_id=test_department.id,
            created_by=project_manager_user.id,
        )
        db_session.add(project)
        await db_session.flush()

        response = await client.post(
            f"/projects/{project.id}/delete",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Project).where(Project.id == project.id)
        )
        deleted = result.scalars().first()
        assert deleted is None