import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import date, datetime

from sqlalchemy import Column, DateTime, Date, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Sprint(Base):
    __tablename__ = "sprints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    status = Column(String(20), nullable=False, default="Planning")
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="sprints", lazy="selectin")
    tickets = relationship("Ticket", back_populates="sprint", lazy="selectin")

    def __repr__(self):
        return f"<Sprint(id={self.id}, name='{self.name}', status='{self.status}')>"