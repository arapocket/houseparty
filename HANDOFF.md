# House Party — handoff

Written 2026-09-24, updated the same day after session 2. The backend runs; the iOS app is not started.

## What the product is

An iOS app for **hosting house parties**. People find each other through
free-text interests, match mutually, and hosts invite their matches to parties
they're throwing. Interests are the discovery mechanism; parties are the point.

The reason interests are free text (not a fixed list) is to let people be as
specific as possible — "Kid A era Radiohead", not "Music".

## Product decisions already made (do not re-litigate)

**Profile**
- Photo, first name, age, neighborhood, short bio
- Up to 12 interests, 40 characters each, free text
- "Down to party" — a simple on/off toggle, no date range
- **21+**, verified by birthdate at signup
- **No age filtering of any kind** beyond the 21+ floor
- Phone verification at signup

**Interest matching**
- Normalize before matching: lowercase, strip punctuation, collapse spaces
- Suggest existing interests while typing, ranked by popularity, so wording
  converges over time
- No AI/semantic matching in v1 (was discussed, deferred)

**Discover**
- **Interest-first list** (scrollable rows, shared interests are the headline,
  photo small) — not swipe cards, not photo-first
- Ranked by number of shared interests, then distance
- Radius is user-set, default 15 km, range 1–50 km
- **The app never offers to widen the radius.** Explicitly rejected.

**Matching**
- Mutual: both people must like each other
- No DMs between matches

**Parties**
- Anyone can host
- **Always invite-only.** No browsing or discovering parties, no join requests.
- **A host can only invite people they have matched with**
- **20 invites per party.** To exceed it, the host submits a request that an
  admin approves (raises `User.invite_cap`).
- Only the host adds people, and can remove anyone they added
- Guests can **suggest** people to the host. Since hosts can only invite their
  own matches, a suggestion works as an *introduction*: both parties surface at
  the top of each other's Discover, and if they match the host can invite.
- Exact address is hidden until an invite is accepted; before that, neighborhood
  and rounded distance only
- Cancelling a party **leaves the chat open**

**Invite screen shows:** host profile, party theme/description/date, who else is
going, neighborhood + distance.

**Chat — two kinds, deliberately different politics**

This resolves a conflict in the original answers. Confirm with the user if it
comes up, but it's the current design:

| | Planning chat | Reunion chat |
|---|---|---|
| When | Exists from party creation | Opens after the party ends |
| Who's in it | Host + guests who accepted | Opt-in; anyone who hosted or attended |
| Control | Host adds/removes | Members vote each other out |
| Host powers | Yes | **None — host can be voted out** |
| Lifetime | Open indefinitely | Open indefinitely |

- Vote to kick = simple majority of active members excluding the target
  (`votes_needed()` in `app/services/chat.py`). Under 2 other members, kicking
  is off.
- Someone removed by vote is not re-added automatically.
- The reunion chat should carry a **"host again"** action somewhere, creating a
  new party with the same group (`Party.source_party_id` exists for this).

**Passes** (answered session 2)
- Passes aren't final. A separate "Passed" screen lists everyone you passed
  on, newest first, and you can like them from there (`GET /discover/passed`).

**Party location** (answered session 2)
- The host drops a pin for every party; it's required. Guests see only a
  rounded distance from it until they accept.

**Feedback/ratings**
- Post-party "would you party with them again?" is **private only**. No public
  scores, no badges. Used internally to flag bad actors.

**Chat votes** (answered session 2) — anonymous: members see a running
count ("2 of 3 votes to remove"), never who voted. You can take a vote back.

**Host again** (answered session 2) — opens the create screen pre-filled
with the old title, description, neighborhood and interests.

**Notifications** — user said "just do whatever". Suggested set: new match,
invite received, invite accepted, new message (mutable per chat), party reminder.

**Safety** — non-negotiable, this app puts strangers in homes:
- Exact location never leaves the server; distances rounded to whole km
- Address withheld until accepted
- Block and report on profiles, parties, messages
- 21+ only, phone verified

## Stack decisions

**Backend: FastAPI.** The user first chose Django, then switched to FastAPI
because their goal is to *learn Python* and FastAPI hides less. Consequences we
accepted: no Django admin (using SQLAdmin instead), auth is ours to build,
chat uses FastAPI's built-in WebSockets.

- Python 3.12+, `uv` for packaging
- SQLAlchemy 2.0 async + asyncpg + Alembic, Postgres
- Pydantic v2 + pydantic-settings
- PyJWT for tokens; Twilio Verify for SMS codes (stubbed in dev)
- SQLAdmin for moderation review
- pytest, ruff, mypy

**iOS: native only** (user explicitly ruled out React Native).
Swift 6 / SwiftUI / `@Observable` / async-await / SwiftData or GRDB /
URLSession + Codable by hand. **No OpenAPI codegen** — the user rejected it as
not worth the ceremony for a solo project. Write `Codable` structs by hand.

## Repo state (updated 2026-09-24, session 2)

**The backend runs.** All endpoints are written, 48 tests pass, ruff and mypy
are clean, and it has been exercised against a live server (Discover, chat
WebSocket, admin login and ban). No commits yet.

### Running it

Postgres 15 (Homebrew) is already running on this machine; roles and the
`houseparty` / `houseparty_test` databases exist. `uv` is installed.

```bash
cd ~/houseparty/backend
uv run alembic upgrade head          # apply migrations
uv run python -m scripts.seed --reset  # 13 people around SoHo; prints a token for "You"
uv run uvicorn app.main:app --reload # http://localhost:8000/docs
uv run pytest                        # uses the houseparty_test database
```

Admin page: `http://localhost:8000/admin`, user `admin`, password from
`ADMIN_PASSWORD` in `.env` (empty means no logins).

### Layout

| Where | What |
|---|---|
| `app/main.py` | app, router list, `RuleError` → JSON handler, background job that completes ended parties every 5 min |
| `app/errors.py` | `RuleError(message, status_code)`, the only error services raise |
| `app/deps.py` | `Session`, `CurrentUser`, `OnboardedUser` (`Annotated` aliases used by every route) |
| `app/routers/` | auth, profile, interests, discover, matches, parties, invites, chat (incl. WebSocket), safety |
| `app/services/` | the rules: auth, profiles, interests, matching, parties, chat, safety, geo |
| `app/presenters.py` | row → response; the single place that decides what is public |
| `app/admin.py` | SQLAdmin: reports, users (ban), bigger-party requests (approve/deny), interests (block), feedback |
| `migrations/` | Alembic, async; one initial migration. DB URL comes from `.env` |
| `scripts/seed.py` | dev data |
| `tests/` | `test_rules.py` pure functions; `test_api.py` end-to-end against real Postgres |

### Fixed in session 2

- Introductions boosted a suggested person in *everyone's* Discover and
  duplicated rows; now only host ↔ suggested person see each other, and
  introductions show even with no shared interests (radius still applies).
- A match marked unrelated suggestions as fulfilled; now only the right pair.
- Wrong verification codes were rolled back with the request, so attempts
  were never counted (unlimited guessing). Fixed and tested.
- Rate limit on `POST /auth/phone/start`: 5 per number per hour.
- Kick votes from people who later left no longer count.
- Kicked/removed people get hung up on the live chat socket (close code 4403).
- Missing host → 404 instead of a crash; party `distance_km` is now filled in.
- App refuses to boot outside dev/test with the default secrets.
- Added the missing "would you party again?" table and endpoint (`PartyFeedback`).

### Small calls made in session 2 (reversible; mention if relevant)

- Birthdate can be set once, never changed.
- A guest who accepted can back out later (`respond` with `accept: false`).
- Parties with no end time are treated as over 8 hours after they start.
- A party you can't see returns 404, not 403, so its existence isn't confirmed.
- Deleting an account scrubs the profile, cancels their upcoming parties, and
  frees the phone number; the row stays because messages point at it.
- `PartyIn.source_party_id` exists for "host again"; only people who were at
  the source party may use it. The iOS flow for it is still an open question.

### Still to do

1. **iOS app** — `ios/`, open `ios/HouseParty.xcodeproj`. Built and tried in the
   iOS 27 simulator: sign-in, onboarding, Discover (+ Passed list), Parties
   (list, create with map pin, invite matches, accept/decline, suggest), Me.
   Chats too: live messages over WebSocket, reunion join, anonymous
   vote-out with take-back, report/block by long-press, "host again".
   **Still to build:** photo upload, "would you party again?" after a party,
   push notifications, editing a party.
   Look: always dark; serif (New York) everywhere; pink→blue accents; the
   "like" is an acid-house smiley. All of it lives in `ios/HouseParty/Design/`
   (font, corner sizes, colors) — screens don't pick their own.
2. **Push notifications** — nothing sends any yet (needs APNs + device-token
   table). Suggested set: new match, invite received, invite accepted, new
   message (mutable per chat), party reminder.
3. **Photo upload** — only a `photo_url` field. Recommended: S3/R2 presigned
   URLs. Photo moderation undecided.
4. `Interest.BLOCKED_WORDS` is still a two-item placeholder.
5. `ConnectionManager` and the party-completion job assume one server
   process. Fine until there's a second one (then Redis pub/sub + a real
   scheduler).
6. `suggest()` uses `LIKE '%term%'`; move to `pg_trgm` when it's slow.

## How the user works

- Wants **plain English**, no jargon. They pushed back hard on it twice.
- Blunt, decides fast, and will reverse a decision without ceremony. Ask
  focused questions; don't present surveys of options.
- Doesn't want spec documents — asked to build and keep brainstorming.
- Learning Python. Favor readable code that shows what's happening over clever
  or heavily abstracted code.

## Open questions never answered

- Photo storage and moderation of uploaded photos

## Machine notes

- macOS 27 is installed. Until the Xcode license is accepted
  (`sudo xcodebuild -license`), the system `python3` won't run; use
  `uv run python` or `backend/.venv/bin/python` instead.
