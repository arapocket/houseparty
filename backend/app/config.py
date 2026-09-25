"""All configuration lives here, read from environment variables at startup.

If a required setting is missing the app refuses to boot, which is much better
than discovering it when the first user hits the endpoint that needs it.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://houseparty:houseparty@localhost:5432/houseparty"

    # Signs every login token. Anyone who knows it can sign in as anybody.
    jwt_secret: str = "dev-only-secret-do-not-use-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24 * 30

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_service_sid: str = ""

    admin_session_secret: str = "dev-only-admin-secret-do-not-use-in-production"
    admin_username: str = "admin"
    # Empty means the admin page refuses every login. Set it in .env.
    admin_password: str = ""

    # Where the app reaches this server. Used to build links to uploaded
    # photos when they're stored locally.
    public_base_url: str = "http://localhost:8000"

    # Photos. "local" keeps them in backend/uploads (dev); "r2" uses
    # Cloudflare R2. Moderation "off" lets everything through (dev);
    # "rekognition" uses Amazon's image moderation.
    storage_backend: str = "local"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_public_base_url: str = ""
    moderation_backend: str = "off"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Push notifications (Apple). Empty = dev: notifications are logged, not
    # sent. The private key is the contents of the .p8 file from Apple.
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_private_key: str = ""
    apns_bundle_id: str = "app.houseparty.HouseParty"
    apns_use_sandbox: bool = True
    # How long before a party starts its reminder goes out.
    party_reminder_hours: int = 2

    # Browser origins allowed to call the API. The iOS app does not need this;
    # it only matters if a web page ever talks to the API.
    cors_origins: list[str] = []

    # Product rules. These are decisions, not knobs for users to turn.
    min_age: int = 21
    max_interests_per_user: int = 12
    interest_max_length: int = 40
    default_radius_km: int = 15
    min_radius_km: int = 1
    max_radius_km: int = 50
    default_invite_cap: int = 20
    verification_code_ttl_seconds: int = 10 * 60
    verification_max_attempts: int = 5
    # How many codes one phone number can request per hour, so nobody can use
    # us to spam a number (or run up the SMS bill).
    verification_starts_per_hour: int = 5
    # Parties with no end time are treated as over this long after they start.
    default_party_length_hours: int = 8
    # How often the background job checks for parties that have ended.
    party_sweep_interval_seconds: int = 300

    @property
    def is_dev(self) -> bool:
        return self.env in ("dev", "test")

    @model_validator(mode="after")
    def real_secrets_outside_dev(self) -> Settings:
        """Refuse to start in production with the dev secrets still in place."""
        if not self.is_dev:
            for name in ("jwt_secret", "admin_session_secret"):
                value = getattr(self, name)
                if "dev-only" in value or len(value) < 32:
                    raise ValueError(f"Set a real {name.upper()} (32+ random characters).")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
