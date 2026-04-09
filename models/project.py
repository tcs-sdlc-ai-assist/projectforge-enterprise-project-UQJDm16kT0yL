import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from database import Base


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    role = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    project = relationship("Project", back_populates="project_members", lazy="selectin")
    user = relationship("User", back_populates="project_memberships", lazy="selectin")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    key = Column(String(20), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="Planning")
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    department = relationship("Department", back_populates="projects", lazy="selectin")
    creator = relationship("User", back_populates="created_projects", foreign_keys=[created_by], lazy="selectin")
    project_members = relationship("ProjectMember", back_populates="project", lazy="selectin", cascade="all, delete-orphan")
    sprints = relationship("Sprint", back_populates="project", lazy="selectin", cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="project", lazy="selectin", cascade="all, delete-orphan")
    labels = relationship("Label", back_populates="project", lazy="selectin", cascade="all, delete-orphan")

    @property
    def members(self):
        return [pm.user for pm in self.project_members if pm.user is not None]

    @property
    def member_count(self):
        return len(self.project_members)

    @staticmethod
    def generate_key(name: str) -> str:
        words = name.strip().upper().split()
        if len(words) >= 2:
            key = "".join(w[0] for w in words[:4])
        else:
            key = name.strip().upper()[:4]
        return key.replace(" ", "")

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}', key='{self.key}', status='{self.status}')>"