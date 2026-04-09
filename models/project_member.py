import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Column, String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class ProjectMember(Base):
    __tablename__ = "project_members"

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member_project_user"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="member")  # owner, manager, member, observer
    joined_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="project_members", lazy="selectin")
    user = relationship("User", back_populates="project_memberships", lazy="selectin")

    def __repr__(self):
        return f"<ProjectMember(id={self.id}, project_id={self.project_id}, user_id={self.user_id}, role={self.role})>"