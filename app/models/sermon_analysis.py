import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base


class SermonAnalysis(Base):
    __tablename__ = "sermon_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    sermon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sermons.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_teachings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    action_points: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reflection_questions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
