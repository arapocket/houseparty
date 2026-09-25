"""All configuration lives here, read from environment variables at startup.

If a required setting is missing the app refuses to boot, which is much better
than discovering it when the first user hits the endpoint that needs it.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://houseparty:houseparty@localhost:5432/houseparty"
    # On AWS the database login arrives as separate pieces (from Secrets
    # Manager) instead of one URL. If DB_HOST is set, these win.
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "houseparty"
    db_username: str = ""
    db_password: str = ""

    # Signs every login token. Anyone who knows it can sign in as anybody.
    jwt_secret: str = "dev-only-secret-do-not-use-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24 * 30

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_service_sid: str = ""
    # Outside dev, sign-in codes are only ever texted. For a test deployment
    # before Twilio is set up, this lets them go to the server log instead.
    allow_logged_codes: bool = False

    admin_session_secret: str = "dev-only-admin-secret-do-not-use-in-production"
    admin_username: str = "admin"
    # Empty means the admin page refuses every login. Set it in .env.
    admin_password: str = ""

    # Photos. "local" keeps them in backend/uploads (dev); "s3" puts them in
    # an S3 bucket that CloudFront serves at /photos/. Moderation "off" lets
    # everything through (dev); "rekognition" uses Amazon's image moderation.
    # On AWS no keys are needed: the server's own AWS role grants access.
    storage_backend: str = "local"
    s3_bucket: str = ""
    moderation_backend: str = "off"
    aws_region: str = "us-east-1"

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
    def database_from_parts(self) -> Settings:
        if self.db_host:
            # quote_plus: generated passwords can contain characters like @ or /
            # that would otherwise break the URL.
            self.database_url = (
                f"postgresql+asyncpg://{quote_plus(self.db_username)}:"
                f"{quote_plus(self.db_password)}@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self

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
