import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(150), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(Text, nullable=False)
    display_name = Column(String(200), nullable=True)
    role = Column(String(50), nullable=False, default="Viewer")
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    department = relationship("Department", back_populates="members", foreign_keys=[department_id], lazy="selectin")
    project_members = relationship("ProjectMember", back_populates="user", lazy="selectin")
    assigned_tickets = relationship("Ticket", back_populates="assignee", foreign_keys="[Ticket.assignee_id]", lazy="selectin")
    reported_tickets = relationship("Ticket", back_populates="reporter", foreign_keys="[Ticket.reporter_id]", lazy="selectin")
    comments = relationship("Comment", back_populates="user", lazy="selectin")
    time_entries = relationship("TimeEntry", back_populates="user", lazy="selectin")
    audit_logs = relationship("AuditLog", back_populates="actor", lazy="selectin")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"