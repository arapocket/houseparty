# The server, packaged to run on AWS.
#
# Built for ARM (Graviton) because it's cheaper on AWS and matches Apple
# Silicon Macs, so what you build here is what runs there.

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

# Dependencies first, in their own layer: code changes then rebuild in
# seconds instead of reinstalling everything.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" ENV=production
EXPOSE 8000

# Bring the database up to date, then serve. --proxy-headers because AWS's
# load balancer sits in front and says who the real visitor is.
# One process on purpose: live chat and the party job assume a single server
# (see "Known gaps" in HANDOFF.md).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
