import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base

sermon_themes = Table(
    "sermon_themes",
    Base.metadata,
    Column(
        "sermon_id",
        UUID(as_uuid=True),
        ForeignKey("sermons.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "theme_id",
        UUID(as_uuid=True),
        ForeignKey("themes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

sermon_bible_references = Table(
    "sermon_bible_references",
    Base.metadata,
    Column(
        "sermon_id",
        UUID(as_uuid=True),
        ForeignKey("sermons.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "bible_reference_id",
        UUID(as_uuid=True),
        ForeignKey("bible_references.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    sermons = relationship("Sermon", secondary=sermon_themes, back_populates="themes")


class BibleReference(Base):
    __tablename__ = "bible_references"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    book: Mapped[str] = mapped_column(String(50), nullable=False)
    chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    verse_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verse_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_text: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    sermons = relationship(
        "Sermon", secondary=sermon_bible_references, back_populates="bible_references"
    )
