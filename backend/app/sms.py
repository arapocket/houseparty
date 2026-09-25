"""Sending verification codes.

In dev the code is printed to the console, so you can sign up without paying
Twilio or owning a phone number. Set the Twilio settings to switch to real SMS.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.errors import RuleError

log = logging.getLogger("houseparty.sms")


def twilio_configured() -> bool:
    return bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_verify_service_sid
    )


async def send_code(phone: str, code: str) -> None:
    if not twilio_configured():
        if not (settings.is_dev or settings.allow_logged_codes):
            # Never quietly log real people's codes in production.
            raise RuleError("Sign-in texts aren't working right now. Try again soon.", 503)
        log.warning("[dev] verification code for %s is %s", phone, code)
        return

    url = (
        f"https://verify.twilio.com/v2/Services/{settings.twilio_verify_service_sid}/Verifications"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            url,
            data={"To": phone, "Channel": "sms"},
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        )
        response.raise_for_status()


async def check_code(phone: str, code: str) -> bool:
    """Ask Twilio whether the code is right. Only used when Twilio is set up;
    in dev we check our own stored code instead (see services/auth.py)."""
    url = (
        f"https://verify.twilio.com/v2/Services/"
        f"{settings.twilio_verify_service_sid}/VerificationCheck"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            url,
            data={"To": phone, "Code": code},
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        )
    # Twilio answers 404 when the code expired or was already used.
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return response.json().get("status") == "approved"
