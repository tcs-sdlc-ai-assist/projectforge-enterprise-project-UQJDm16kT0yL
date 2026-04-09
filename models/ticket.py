import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Date,
    ForeignKey,
    Table,
    func,
)
from sqlalchemy.orm import relationship

from database import Base


ticket_labels = Table(
    "ticket_labels",
    Base.metadata,
    Column("ticket_id", String(36), ForeignKey("tickets.id"), primary_key=True),
    Column("label_id", String(36), ForeignKey("labels.id"), primary_key=True),
)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_key = Column(String(50), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    sprint_id = Column(String(36), ForeignKey("sprints.id"), nullable=True)
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reporter_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    parent_id = Column(String(36), ForeignKey("tickets.id"), nullable=True)
    status = Column(String(50), nullable=False, default="Open")
    type = Column(String(50), nullable=False, default="Task")
    ticket_type = Column(String(50), nullable=True)
    priority = Column(String(50), nullable=False, default="Medium")
    due_date = Column(Date, nullable=True)
    closed_date = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="tickets", lazy="selectin")
    sprint = relationship("Sprint", back_populates="tickets", lazy="selectin")
    assignee = relationship(
        "User",
        foreign_keys=[assignee_id],
        back_populates="assigned_tickets",
        lazy="selectin",
    )
    reporter = relationship(
        "User",
        foreign_keys=[reporter_id],
        back_populates="reported_tickets",
        lazy="selectin",
    )
    parent = relationship(
        "Ticket",
        remote_side=[id],
        back_populates="children",
        lazy="selectin",
    )
    children = relationship(
        "Ticket",
        back_populates="parent",
        lazy="selectin",
    )
    labels = relationship(
        "Label",
        secondary=ticket_labels,
        back_populates="tickets",
        lazy="selectin",
    )
    comments = relationship(
        "Comment",
        back_populates="ticket",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    time_entries = relationship(
        "TimeEntry",
        back_populates="ticket",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def is_overdue(self):
        if self.due_date and self.status not in ("Closed",):
            if isinstance(self.due_date, date):
                return self.due_date < date.today()
        return False

    def __repr__(self):
        return f"<Ticket(id={self.id}, title={self.title}, status={self.status})>"