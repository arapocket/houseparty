"""The admin page at /admin. The only moderation tool there is.

What you can do here:
  * read reports and mark them handled
  * ban and unban people
  * approve or deny requests for bigger parties
  * block interests nobody should be able to use
  * see private "would you party again?" answers, to spot bad actors

Log in with ADMIN_USERNAME / ADMIN_PASSWORD from .env. If ADMIN_PASSWORD is
empty, nobody can log in.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from sqladmin import Admin, ModelView, action
from sqladmin.authentication import AuthenticationBackend

from app.config import settings
from app.db import SessionFactory, engine
from app.models import (
    REQUEST_APPROVED,
    REQUEST_DENIED,
    REQUEST_PENDING,
    Interest,
    InviteCapRequest,
    Party,
    PartyFeedback,
    Report,
    User,
)


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        if not settings.admin_password:
            return False
        # compare_digest takes the same time whether the guess is close or
        # not, so nobody can work the password out by timing the response.
        ok = secrets.compare_digest(username, settings.admin_username) and secrets.compare_digest(
            password, settings.admin_password
        )
        if ok:
            request.session.update({"admin": True})
        return ok

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin"))


def selected_ids(request: Request) -> list[uuid.UUID]:
    """The rows ticked in the list (or the one being viewed)."""
    raw = request.query_params.get("pks", "")
    return [uuid.UUID(pk) for pk in raw.split(",") if pk]


def back_to_list(request: Request, view: ModelView) -> RedirectResponse:
    return RedirectResponse(request.url_for("admin:list", identity=view.identity))


class ReportAdmin(ModelView, model=Report):
    name_plural = "Reports"
    icon = "fa-solid fa-flag"
    can_create = False
    can_edit = False
    column_list = [
        Report.created_at,
        Report.status,
        Report.reason,
        Report.note,
        Report.reporter_id,
        Report.subject_user_id,
        Report.subject_party_id,
        Report.subject_message_id,
    ]
    column_default_sort = [(Report.created_at, True)]

    @action(name="resolve", label="Mark handled")
    async def resolve(self, request: Request) -> RedirectResponse:
        async with SessionFactory() as session:
            for pk in selected_ids(request):
                report = await session.get(Report, pk)
                if report:
                    report.status = "resolved"
            await session.commit()
        return back_to_list(request, self)


class UserAdmin(ModelView, model=User):
    name_plural = "Users"
    icon = "fa-solid fa-user"
    can_create = False
    can_delete = False
    column_list = [
        User.first_name,
        User.phone,
        User.neighborhood,
        User.is_banned,
        User.invite_cap,
        User.created_at,
        User.deleted_at,
    ]
    column_searchable_list = [User.first_name, User.phone]
    # Exact location stays out of the admin page too.
    column_details_exclude_list = [User.latitude, User.longitude]
    form_columns = [User.invite_cap, User.is_banned]

    @action(name="ban", label="Ban", confirmation_message="Ban the selected people?")
    async def ban(self, request: Request) -> RedirectResponse:
        await self._set_banned(request, True)
        return back_to_list(request, self)

    @action(name="unban", label="Unban")
    async def unban(self, request: Request) -> RedirectResponse:
        await self._set_banned(request, False)
        return back_to_list(request, self)

    async def _set_banned(self, request: Request, banned: bool) -> None:
        async with SessionFactory() as session:
            for pk in selected_ids(request):
                user = await session.get(User, pk)
                if user:
                    user.is_banned = banned
            await session.commit()


class InviteCapRequestAdmin(ModelView, model=InviteCapRequest):
    name = "Bigger party request"
    name_plural = "Bigger party requests"
    icon = "fa-solid fa-users"
    can_create = False
    can_edit = False
    column_list = [
        InviteCapRequest.created_at,
        InviteCapRequest.status,
        InviteCapRequest.host_id,
        InviteCapRequest.party_id,
        InviteCapRequest.requested_cap,
        InviteCapRequest.reason,
    ]
    column_default_sort = [(InviteCapRequest.created_at, True)]

    @action(name="approve", label="Approve")
    async def approve(self, request: Request) -> RedirectResponse:
        async with SessionFactory() as session:
            for pk in selected_ids(request):
                row = await session.get(InviteCapRequest, pk)
                if row is None or row.status != REQUEST_PENDING:
                    continue
                row.status = REQUEST_APPROVED
                row.decided_at = datetime.now(UTC)
                # Raise the host's limit for future parties, and this party's
                # limit right away.
                host = await session.get(User, row.host_id)
                if host:
                    host.invite_cap = max(host.invite_cap, row.requested_cap)
                if row.party_id:
                    party = await session.get(Party, row.party_id)
                    if party:
                        party.guest_cap = max(party.guest_cap, row.requested_cap)
            await session.commit()
        return back_to_list(request, self)

    @action(name="deny", label="Deny")
    async def deny(self, request: Request) -> RedirectResponse:
        async with SessionFactory() as session:
            for pk in selected_ids(request):
                row = await session.get(InviteCapRequest, pk)
                if row and row.status == REQUEST_PENDING:
                    row.status = REQUEST_DENIED
                    row.decided_at = datetime.now(UTC)
            await session.commit()
        return back_to_list(request, self)


class InterestAdmin(ModelView, model=Interest):
    name_plural = "Interests"
    icon = "fa-solid fa-tag"
    can_create = False
    column_list = [Interest.display, Interest.usage_count, Interest.is_blocked]
    column_searchable_list = [Interest.display, Interest.normalized]
    column_default_sort = [(Interest.usage_count, True)]
    form_columns = [Interest.display, Interest.is_blocked]


class FeedbackAdmin(ModelView, model=PartyFeedback):
    name = "Party feedback"
    name_plural = "Party feedback"
    icon = "fa-solid fa-comment"
    can_create = False
    can_edit = False
    column_list = [
        PartyFeedback.created_at,
        PartyFeedback.subject_id,
        PartyFeedback.would_party_again,
        PartyFeedback.note,
        PartyFeedback.author_id,
        PartyFeedback.party_id,
    ]
    column_default_sort = [(PartyFeedback.created_at, True)]


def mount_admin(app: FastAPI) -> None:
    admin = Admin(
        app,
        engine,
        title="House Party admin",
        authentication_backend=AdminAuth(secret_key=settings.admin_session_secret),
    )
    for view in (ReportAdmin, UserAdmin, InviteCapRequestAdmin, InterestAdmin, FeedbackAdmin):
        admin.add_view(view)
