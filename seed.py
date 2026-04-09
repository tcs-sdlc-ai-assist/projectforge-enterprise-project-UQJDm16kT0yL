import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging
from sqlalchemy import select

from database import async_session
from models.user import User
from models.department import Department
from config import settings
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SUGGESTED_LABELS = [
    {"name": "bug", "color": "#dc2626"},
    {"name": "feature", "color": "#2563eb"},
    {"name": "enhancement", "color": "#7c3aed"},
    {"name": "documentation", "color": "#0891b2"},
    {"name": "design", "color": "#db2777"},
    {"name": "testing", "color": "#ea580c"},
    {"name": "refactor", "color": "#65a30d"},
    {"name": "performance", "color": "#ca8a04"},
    {"name": "security", "color": "#dc2626"},
    {"name": "infrastructure", "color": "#475569"},
    {"name": "accessibility", "color": "#0d9488"},
    {"name": "urgent", "color": "#b91c1c"},
    {"name": "good first issue", "color": "#16a34a"},
    {"name": "help wanted", "color": "#9333ea"},
    {"name": "wontfix", "color": "#6b7280"},
    {"name": "duplicate", "color": "#9ca3af"},
    {"name": "blocked", "color": "#ef4444"},
    {"name": "tech debt", "color": "#f59e0b"},
]


async def seed_database() -> None:
    """Seed the database with default department and admin user if not present."""
    async with async_session() as session:
        try:
            # Check for existing Engineering department
            result = await session.execute(
                select(Department).where(Department.code == "ENG")
            )
            department = result.scalars().first()

            if department is None:
                department = Department(
                    name="Engineering",
                    code="ENG",
                )
                session.add(department)
                await session.flush()
                logger.info("Created default Engineering department")

            # Check for existing admin user
            admin_username = settings.DEFAULT_ADMIN_USERNAME
            admin_password = settings.DEFAULT_ADMIN_PASSWORD

            result = await session.execute(
                select(User).where(User.username == admin_username)
            )
            admin_user = result.scalars().first()

            if admin_user is None:
                password_hash = pwd_context.hash(admin_password)
                admin_user = User(
                    username=admin_username,
                    email="admin@projectforge.com",
                    password_hash=password_hash,
                    display_name="Admin",
                    role="Super Admin",
                    department_id=department.id,
                    is_active=True,
                )
                session.add(admin_user)
                await session.flush()

                # Set department head to admin user
                department.head_id = admin_user.id
                await session.flush()

                logger.info(
                    "Created default admin user: %s with role Super Admin",
                    admin_username,
                )
            else:
                logger.info(
                    "Admin user '%s' already exists, skipping seed",
                    admin_username,
                )

            await session.commit()
            logger.info("Database seeding completed successfully")

        except Exception:
            await session.rollback()
            logger.exception("Error during database seeding")
            raise