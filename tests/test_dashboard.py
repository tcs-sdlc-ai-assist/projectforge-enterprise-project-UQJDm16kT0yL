import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta

from models.user import User
from models.project import Project, ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket
from models.time_entry import TimeEntry
from models.audit_log import AuditLog
from models.department import Department
from tests.conftest import _create_user, _auth_cookies


@pytest.mark.asyncio
class TestDashboard:

    async def test_dashboard_redirects_unauthenticated(self, client: AsyncClient):
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_dashboard_loads_for_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_sprint: Sprint,
        test_ticket: Ticket,
    ):
        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Dashboard" in content
        assert "Total Projects" in content
        assert "Active Sprints" in content
        assert "Open Tickets" in content
        assert "Overdue Tickets" in content
        assert "Hours Logged" in content

    async def test_dashboard_loads_for_project_manager(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            "/dashboard",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Dashboard" in content
        assert "Recent Activity" in content

    async def test_dashboard_loads_for_developer(
        self,
        client: AsyncClient,
        developer_cookies: dict,
    ):
        response = await client.get(
            "/dashboard",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Dashboard" in content

    async def test_dashboard_loads_for_qa(
        self,
        client: AsyncClient,
        qa_cookies: dict,
    ):
        response = await client.get(
            "/dashboard",
            cookies=qa_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Dashboard" in content

    async def test_dashboard_loads_for_viewer(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
    ):
        response = await client.get(
            "/dashboard",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Dashboard" in content

    async def test_dashboard_shows_correct_project_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
        test_department: Department,
    ):
        for i in range(3):
            project = Project(
                name=f"Dashboard Test Project {i}",
                key=f"DTP{i}",
                description=f"Test project {i}",
                status="Active",
                department_id=test_department.id,
                created_by=super_admin_user.id,
            )
            db_session.add(project)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Total Projects" in content

    async def test_dashboard_shows_active_sprints_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        active_sprint = Sprint(
            name="Active Sprint Dashboard",
            project_id=test_project.id,
            status="Active",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=14),
        )
        db_session.add(active_sprint)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Active Sprints" in content

    async def test_dashboard_shows_open_tickets_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_cookies: dict,
        test_project: Project,
        super_admin_user: User,
    ):
        for i in range(5):
            ticket = Ticket(
                title=f"Open Ticket {i}",
                project_id=test_project.id,
                ticket_key=f"{test_project.key}-{100 + i}",
                type="Task",
                priority="Medium",
                status="Open",
                reporter_id=super_admin_user.id,
            )
            db_session.add(ticket)

        closed_ticket = Ticket(
            title="Closed Ticket",
            project_id=test_project.id,
            ticket_key=f"{test_project.key}-200",
            type="Task",
            priority="Low",
            status="Closed",
            reporter_id=super_admin_user.id,
        )
        db_session.add(closed_ticket)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Open Tickets" in content

    async def test_dashboard_shows_overdue_tickets(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_cookies: dict,
        test_project: Project,
        super_admin_user: User,
    ):
        overdue_ticket = Ticket(
            title="Overdue Ticket",
            project_id=test_project.id,
            ticket_key=f"{test_project.key}-300",
            type="Bug",
            priority="High",
            status="Open",
            reporter_id=super_admin_user.id,
            due_date=date.today() - timedelta(days=5),
        )
        db_session.add(overdue_ticket)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Overdue Tickets" in content

    async def test_dashboard_shows_tickets_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_cookies: dict,
        test_project: Project,
        super_admin_user: User,
    ):
        statuses = ["Open", "In Progress", "In Review", "Closed"]
        for i, status_val in enumerate(statuses):
            ticket = Ticket(
                title=f"Status Ticket {status_val}",
                project_id=test_project.id,
                ticket_key=f"{test_project.key}-{400 + i}",
                type="Task",
                priority="Medium",
                status=status_val,
                reporter_id=super_admin_user.id,
            )
            db_session.add(ticket)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Tickets by Status" in content

    async def test_dashboard_shows_top_contributors(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_cookies: dict,
        test_ticket: Ticket,
        super_admin_user: User,
    ):
        for i in range(3):
            time_entry = TimeEntry(
                ticket_id=test_ticket.id,
                user_id=super_admin_user.id,
                hours=float(i + 1),
                description=f"Work entry {i}",
                logged_date=date.today() - timedelta(days=i),
            )
            db_session.add(time_entry)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Top Contributors" in content
        assert super_admin_user.username in content

    async def test_dashboard_shows_total_hours_logged(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_cookies: dict,
        test_ticket: Ticket,
        super_admin_user: User,
    ):
        time_entry = TimeEntry(
            ticket_id=test_ticket.id,
            user_id=super_admin_user.id,
            hours=4.5,
            description="Hours test",
            logged_date=date.today(),
        )
        db_session.add(time_entry)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Hours Logged" in content

    async def test_dashboard_recent_activity_visible_for_super_admin(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_cookies: dict,
        super_admin_user: User,
    ):
        audit_log = AuditLog(
            entity_type="Project",
            entity_id="test-entity-id",
            action="CREATE",
            user_id=super_admin_user.id,
            details='{"name": "Test"}',
        )
        db_session.add(audit_log)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Recent Activity" in content

    async def test_dashboard_recent_activity_visible_for_pm(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        project_manager_cookies: dict,
        project_manager_user: User,
    ):
        audit_log = AuditLog(
            entity_type="Ticket",
            entity_id="test-entity-id-2",
            action="UPDATE",
            user_id=project_manager_user.id,
            details='{"status": "Active"}',
        )
        db_session.add(audit_log)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Recent Activity" in content

    async def test_dashboard_recent_activity_hidden_for_developer(
        self,
        client: AsyncClient,
        developer_cookies: dict,
    ):
        response = await client.get(
            "/dashboard",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Recent Activity" not in content

    async def test_dashboard_recent_activity_hidden_for_viewer(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
    ):
        response = await client.get(
            "/dashboard",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Recent Activity" not in content

    async def test_dashboard_top_contributors_ranking_order(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_cookies: dict,
        test_project: Project,
        test_department: Department,
        super_admin_user: User,
    ):
        user_a = await _create_user(
            db_session,
            username="contributor_a",
            password="testpass123",
            role="Developer",
            department_id=test_department.id,
        )
        user_b = await _create_user(
            db_session,
            username="contributor_b",
            password="testpass123",
            role="Developer",
            department_id=test_department.id,
        )

        ticket = Ticket(
            title="Ranking Ticket",
            project_id=test_project.id,
            ticket_key=f"{test_project.key}-500",
            type="Task",
            priority="Medium",
            status="Open",
            reporter_id=super_admin_user.id,
        )
        db_session.add(ticket)
        await db_session.flush()

        time_entry_a = TimeEntry(
            ticket_id=ticket.id,
            user_id=user_a.id,
            hours=10.0,
            description="Lots of work",
            logged_date=date.today(),
        )
        db_session.add(time_entry_a)

        time_entry_b = TimeEntry(
            ticket_id=ticket.id,
            user_id=user_b.id,
            hours=5.0,
            description="Some work",
            logged_date=date.today(),
        )
        db_session.add(time_entry_b)
        await db_session.flush()

        response = await client.get(
            "/dashboard",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "contributor_a" in content
        assert "contributor_b" in content
        pos_a = content.index("contributor_a")
        pos_b = content.index("contributor_b")
        assert pos_a < pos_b


@pytest.mark.asyncio
class TestAuditLog:

    async def test_audit_log_redirects_unauthenticated(self, client: AsyncClient):
        response = await client.get("/audit-log", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    async def test_audit_log_accessible_by_super_admin(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.get(
            "/audit-log",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Audit Log" in content

    async def test_audit_log_forbidden_for_project_manager(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
    ):
        response = await client.get(
            "/audit-log",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_audit_log_forbidden_for_developer(
        self,
        client: AsyncClient,
        developer_cookies: dict,
    ):
        response = await client.get(
            "/audit-log",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_audit_log_forbidden_for_qa(
        self,
        client: AsyncClient,
        qa_cookies: dict,
    ):
        response = await client.get(
            "/audit-log",
            cookies=qa_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_audit_log_forbidden_for_viewer(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
    ):
        response = await client.get(
            "/audit-log",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_audit_log_displays_entries(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        for i in range(3):
            audit_log = AuditLog(
                entity_type="Project",
                entity_id=f"entity-{i}",
                action="CREATE",
                user_id=super_admin_user.id,
                details=f'{{"name": "Project {i}"}}',
            )
            db_session.add(audit_log)
        await db_session.flush()

        response = await client.get(
            "/audit-log",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Project" in content
        assert "CREATE" in content

    async def test_audit_log_filter_by_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        audit_project = AuditLog(
            entity_type="Project",
            entity_id="proj-1",
            action="CREATE",
            user_id=super_admin_user.id,
            details='{"name": "Filter Test Project"}',
        )
        db_session.add(audit_project)

        audit_ticket = AuditLog(
            entity_type="Ticket",
            entity_id="ticket-1",
            action="UPDATE",
            user_id=super_admin_user.id,
            details='{"title": "Filter Test Ticket"}',
        )
        db_session.add(audit_ticket)
        await db_session.flush()

        response = await client.get(
            "/audit-log?entity_type=Project",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Project" in content

    async def test_audit_log_filter_by_action_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        audit_create = AuditLog(
            entity_type="Sprint",
            entity_id="sprint-1",
            action="CREATE",
            user_id=super_admin_user.id,
            details='{"name": "Sprint 1"}',
        )
        db_session.add(audit_create)

        audit_delete = AuditLog(
            entity_type="Sprint",
            entity_id="sprint-2",
            action="DELETE",
            user_id=super_admin_user.id,
            details='{"name": "Sprint 2"}',
        )
        db_session.add(audit_delete)
        await db_session.flush()

        response = await client.get(
            "/audit-log?action_type=DELETE",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "DELETE" in content

    async def test_audit_log_filter_by_user_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
        test_department: Department,
    ):
        other_user = await _create_user(
            db_session,
            username="audit_other_user",
            password="testpass123",
            role="Developer",
            department_id=test_department.id,
        )

        audit_admin = AuditLog(
            entity_type="Label",
            entity_id="label-1",
            action="CREATE",
            user_id=super_admin_user.id,
            details='{"name": "bug"}',
        )
        db_session.add(audit_admin)

        audit_other = AuditLog(
            entity_type="Label",
            entity_id="label-2",
            action="CREATE",
            user_id=other_user.id,
            details='{"name": "feature"}',
        )
        db_session.add(audit_other)
        await db_session.flush()

        response = await client.get(
            f"/audit-log?user_id={super_admin_user.id}",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert super_admin_user.username in content

    async def test_audit_log_combined_filters(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        audit_log = AuditLog(
            entity_type="Department",
            entity_id="dept-1",
            action="UPDATE",
            user_id=super_admin_user.id,
            details='{"name": "Engineering"}',
        )
        db_session.add(audit_log)
        await db_session.flush()

        response = await client.get(
            f"/audit-log?entity_type=Department&action_type=UPDATE&user_id={super_admin_user.id}",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Department" in content
        assert "UPDATE" in content

    async def test_audit_log_empty_state(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.get(
            "/audit-log?entity_type=NonExistentType",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "No audit log entries" in content or "No entries match" in content

    async def test_audit_log_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        for i in range(55):
            audit_log = AuditLog(
                entity_type="Ticket",
                entity_id=f"paginated-ticket-{i}",
                action="CREATE",
                user_id=super_admin_user.id,
                details=f'{{"title": "Ticket {i}"}}',
            )
            db_session.add(audit_log)
        await db_session.flush()

        response_page1 = await client.get(
            "/audit-log?page=1",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response_page1.status_code == 200
        content_page1 = response_page1.text
        assert "Audit Log" in content_page1

        response_page2 = await client.get(
            "/audit-log?page=2",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response_page2.status_code == 200
        content_page2 = response_page2.text
        assert "Audit Log" in content_page2

    async def test_audit_log_page_1_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        for i in range(5):
            audit_log = AuditLog(
                entity_type="Comment",
                entity_id=f"comment-{i}",
                action="CREATE",
                user_id=super_admin_user.id,
                details=f'{{"content": "Comment {i}"}}',
            )
            db_session.add(audit_log)
        await db_session.flush()

        response = await client.get(
            "/audit-log",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "Comment" in content

    async def test_audit_log_shows_actor_username(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        audit_log = AuditLog(
            entity_type="User",
            entity_id="user-1",
            action="CREATE",
            user_id=super_admin_user.id,
            details='{"username": "newuser"}',
        )
        db_session.add(audit_log)
        await db_session.flush()

        response = await client.get(
            "/audit-log",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert super_admin_user.username in content

    async def test_audit_log_shows_entity_types_in_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        for entity_type in ["Project", "Ticket", "Sprint"]:
            audit_log = AuditLog(
                entity_type=entity_type,
                entity_id=f"{entity_type.lower()}-filter-1",
                action="CREATE",
                user_id=super_admin_user.id,
                details=f'{{"type": "{entity_type}"}}',
            )
            db_session.add(audit_log)
        await db_session.flush()

        response = await client.get(
            "/audit-log",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "All Entity Types" in content

    async def test_audit_log_shows_action_types_in_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        super_admin_user: User,
        super_admin_cookies: dict,
    ):
        for action in ["CREATE", "UPDATE", "DELETE"]:
            audit_log = AuditLog(
                entity_type="Project",
                entity_id=f"action-filter-{action}",
                action=action,
                user_id=super_admin_user.id,
                details=f'{{"action": "{action}"}}',
            )
            db_session.add(audit_log)
        await db_session.flush()

        response = await client.get(
            "/audit-log",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert "All Actions" in content

    async def test_audit_log_clear_filters_link(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.get(
            "/audit-log?entity_type=NonExistent",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        content = response.text
        assert 'href="/audit-log"' in content