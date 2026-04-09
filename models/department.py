import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), unique=True, nullable=False, index=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    head_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    head = relationship("User", foreign_keys=[head_id], back_populates="headed_department", lazy="selectin")
    members = relationship("User", foreign_keys="[User.department_id]", back_populates="department", lazy="selectin")
    projects = relationship("Project", back_populates="department", lazy="selectin")

    def __repr__(self):
        return f"<Department(id={self.id}, name={self.name}, code={self.code})>"

    @property
    def member_count(self):
        if self.members:
            return len(self.members)
        return 0