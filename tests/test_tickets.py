import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from models.project import Project, ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket, ticket_labels
from models.label import Label
from models.comment import Comment
from models.time_entry import TimeEntry
from tests.conftest import _create_user, _auth_cookies


# ─── Ticket CRUD ───────────────────────────────────────────────────────────────


class TestTicketCreate:
    async def test_create_ticket_form_requires_login(self, client: AsyncClient):
        response = await client.get("/projects/fake-id/tickets/create", follow_redirects=False)
        assert response.status_code == 303

    async def test_create_ticket_form_accessible_by_developer(
        self,
        client: AsyncClient,
        developer_cookies: dict,
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

        response = await client.get(
            f"/projects/{test_project.id}/tickets/create",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200

    async def test_create_ticket_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_sprint: Sprint,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/create",
            cookies=super_admin_cookies,
            data={
                "title": "New Test Ticket",
                "description": "A description for the new ticket",
                "type": "Bug",
                "priority": "High",
                "assignee_id": "",
                "sprint_id": test_sprint.id,
                "parent_id": "",
                "due_date": "2025-12-31",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/tickets/" in response.headers.get("location", "")

    async def test_create_ticket_missing_title(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/create",
            cookies=super_admin_cookies,
            data={
                "title": "",
                "description": "No title",
                "type": "Task",
                "priority": "Medium",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Title is required" in response.content

    async def test_create_ticket_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/tickets/create",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_create_ticket_generates_key(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/create",
            cookies=super_admin_cookies,
            data={
                "title": "Ticket With Key",
                "description": "",
                "type": "Task",
                "priority": "Low",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Ticket).where(Ticket.title == "Ticket With Key")
        )
        ticket = result.scalars().first()
        assert ticket is not None
        assert ticket.ticket_key is not None
        assert test_project.key in ticket.ticket_key


class TestTicketDetail:
    async def test_ticket_detail_requires_login(
        self,
        client: AsyncClient,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}",
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_ticket_detail_accessible(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert test_ticket.title.encode() in response.content

    async def test_ticket_detail_shortcut(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_ticket: Ticket,
    ):
        response = await client.get(
            f"/tickets/{test_ticket.id}",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert f"/projects/{test_ticket.project_id}/tickets/{test_ticket.id}" in response.headers.get("location", "")

    async def test_ticket_detail_not_found(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/tickets/nonexistent-id",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 404


class TestTicketEdit:
    async def test_edit_ticket_form_accessible(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/edit",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200

    async def test_edit_ticket_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/edit",
            cookies=super_admin_cookies,
            data={
                "title": "Updated Ticket Title",
                "description": "Updated description",
                "type": "Feature",
                "priority": "Critical",
                "status": "In Progress",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_edit_ticket_empty_title_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/edit",
            cookies=super_admin_cookies,
            data={
                "title": "",
                "description": "No title",
                "type": "Task",
                "priority": "Medium",
                "status": "Open",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Title is required" in response.content

    async def test_edit_ticket_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.get(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/edit",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403


class TestTicketDelete:
    async def test_delete_ticket_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        ticket_id = test_ticket.id
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{ticket_id}/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        deleted_ticket = result.scalars().first()
        assert deleted_ticket is None

    async def test_delete_ticket_developer_forbidden(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/delete",
            cookies=developer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_delete_ticket_not_found(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/nonexistent-id/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 404


# ─── Ticket Status Workflow ────────────────────────────────────────────────────


class TestTicketStatusWorkflow:
    async def test_change_status_open_to_in_progress(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=super_admin_cookies,
            data={"status": "In Progress"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)

        await db_session.refresh(test_ticket)
        assert test_ticket.status == "In Progress"

    async def test_change_status_to_in_review(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        test_ticket.status = "In Progress"
        await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=super_admin_cookies,
            data={"status": "In Review"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)

        await db_session.refresh(test_ticket)
        assert test_ticket.status == "In Review"

    async def test_change_status_to_qa_testing(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        test_ticket.status = "In Review"
        await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=super_admin_cookies,
            data={"status": "QA Testing"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)

        await db_session.refresh(test_ticket)
        assert test_ticket.status == "QA Testing"

    async def test_change_status_to_closed(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=super_admin_cookies,
            data={"status": "Closed"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)

        await db_session.refresh(test_ticket)
        assert test_ticket.status == "Closed"
        assert test_ticket.closed_date is not None

    async def test_change_status_to_reopened(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        test_ticket.status = "Closed"
        await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=super_admin_cookies,
            data={"status": "Reopened"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)

        await db_session.refresh(test_ticket)
        assert test_ticket.status == "Reopened"
        assert test_ticket.closed_date is None

    async def test_change_status_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=viewer_cookies,
            data={"status": "In Progress"},
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_change_status_empty_status_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=super_admin_cookies,
            data={"status": ""},
            follow_redirects=False,
        )
        assert response.status_code == 400


# ─── Subtask Creation ──────────────────────────────────────────────────────────


class TestSubtaskCreation:
    async def test_create_subtask_with_parent_id(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/create",
            cookies=super_admin_cookies,
            data={
                "title": "Subtask of Test Ticket",
                "description": "This is a subtask",
                "type": "Task",
                "priority": "Low",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": test_ticket.id,
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Ticket).where(Ticket.title == "Subtask of Test Ticket")
        )
        subtask = result.scalars().first()
        assert subtask is not None
        assert subtask.parent_id == test_ticket.id

    async def test_subtask_appears_on_parent_detail(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        subtask = Ticket(
            title="Child Subtask",
            description="A child ticket",
            project_id=test_project.id,
            ticket_key=f"{test_project.key}-99",
            type="Task",
            ticket_type="Task",
            priority="Low",
            status="Open",
            parent_id=test_ticket.id,
        )
        db_session.add(subtask)
        await db_session.flush()

        response = await client.get(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Child Subtask" in response.content


# ─── Label Assignment ──────────────────────────────────────────────────────────


class TestLabelAssignment:
    async def test_create_ticket_with_labels(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_label: Label,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/create",
            cookies=super_admin_cookies,
            data={
                "title": "Ticket With Label",
                "description": "",
                "type": "Bug",
                "priority": "High",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
                "label_ids": test_label.id,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Ticket).where(Ticket.title == "Ticket With Label")
        )
        ticket = result.scalars().first()
        assert ticket is not None

        label_result = await db_session.execute(
            select(ticket_labels).where(ticket_labels.c.ticket_id == ticket.id)
        )
        labels = label_result.all()
        assert len(labels) == 1
        assert labels[0].label_id == test_label.id

    async def test_edit_ticket_update_labels(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        test_label: Label,
        db_session: AsyncSession,
    ):
        label2 = Label(
            name="test-feature",
            color="#2563eb",
            project_id=test_project.id,
        )
        db_session.add(label2)
        await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/edit",
            cookies=super_admin_cookies,
            data={
                "title": test_ticket.title,
                "description": test_ticket.description or "",
                "type": test_ticket.type,
                "priority": test_ticket.priority,
                "status": test_ticket.status,
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
                "label_ids": [test_label.id, label2.id],
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        label_result = await db_session.execute(
            select(ticket_labels).where(ticket_labels.c.ticket_id == test_ticket.id)
        )
        labels = label_result.all()
        assert len(labels) == 2


# ─── Comments ──────────────────────────────────────────────────────────────────


class TestComments:
    async def test_create_comment_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/comments",
            cookies=super_admin_cookies,
            data={
                "content": "This is a test comment",
                "parent_id": "",
                "is_internal": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Comment).where(Comment.ticket_id == test_ticket.id)
        )
        comments = result.scalars().all()
        assert any(c.content == "This is a test comment" for c in comments)

    async def test_create_internal_comment(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/comments",
            cookies=super_admin_cookies,
            data={
                "content": "Internal note for team",
                "parent_id": "",
                "is_internal": "true",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Comment).where(
                Comment.ticket_id == test_ticket.id,
                Comment.content == "Internal note for team",
            )
        )
        comment = result.scalars().first()
        assert comment is not None
        assert comment.is_internal is True

    async def test_create_public_comment(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/comments",
            cookies=super_admin_cookies,
            data={
                "content": "Public comment visible to all",
                "parent_id": "",
                "is_internal": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Comment).where(
                Comment.ticket_id == test_ticket.id,
                Comment.content == "Public comment visible to all",
            )
        )
        comment = result.scalars().first()
        assert comment is not None
        assert comment.is_internal is False

    async def test_create_reply_comment(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        test_comment: Comment,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/comments",
            cookies=super_admin_cookies,
            data={
                "content": "This is a reply",
                "parent_id": test_comment.id,
                "is_internal": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Comment).where(
                Comment.ticket_id == test_ticket.id,
                Comment.content == "This is a reply",
            )
        )
        reply = result.scalars().first()
        assert reply is not None
        assert reply.parent_id == test_comment.id

    async def test_create_comment_empty_content_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/comments",
            cookies=super_admin_cookies,
            data={
                "content": "",
                "parent_id": "",
                "is_internal": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_create_comment_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/comments",
            cookies=viewer_cookies,
            data={
                "content": "Viewer should not be able to comment",
                "parent_id": "",
                "is_internal": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_delete_comment_by_owner(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        test_comment: Comment,
        db_session: AsyncSession,
    ):
        comment_id = test_comment.id
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/comments/{comment_id}/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        deleted = result.scalars().first()
        assert deleted is None

    async def test_delete_comment_not_found(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/comments/nonexistent-id/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 404


# ─── Time Entries ──────────────────────────────────────────────────────────────


class TestTimeEntries:
    async def test_create_time_entry_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/time-entries",
            cookies=super_admin_cookies,
            data={
                "hours": "3.5",
                "description": "Worked on implementation",
                "entry_date": "2025-01-15",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(TimeEntry).where(TimeEntry.ticket_id == test_ticket.id)
        )
        entries = result.scalars().all()
        assert any(e.hours == 3.5 and e.description == "Worked on implementation" for e in entries)

    async def test_create_time_entry_invalid_hours(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/time-entries",
            cookies=super_admin_cookies,
            data={
                "hours": "0",
                "description": "Zero hours",
                "entry_date": "2025-01-15",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_create_time_entry_negative_hours(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/time-entries",
            cookies=super_admin_cookies,
            data={
                "hours": "-1",
                "description": "Negative hours",
                "entry_date": "2025-01-15",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_create_time_entry_missing_date(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/time-entries",
            cookies=super_admin_cookies,
            data={
                "hours": "2",
                "description": "No date",
                "entry_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_create_time_entry_non_numeric_hours(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/time-entries",
            cookies=super_admin_cookies,
            data={
                "hours": "abc",
                "description": "Invalid hours",
                "entry_date": "2025-01-15",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_create_time_entry_viewer_forbidden(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/time-entries",
            cookies=viewer_cookies,
            data={
                "hours": "1",
                "description": "Viewer time entry",
                "entry_date": "2025-01-15",
            },
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_delete_time_entry_by_owner(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
        test_time_entry: TimeEntry,
        db_session: AsyncSession,
    ):
        entry_id = test_time_entry.id
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/time-entries/{entry_id}/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == entry_id)
        )
        deleted = result.scalars().first()
        assert deleted is None

    async def test_delete_time_entry_not_found(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/time-entries/nonexistent-id/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 404

    async def test_delete_time_entry_shortcut(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_ticket: Ticket,
        test_time_entry: TimeEntry,
        db_session: AsyncSession,
    ):
        entry_id = test_time_entry.id
        response = await client.post(
            f"/tickets/{test_ticket.id}/time-entries/{entry_id}/delete",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == entry_id)
        )
        deleted = result.scalars().first()
        assert deleted is None


# ─── Role-Based Access ─────────────────────────────────────────────────────────


class TestTicketRoleAccess:
    async def test_developer_can_create_ticket(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        developer_user: User,
        test_project: Project,
        db_session: AsyncSession,
    ):
        existing = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == test_project.id,
                ProjectMember.user_id == developer_user.id,
            )
        )
        if not existing.scalars().first():
            member = ProjectMember(
                project_id=test_project.id,
                user_id=developer_user.id,
                role="member",
            )
            db_session.add(member)
            await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/create",
            cookies=developer_cookies,
            data={
                "title": "Developer Created Ticket",
                "description": "",
                "type": "Task",
                "priority": "Medium",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_qa_can_create_ticket(
        self,
        client: AsyncClient,
        qa_cookies: dict,
        qa_user: User,
        test_project: Project,
        db_session: AsyncSession,
    ):
        existing = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == test_project.id,
                ProjectMember.user_id == qa_user.id,
            )
        )
        if not existing.scalars().first():
            member = ProjectMember(
                project_id=test_project.id,
                user_id=qa_user.id,
                role="member",
            )
            db_session.add(member)
            await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/create",
            cookies=qa_cookies,
            data={
                "title": "QA Created Bug Report",
                "description": "Found a bug",
                "type": "Bug",
                "priority": "High",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_viewer_cannot_create_ticket(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/create",
            cookies=viewer_cookies,
            data={
                "title": "Viewer Ticket",
                "description": "",
                "type": "Task",
                "priority": "Low",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_viewer_cannot_edit_ticket(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/edit",
            cookies=viewer_cookies,
            data={
                "title": "Viewer Edit Attempt",
                "description": "",
                "type": "Task",
                "priority": "Low",
                "status": "Open",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_viewer_cannot_delete_ticket(
        self,
        client: AsyncClient,
        viewer_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/delete",
            cookies=viewer_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_project_manager_can_delete_ticket(
        self,
        client: AsyncClient,
        project_manager_cookies: dict,
        project_manager_user: User,
        test_project: Project,
        db_session: AsyncSession,
    ):
        existing = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == test_project.id,
                ProjectMember.user_id == project_manager_user.id,
            )
        )
        if not existing.scalars().first():
            member = ProjectMember(
                project_id=test_project.id,
                user_id=project_manager_user.id,
                role="manager",
            )
            db_session.add(member)
            await db_session.flush()

        ticket = Ticket(
            title="PM Delete Target",
            project_id=test_project.id,
            ticket_key=f"{test_project.key}-PM1",
            type="Task",
            ticket_type="Task",
            priority="Low",
            status="Open",
        )
        db_session.add(ticket)
        await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/{ticket.id}/delete",
            cookies=project_manager_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_developer_can_change_status(
        self,
        client: AsyncClient,
        developer_cookies: dict,
        developer_user: User,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        existing = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == test_project.id,
                ProjectMember.user_id == developer_user.id,
            )
        )
        if not existing.scalars().first():
            member = ProjectMember(
                project_id=test_project.id,
                user_id=developer_user.id,
                role="member",
            )
            db_session.add(member)
            await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=developer_cookies,
            data={"status": "In Progress"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)

    async def test_qa_can_change_status(
        self,
        client: AsyncClient,
        qa_cookies: dict,
        qa_user: User,
        test_project: Project,
        test_ticket: Ticket,
        db_session: AsyncSession,
    ):
        existing = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == test_project.id,
                ProjectMember.user_id == qa_user.id,
            )
        )
        if not existing.scalars().first():
            member = ProjectMember(
                project_id=test_project.id,
                user_id=qa_user.id,
                role="member",
            )
            db_session.add(member)
            await db_session.flush()

        response = await client.post(
            f"/projects/{test_project.id}/tickets/{test_ticket.id}/status",
            cookies=qa_cookies,
            data={"status": "QA Testing"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)


# ─── Global Ticket List ───────────────────────────────────────────────────────


class TestGlobalTicketList:
    async def test_global_ticket_list_requires_login(self, client: AsyncClient):
        response = await client.get("/tickets", follow_redirects=False)
        assert response.status_code == 303

    async def test_global_ticket_list_accessible(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_ticket: Ticket,
    ):
        response = await client.get(
            "/tickets",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200

    async def test_global_ticket_list_with_project_filter(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        test_ticket: Ticket,
    ):
        response = await client.get(
            f"/tickets?project_id={test_project.id}",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert test_ticket.title.encode() in response.content

    async def test_global_ticket_list_with_status_filter(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_ticket: Ticket,
    ):
        response = await client.get(
            "/tickets?status=Open",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200

    async def test_global_ticket_list_with_search(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_ticket: Ticket,
    ):
        response = await client.get(
            f"/tickets?search={test_ticket.title[:5]}",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200


# ─── Global Ticket Create ─────────────────────────────────────────────────────


class TestGlobalTicketCreate:
    async def test_global_create_ticket_form(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.get(
            "/tickets/create",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 200

    async def test_global_create_ticket_redirects_with_project_id(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
    ):
        response = await client.get(
            f"/tickets/create?project_id={test_project.id}",
            cookies=super_admin_cookies,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert f"/projects/{test_project.id}/tickets/create" in response.headers.get("location", "")

    async def test_global_create_ticket_post_success(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
        test_project: Project,
        db_session: AsyncSession,
    ):
        response = await client.post(
            "/tickets/create",
            cookies=super_admin_cookies,
            data={
                "title": "Global Created Ticket",
                "description": "Created from global form",
                "type": "Feature",
                "priority": "Medium",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
                "project_id": test_project.id,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(Ticket).where(Ticket.title == "Global Created Ticket")
        )
        ticket = result.scalars().first()
        assert ticket is not None
        assert ticket.project_id == test_project.id

    async def test_global_create_ticket_missing_project_fails(
        self,
        client: AsyncClient,
        super_admin_cookies: dict,
    ):
        response = await client.post(
            "/tickets/create",
            cookies=super_admin_cookies,
            data={
                "title": "No Project Ticket",
                "description": "",
                "type": "Task",
                "priority": "Low",
                "assignee_id": "",
                "sprint_id": "",
                "parent_id": "",
                "due_date": "",
                "project_id": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Project is required" in response.content