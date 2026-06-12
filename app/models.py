"""Modelli SQLAlchemy 2.0 (typed, async-ready)."""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConditionEnum(enum.Enum):
    NEW = "new"
    USED = "used"


class ListingStatusEnum(enum.Enum):
    ACTIVE = "active"
    SOLD = "sold"


class WatchReference(Base):
    """Una referenza di orologio tracciata (es. Rolex Daytona 116500LN)."""

    __tablename__ = "watch_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand: Mapped[str] = mapped_column(String(100), index=True)
    model: Mapped[str] = mapped_column(String(200))
    reference_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    estimated_market_value: Mapped[float | None] = mapped_column(Float, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    listings: Mapped[list["Listing"]] = relationship(
        back_populates="reference",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<WatchReference {self.brand} {self.reference_number}>"


class Listing(Base):
    """Un annuncio scoperto dallo scraper."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference_id: Mapped[int] = mapped_column(
        ForeignKey("watch_references.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2000), unique=True)
    price: Mapped[float] = mapped_column(Float)
    condition: Mapped[ConditionEnum] = mapped_column(
        Enum(ConditionEnum, values_callable=lambda e: [m.value for m in e]),
        default=ConditionEnum.USED,
    )
    has_box_papers: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ListingStatusEnum] = mapped_column(
        Enum(ListingStatusEnum, values_callable=lambda e: [m.value for m in e]),
        default=ListingStatusEnum.ACTIVE,
        index=True,
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    reference: Mapped[WatchReference] = relationship(back_populates="listings")

    def __repr__(self) -> str:
        return f"<Listing #{self.id} ref={self.reference_id} {self.price}€ {self.status.value}>"


class User(Base):
    """Utente Telegram registrato tramite /start."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    filters: Mapped[list["UserFilter"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User chat_id={self.telegram_chat_id} active={self.is_active}>"


class UserFilter(Base):
    """Criteri di alert dell'utente."""

    __tablename__ = "user_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    max_price: Mapped[float | None] = mapped_column(Float, default=None)
    min_margin_percentage: Mapped[float] = mapped_column(Float, default=10.0)
    target_brand: Mapped[str | None] = mapped_column(String(100), default=None)

    user: Mapped[User] = relationship(back_populates="filters")

    def __repr__(self) -> str:
        return (
            f"<UserFilter user={self.user_id} max_price={self.max_price} "
            f"min_margin={self.min_margin_percentage}% brand={self.target_brand}>"
        )


class SentAlert(Base):
    """Deduplicazione persistente delle notifiche: un alert per coppia utente/annuncio."""

    __tablename__ = "sent_alerts"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_sent_alert"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<SentAlert user={self.user_id} listing={self.listing_id}>"
