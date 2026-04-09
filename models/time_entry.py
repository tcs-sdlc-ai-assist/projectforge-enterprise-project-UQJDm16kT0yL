import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    hours = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    logged_date = Column(Date, nullable=False, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="time_entries", lazy="selectin")
    user = relationship("User", back_populates="time_entries", lazy="selectin")