import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    parent_id = Column(String(36), ForeignKey("comments.id"), nullable=True)
    is_internal = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    ticket = relationship("Ticket", back_populates="comments", lazy="selectin")
    user = relationship("User", back_populates="comments", lazy="selectin")
    parent = relationship(
        "Comment",
        back_populates="replies",
        remote_side=[id],
        lazy="selectin",
    )
    replies = relationship(
        "Comment",
        back_populates="parent",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<Comment(id={self.id}, ticket_id={self.ticket_id}, user_id={self.user_id})>"