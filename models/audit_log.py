import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from database import Base


class AuditActionType(str, enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User", back_populates="audit_logs", lazy="selectin")

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, entity_type={self.entity_type}, entity_id={self.entity_id})>"