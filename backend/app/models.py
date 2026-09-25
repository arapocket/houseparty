"""Database tables.

Kept in one file on purpose: the whole data model fits on a couple of screens,
which is worth more than tidy folders while the shape is still moving.

Status/kind columns are plain strings with the allowed values listed above them,
rather than database enums, because changing a database enum later needs an
awkward migration and we will change these.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# ---------------------------------------------------------------------------
# allowed values for the string columns below
# ---------------------------------------------------------------------------

DECISION_LIKE = "like"
DECISION_PASS = "pass"

INVITE_PENDING = "pending"
INVITE_ACCEPTED = "accepted"
INVITE_DECLINED = "declined"
INVITE_REVOKED = "revoked"

PARTY_ACTIVE = "active"
PARTY_CANCELLED = "cancelled"
PARTY_COMPLETED = "completed"

# The planning chat belongs to the host: they add and remove people.
# The reunion chat is a peer group: members vote each other out, host included.
CHAT_PLANNING = "planning"
CHAT_REUNION = "reunion"

SUGGESTION_PENDING = "pending"
SUGGESTION_MATCHED = "matched"
SUGGESTION_DISMISSED = "dismissed"

REQUEST_PENDING = "pending"
REQUEST_APPROVED = "approved"
REQUEST_DENIED = "denied"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# people
# ---------------------------------------------------------------------------


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # 48 rather than 32 so a deleted account's "deleted:<id>" placeholder fits.
    phone: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    first_name: Mapped[str | None] = mapped_column(String(40))
    birthdate: Mapped[date | None] = mapped_column(Date)
    bio: Mapped[str | None] = mapped_column(String(300))
    photo_url: Mapped[str | None] = mapped_column(String(500))

    # Never returned to other users. Only a rounded distance is exposed.
    neighborhood: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    search_radius_km: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    down_to_party: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # How many people this user may invite to a single party. Raised by an
    # approved InviteCapRequest.
    invite_cap: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    interests: Mapped[list[UserInterest]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_onboarded(self) -> bool:
        return bool(self.first_name and self.birthdate and self.phone_verified_at)


class Interest(Base, TimestampMixin):
    """One row per distinct interest, shared by everyone who typed it.

    `normalized` is what we match on (lowercased, punctuation and extra spaces
    stripped). `display` is the first spelling anybody used, which is what we
    show and suggest.
    """

    __tablename__ = "interests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    normalized: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    display: Mapped[str] = mapped_column(String(60), nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (Index("ix_interests_usage", "usage_count"),)


class UserInterest(Base):
    __tablename__ = "user_interests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    interest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interests.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="interests")
    interest: Mapped[Interest] = relationship(lazy="joined")


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------


class Decision(Base):
    """A like or a pass. One row per direction, so we can tell who liked first."""

    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("actor_id", "target_id", name="uq_decision_pair"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Match(Base):
    """Created when two people have both liked each other.

    user_low/user_high hold the same pair in a fixed order so the unique
    constraint catches duplicates no matter who liked first.
    """

    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("user_low_id", "user_high_id", name="uq_match_pair"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_low_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_high_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    blocker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# parties
# ---------------------------------------------------------------------------


class Party(Base, TimestampMixin):
    __tablename__ = "parties"

    id: Mapped[uuid.UUID] = _uuid_pk()
    host_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    neighborhood: Mapped[str] = mapped_column(String(80), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    # Only sent to guests whose invite is accepted.
    address: Mapped[str | None] = mapped_column(String(300))

    guest_cap: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PARTY_ACTIVE, nullable=False)

    # Set when created via "host again", so we can show the lineage.
    source_party_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parties.id", ondelete="SET NULL")
    )

    __table_args__ = (CheckConstraint("guest_cap > 0", name="ck_party_cap_positive"),)


class PartyInterest(Base):
    __tablename__ = "party_interests"

    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True
    )
    interest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interests.id", ondelete="CASCADE"), primary_key=True
    )

    interest: Mapped[Interest] = relationship(lazy="joined")


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (UniqueConstraint("party_id", "invitee_id", name="uq_invite_party_user"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invitee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default=INVITE_PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Suggestion(Base):
    """A guest pointing the host at someone they know.

    The host can only invite their own matches, so a suggestion works as an
    introduction: both people see each other boosted in Discover, and if they
    match the host can then invite them.
    """

    __tablename__ = "suggestions"
    __table_args__ = (
        UniqueConstraint("party_id", "suggested_user_id", name="uq_suggestion_party_user"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suggested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    suggested_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default=SUGGESTION_PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InviteCapRequest(Base):
    """Hosts asking to invite more than their cap. Reviewed in the admin page."""

    __tablename__ = "invite_cap_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    host_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parties.id", ondelete="CASCADE"))
    requested_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=REQUEST_PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"
    __table_args__ = (UniqueConstraint("party_id", "kind", name="uq_chat_party_kind"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(String(80))


class ChatMember(Base):
    __tablename__ = "chat_members"
    __table_args__ = (UniqueConstraint("chat_id", "user_id", name="uq_chat_member"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_host: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by_vote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KickVote(Base):
    """Votes to remove someone from a reunion chat. One row per voter/target."""

    __tablename__ = "kick_votes"
    __table_args__ = (UniqueConstraint("chat_id", "target_id", "voter_id", name="uq_kick_vote"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# safety
# ---------------------------------------------------------------------------


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    subject_party_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE")
    )
    subject_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE")
    )
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PartyFeedback(Base):
    """ "Would you party with them again?" after a party.

    Private. Nobody ever sees their own or anyone else's answers; it exists so
    an admin can spot people who keep getting a "no".
    """

    __tablename__ = "party_feedback"
    __table_args__ = (
        UniqueConstraint("party_id", "author_id", "subject_id", name="uq_feedback_once"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    would_party_again: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PhoneVerification(Base):
    """Short-lived signup codes. Only used when Twilio Verify is not configured."""

    __tablename__ = "phone_verifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
