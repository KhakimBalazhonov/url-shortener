from datetime import datetime

from sqlalchemy import DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_url: Mapped[str] = mapped_column(String(2048))
    short_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    clicks_count: Mapped[int] = mapped_column(server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Индексирует только ссылки с установленным сроком действия, исключая бессрочные ссылки
        # Используется фоновой задачей для поиска и удаления просроченных ссылок
        Index("ix_links_expires_at", "expires_at", postgresql_where=text("expires_at IS NOT NULL")),
    )
