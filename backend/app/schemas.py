"""Request and response shapes.

These are the contract the iOS app codes against, and the place bad input gets
rejected before it reaches any logic.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings

# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


def clean_phone(raw: str) -> str:
    """Accept "+1 (415) 555-0100" and store "+14155550100".

    Numbers must include the country code, which is the format Twilio wants.
    """
    digits = re.sub(r"[\s().-]", "", raw)
    if not re.fullmatch(r"\+[1-9]\d{6,14}", digits):
        raise ValueError("Enter the number with its country code, like +1 415 555 0100.")
    return digits


class PhoneStartIn(BaseModel):
    phone: str = Field(min_length=7, max_length=32)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return clean_phone(value)


class PhoneVerifyIn(BaseModel):
    phone: str = Field(min_length=7, max_length=32)
    code: str = Field(min_length=4, max_length=8)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return clean_phone(value)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    needs_onboarding: bool


# ---------------------------------------------------------------------------
# interests
# ---------------------------------------------------------------------------


class InterestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display: str
    usage_count: int


class InterestSuggestionOut(BaseModel):
    display: str
    usage_count: int


class InterestsIn(BaseModel):
    """The full list, replacing whatever was there. Simpler for the client than
    add/remove calls, and it keeps ordering meaningful."""

    interests: list[str] = Field(max_length=settings.max_interests_per_user)

    @field_validator("interests")
    @classmethod
    def check_lengths(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value.strip()) < 2:
                raise ValueError("Interests need at least 2 characters.")
            if len(value.strip()) > settings.interest_max_length:
                raise ValueError(f"Keep interests under {settings.interest_max_length} characters.")
        return values


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------


class ProfileIn(BaseModel):
    """PATCH /me. Every field is optional; only the ones sent are changed.

    Birthdate can be set once and never changed, or the 21+ check would be
    meaningless.
    """

    first_name: str | None = Field(default=None, min_length=1, max_length=40)
    birthdate: date | None = None
    bio: str | None = Field(default=None, max_length=300)
    neighborhood: str | None = Field(default=None, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    search_radius_km: int | None = Field(
        default=None, ge=settings.min_radius_km, le=settings.max_radius_km
    )
    down_to_party: bool | None = None


class PublicProfileOut(BaseModel):
    """What other people see. No exact location, no phone, no age filtering."""

    id: uuid.UUID
    first_name: str | None
    age: int | None
    bio: str | None
    photo_url: str | None
    neighborhood: str | None
    down_to_party: bool
    interests: list[str]


class MeOut(PublicProfileOut):
    phone: str
    # True while a newly uploaded photo waits for a person to check it.
    photo_in_review: bool = False
    search_radius_km: int
    invite_cap: int
    needs_onboarding: bool


# ---------------------------------------------------------------------------
# discover / matching
# ---------------------------------------------------------------------------


class DiscoverCardOut(BaseModel):
    user: PublicProfileOut
    shared_interests: list[str]
    distance_km: int
    suggested_for_party_id: uuid.UUID | None = None


class DecisionIn(BaseModel):
    decision: str

    @field_validator("decision")
    @classmethod
    def valid(cls, value: str) -> str:
        if value not in ("like", "pass"):
            raise ValueError("decision must be 'like' or 'pass'")
        return value


class PassedOut(BaseModel):
    """One row in the "Passed" list. Liking someone from here uses the normal
    POST /discover/{user_id}/decision."""

    user: PublicProfileOut
    shared_interests: list[str]
    passed_at: datetime


class DecisionOut(BaseModel):
    matched: bool
    match_id: uuid.UUID | None = None


class MatchOut(BaseModel):
    user: PublicProfileOut
    matched_at: datetime
    shared_interests: list[str]


# ---------------------------------------------------------------------------
# parties
# ---------------------------------------------------------------------------


class PartyIn(BaseModel):
    # AwareDatetime rejects times without a timezone. "8pm" means nothing on a
    # server that does not know which city you are in.
    title: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None
    neighborhood: str = Field(min_length=1, max_length=80)
    # The pin the host drops for this party. Guests only ever see a rounded
    # distance from it; the exact spot and address wait until they accept.
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # Free text for the details a pin can't carry: "Apt 4B, buzz twice".
    address: str | None = Field(default=None, max_length=300)
    interests: list[str] = Field(min_length=1, max_length=5)
    # Set by "host again" from a reunion chat.
    source_party_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def ends_after_start(self) -> PartyIn:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("The party has to end after it starts.")
        return self


class PartyUpdateIn(BaseModel):
    """PATCH /parties/{id}. Only the fields sent are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    neighborhood: str | None = Field(default=None, min_length=1, max_length=80)
    address: str | None = Field(default=None, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    interests: list[str] | None = Field(default=None, min_length=1, max_length=5)

    @model_validator(mode="after")
    def pin_moves_as_a_pair(self) -> PartyUpdateIn:
        sent = self.model_fields_set
        if ("latitude" in sent) != ("longitude" in sent):
            raise ValueError("Send latitude and longitude together to move the pin.")
        if "latitude" in sent and (self.latitude is None or self.longitude is None):
            raise ValueError("A party always needs a pin.")
        return self


class PartyOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime | None
    neighborhood: str
    status: str
    interests: list[str]
    host: PublicProfileOut
    guest_count: int
    guest_cap: int
    invites_left: int
    distance_km: int | None = None
    # Only filled in once your invite is accepted, or if you are the host.
    address: str | None = None
    my_invite_status: str | None = None
    guests: list[PublicProfileOut] = []
    # The exact pin. Only ever sent to the host, so they can edit it.
    latitude: float | None = None
    longitude: float | None = None


class InviteIn(BaseModel):
    user_id: uuid.UUID


class InviteOut(BaseModel):
    id: uuid.UUID
    party_id: uuid.UUID
    status: str
    created_at: datetime
    party: PartyOut | None = None


class GuestOut(BaseModel):
    """The host's view of one invite: who, and where it stands."""

    invite_id: uuid.UUID
    user: PublicProfileOut
    status: str


class InviteRespondIn(BaseModel):
    accept: bool


class SuggestGuestIn(BaseModel):
    user_id: uuid.UUID


class BiggerPartyIn(BaseModel):
    requested_cap: int = Field(gt=settings.default_invite_cap, le=200)
    reason: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


class ChatOut(BaseModel):
    id: uuid.UUID
    party_id: uuid.UUID
    kind: str
    title: str | None
    member_count: int
    joined: bool
    can_join: bool
    # For the chat list preview. Empty until someone says something.
    last_message: str | None = None
    last_message_at: datetime | None = None
    last_sender_name: str | None = None
    muted: bool = False


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    sender_id: uuid.UUID | None
    sender_name: str | None
    body: str
    created_at: datetime


class KickVoteIn(BaseModel):
    user_id: uuid.UUID


class ChatMemberOut(BaseModel):
    user: PublicProfileOut
    is_host: bool
    # Reunion chats only. Votes are anonymous: everyone sees the count,
    # nobody sees who voted. `i_voted` is only about the person asking.
    votes_to_remove: int = 0
    votes_needed: int = 0
    i_voted: bool = False


class KickVoteOut(BaseModel):
    votes: int
    votes_needed: int
    removed: bool


# ---------------------------------------------------------------------------
# safety
# ---------------------------------------------------------------------------


class ReportIn(BaseModel):
    subject_user_id: uuid.UUID | None = None
    subject_party_id: uuid.UUID | None = None
    subject_message_id: uuid.UUID | None = None
    reason: str = Field(max_length=40)
    note: str | None = Field(default=None, max_length=1000)


class BlockIn(BaseModel):
    user_id: uuid.UUID


class FeedbackIn(BaseModel):
    """ "Would you party with them again?" Private; never shown to anyone."""

    user_id: uuid.UUID
    would_party_again: bool
    note: str | None = Field(default=None, max_length=1000)


class PhotoOut(BaseModel):
    live: bool
    me: MeOut


class MyFeedbackOut(BaseModel):
    """Your own "would you party again?" answers for one party, so the app
    can show what you already said. Never anyone else's."""

    answers: dict[uuid.UUID, bool]


class DeviceIn(BaseModel):
    """The push token iOS hands the app for this phone."""

    token: str = Field(min_length=8, max_length=200)


class MuteIn(BaseModel):
    muted: bool


class SimpleOk(BaseModel):
    ok: bool = True
