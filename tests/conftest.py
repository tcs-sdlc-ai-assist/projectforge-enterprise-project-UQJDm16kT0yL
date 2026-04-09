import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base, get_db
from models.user import User
from models.department import Department
from models.project import Project, ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket
from models.label import Label
from models.comment import Comment
from models.time_entry import TimeEntry
from models.audit_log import AuditLog
from dependencies import create_session_cookie, COOKIE_NAME
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

test_async_session = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()


async def _create_user(
    db_session: AsyncSession,
    username: str,
    password: str,
    role: str,
    email: str = None,
    department_id: str = None,
) -> User:
    password_hash = pwd_context.hash(password)
    user = User(
        username=username,
        email=email or f"{username}@test.com",
        password_hash=password_hash,
        display_name=username.replace("_", " ").title(),
        role=role,
        department_id=department_id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _auth_cookies(user: User) -> dict:
    cookie_value = create_session_cookie(user.id)
    return {COOKIE_NAME: cookie_value}


@pytest_asyncio.fixture
async def test_department(db_session: AsyncSession) -> Department:
    department = Department(
        name="Test Engineering",
        code="TENG",
    )
    db_session.add(department)
    await db_session.flush()
    return department


@pytest_asyncio.fixture
async def super_admin_user(db_session: AsyncSession, test_department: Department) -> User:
    user = await _create_user(
        db_session,
        username="test_super_admin",
        password="testpass123",
        role="Super Admin",
        department_id=test_department.id,
    )
    return user


@pytest_asyncio.fixture
async def project_manager_user(db_session: AsyncSession, test_department: Department) -> User:
    user = await _create_user(
        db_session,
        username="test_pm",
        password="testpass123",
        role="Project Manager",
        department_id=test_department.id,
    )
    return user


@pytest_asyncio.fixture
async def developer_user(db_session: AsyncSession, test_department: Department) -> User:
    user = await _create_user(
        db_session,
        username="test_developer",
        password="testpass123",
        role="Developer",
        department_id=test_department.id,
    )
    return user


@pytest_asyncio.fixture
async def qa_user(db_session: AsyncSession, test_department: Department) -> User:
    user = await _create_user(
        db_session,
        username="test_qa",
        password="testpass123",
        role="QA",
        department_id=test_department.id,
    )
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession, test_department: Department) -> User:
    user = await _create_user(
        db_session,
        username="test_viewer",
        password="testpass123",
        role="Viewer",
        department_id=test_department.id,
    )
    return user


@pytest_asyncio.fixture
async def super_admin_cookies(super_admin_user: User) -> dict:
    return _auth_cookies(super_admin_user)


@pytest_asyncio.fixture
async def project_manager_cookies(project_manager_user: User) -> dict:
    return _auth_cookies(project_manager_user)


@pytest_asyncio.fixture
async def developer_cookies(developer_user: User) -> dict:
    return _auth_cookies(developer_user)


@pytest_asyncio.fixture
async def qa_cookies(qa_user: User) -> dict:
    return _auth_cookies(qa_user)


@pytest_asyncio.fixture
async def viewer_cookies(viewer_user: User) -> dict:
    return _auth_cookies(viewer_user)


@pytest_asyncio.fixture
async def authenticated_client(
    client: AsyncClient,
    super_admin_cookies: dict,
) -> AsyncClient:
    client.cookies.update(super_admin_cookies)
    return client


@pytest_asyncio.fixture
async def test_project(
    db_session: AsyncSession,
    super_admin_user: User,
    test_department: Department,
) -> Project:
    project = Project(
        name="Test Project",
        key="TP",
        description="A test project for unit tests",
        status="Active",
        department_id=test_department.id,
        created_by=super_admin_user.id,
    )
    db_session.add(project)
    await db_session.flush()

    member = ProjectMember(
        project_id=project.id,
        user_id=super_admin_user.id,
        role="owner",
    )
    db_session.add(member)
    await db_session.flush()

    return project


@pytest_asyncio.fixture
async def test_sprint(
    db_session: AsyncSession,
    test_project: Project,
) -> Sprint:
    from datetime import date, timedelta

    sprint = Sprint(
        name="Test Sprint 1",
        project_id=test_project.id,
        status="Planning",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=14),
    )
    db_session.add(sprint)
    await db_session.flush()
    return sprint


@pytest_asyncio.fixture
async def test_label(
    db_session: AsyncSession,
    test_project: Project,
) -> Label:
    label = Label(
        name="test-bug",
        color="#dc2626",
        project_id=test_project.id,
    )
    db_session.add(label)
    await db_session.flush()
    return label


@pytest_asyncio.fixture
async def test_ticket(
    db_session: AsyncSession,
    test_project: Project,
    test_sprint: Sprint,
    super_admin_user: User,
) -> Ticket:
    from datetime import date, timedelta

    ticket = Ticket(
        title="Test Ticket",
        description="A test ticket for unit tests",
        project_id=test_project.id,
        sprint_id=test_sprint.id,
        ticket_key=f"{test_project.key}-1",
        type="Bug",
        ticket_type="Bug",
        priority="High",
        status="Open",
        assignee_id=super_admin_user.id,
        reporter_id=super_admin_user.id,
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(ticket)
    await db_session.flush()
    return ticket


@pytest_asyncio.fixture
async def test_comment(
    db_session: AsyncSession,
    test_ticket: Ticket,
    super_admin_user: User,
) -> Comment:
    comment = Comment(
        content="This is a test comment",
        ticket_id=test_ticket.id,
        user_id=super_admin_user.id,
        is_internal=False,
    )
    db_session.add(comment)
    await db_session.flush()
    return comment


@pytest_asyncio.fixture
async def test_time_entry(
    db_session: AsyncSession,
    test_ticket: Ticket,
    super_admin_user: User,
) -> TimeEntry:
    from datetime import date

    time_entry = TimeEntry(
        ticket_id=test_ticket.id,
        user_id=super_admin_user.id,
        hours=2.5,
        description="Test time entry",
        logged_date=date.today(),
    )
    db_session.add(time_entry)
    await db_session.flush()
    return time_entry