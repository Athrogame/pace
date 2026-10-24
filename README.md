# Pace

A planner and AI coach for students with jobs. It fits homework around school, shifts and
sleep, shows the cost of an extra shift before you say yes, learns how long your work really
takes, and backs off when you're running on empty.

**Pace is live:** [Open the app](https://pace-dus1.onrender.com/). The public deployment
uses Render and Supabase, with the age and parent-consent flow enabled.

- **Backend:** Python 3.11+, FastAPI, SQLite locally or PostgreSQL when deployed
- **Durable deployment storage:** PostgreSQL (including Supabase) through `PACE_DATABASE_URL`.
  Local development still uses SQLite when that variable is unset.
- **Frontend:** plain HTML/CSS/JavaScript (ES modules, no build step)
- **AI:** Claude via the official `anthropic` SDK. It writes coach messages and suggests
  fields for Google Tasks imports. The planner and mode engine (plain Python rules) decide
  the schedule and when to push or rest. The coach refreshes when the upcoming 48-hour
  schedule changes; ordinary page reloads reuse the current message.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # then put your key in .env (optional)
uvicorn backend.main:app --reload
```

Open http://localhost:8000. Without an API key the coach uses its built-in fallback messages,
so everything still works.

## Desktop app (Windows)

Pace can run as its own app window instead of a browser tab:

```powershell
powershell -ExecutionPolicy Bypass -File create-shortcut.ps1
```

This puts a **Pace** shortcut (with the Pace icon) on your Desktop. Double-clicking it runs
`launch_pace.py`, which starts Pace's server in the background, opens Pace in an Edge (or
Chrome) app window with no tabs or address bar, and stops the server when you close the
window. The window has its own profile, so sign in once inside it. Logs:
`%LOCALAPPDATA%\Pace\launcher.log`.

## Deploy your own copy (Supabase + Render)

Render's free web service discards local SQLite files on restarts and idle spin-down. The
included `render.yaml` requires a PostgreSQL connection before it will start, so a
deployed Pace instance cannot silently lose account plans.

1. Create a Supabase project. In its dashboard, click **Connect → Session pooler** and copy
   the PostgreSQL connection string. Replace `[YOUR-PASSWORD]` locally; never put this URL in
   frontend code, Git, or a chat message. Pace forces encrypted PostgreSQL connections and
   creates its tables in a private `pace` schema outside Supabase's default public Data API.
2. In Render's **Environment** settings, set `PACE_DATABASE_URL` to that complete connection
   string and set `PACE_CONTACT_EMAIL` to the public address for privacy and support requests.
   `render.yaml` requires both settings before launch and pins only the shared demo's clock.
3. Deploy, then open the site and confirm a test plan remains after a service restart.

To move an existing local plan into a **new, empty** Supabase project, put the URL in your
local `.env`, run `python -m backend.migrate_to_postgres pace.db`, then remove the URL from
local `.env` if you want local development to keep using SQLite. The migration refuses to
merge into a project that already contains Pace data. Back up `pace.db` before migrating.

Supabase Free projects can pause after inactivity and do not include automatic daily backups.
No automated off-site export is configured. A paused project may require a dashboard resume
before Pace can serve plans.

On a phone, open the deployed site and use **Add to Home Screen**. Pace installs with its own
icon and opens full screen.

## Demo data

```powershell
$env:PACE_DEMO_NOW="2026-10-19T15:30:00"; python -m backend.seed_demo
$env:PACE_DEMO_NOW="2026-10-19T15:30:00"; uvicorn backend.main:app
```

Then open http://localhost:8000/?as=demo. `PACE_DEMO_NOW` pins only the demo plan's clock to
Monday afternoon, so every take looks the same; everyone else's plan keeps the real date.
(`PACE_NOW` pins the clock for every plan, which the tests use.) Use **Leave the demo** at the top
of the screen to get back to your own plan.

Demo script (re-run the seed to reset between takes):

1. **Something came up** → "The rest of today" → Thursday night turns red; History essay and
   Math test study are flagged ("Consider asking your teacher for an extension").
2. **Week** → **Rebalance my week** → every night is green again.
3. **Decide** → Extra shift, Wednesday 3:15 PM to 9:30 PM → before/after shows what it would
   cost → "Not this time". Nothing is saved.
4. **Check-in** (link at the bottom of Today): 6 hr 30 min of sleep, energy 2, stress 4 →
   Recovery mode, and the coach switches to a rest-first message.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest backend/tests
```

117 tests cover the planner (cutoffs, overlaps, caps, overflow, rebalance, school-day
deadlines), the mode engine, learning estimates, the safety filter, and the API routes
(decision never saves, red button + undo, coach limits), legal pages, and database adapter.

## How it works

- **Planner** (`backend/planner.py`): a pure function. Bedtime = next morning's wake time minus
  the sleep goal; no study in the 30 minutes before bed or the 30 minutes after a shift.
  Tasks are placed earliest-deadline-first in 45-minute chunks under a daily cap. Work that
  doesn't fit is reported as at-risk and shown as lost sleep on the night before it's due.
- **Rebalance**: raises the daily caps by 50% for the rest of the week. It never touches sleep.
- **Decision helper**: runs the planner with and without the hypothetical shift and compares.
- **Decide coach chat**: compares two options using the latest broad sleep and energy bands. If a
  shift was previewed, it also uses the measured sleep and homework effect. Chat text stays out of
  the database; crisis language opens the fixed resource page before any AI request.
- **Learning estimates**: a weighted average of actual ÷ guessed time per subject (recent tasks
  count more, single ratios clamped to 0.25–8). This is statistics on your own data, not a
  trained model. Nothing changes until you tap "Use that".
- **Modes**: Safety → Recovery → Push → Steady, checked in that order from check-ins, sleep
  debt and red-button use. The AI never decides the mode.
- **Safety**: a keyword filter on task titles, decision text and every AI reply. A match shows
  a fixed 988 screen and never reaches the AI. Keyword lists miss things and sometimes
  over-trigger; a false alarm only shows a supportive screen.

## Choices that differ from the spec

- School-day mornings before school are treated as busy (getting ready); the spec's free-slot
  rule would have scheduled 15-minute study blocks at 6:45 AM.
- A `safety_flags` table stores the 24-hour safety marker (the spec had nowhere to keep it).
- Rebalance stays on for the rest of the week (`settings.relaxed_until`) so it survives a
  reload; "Back to normal limits" turns it off.
- The demo's extra shift is on Wednesday, because Thursday already has a regular shift.
- No 24-hour time anywhere a person reads it. Time inputs are hour / minute / AM-PM pickers
  instead of the browser's time input, which shows 24-hour time on some devices.

## Accounts and privacy

The public Privacy Policy and Terms of Service are served at `/privacy-policy` and `/terms`.
`PACE_CONTACT_EMAIL` is the monitored public contact for privacy, parent, and deletion requests.
Operators of their own deployment should review the policy text against their provider settings.

### Under-13 parent email flow

On Render, the age screen runs before any plan API call. A child enters only a parent or guardian
email address. Pace sends a direct notice with a consent link; after a day, the child checks
Pace again to send a separate confirmation email. The plan stays locked until the parent
completes both steps. Google sign-in, Google
imports, and AI are unavailable for under-13 plans; they use local planning messages. Unapproved
contact addresses expire after seven days and are removed during the next age-screen check.

The Render blueprint generates `PACE_AGE_GATE_SECRET` automatically and uses Render's HTTPS
site URL for parent email links. Brevo email credentials, `PACE_BREVO_API_KEY` and
`PACE_BREVO_SENDER` (a verified sender address), must be set in Render's Environment settings.
Render Free blocks SMTP ports, so Pace sends via Brevo's HTTPS API. A Brevo
account and verified sender are required; the app will not start in public mode without them.
Do not put its API key in Git or chat. For a new deployment, test delivery and both email links
before inviting under-13 users. Parents can request review, revocation, or deletion using the public contact email.
Have the notice and provider arrangements reviewed for COPPA before inviting under-13 users.

Accounts are optional. Without one, the browser keeps a random ID and sends it as `X-User-Id`.
With one (a username and password, no email), the server sets an HttpOnly, Secure, SameSite
session cookie so the same plan works on a phone and a laptop. Existing browser tokens are
exchanged once and removed from localStorage.

- Passwords are hashed with scrypt and a per-user salt. The 1,000 most common passwords are
  rejected. Only a SHA-256 of each session token is stored. Sessions last 90 days. Five wrong
  passwords lock that username for 15 minutes. Settings can revoke sessions on all devices.
- Auth and Something came up requests have per-IP limits in shared database counters; production
  keys the IP from Render's trusted `CF-Connecting-IP` header. Unsafe cookie-authenticated
  requests must have a same-origin `Origin` header.
- Requirements have pinned versions, and Render runs `pip-audit` before deploying. Uvicorn
  access logs are disabled so URLs and query strings are not copied into application logs.
- Once an ID belongs to an account, the bare `X-User-Id` header stops working for it, so knowing
  someone's ID isn't enough to read their plan.
- There's no email, so there's no password reset. The sign-up form says so.
- For older users, only a nickname and an optional username are stored, never a real name, email
  or school. The AI never sees either. For under-13 users, Pace also keeps a parent's consent
  email. Settings → "Delete my data" removes every row, including the account or consent record.

### Turning on "Continue with Google"

Google sign-in is enabled on the [public site](https://pace-dus1.onrender.com/) for the Google
accounts listed as test users in the Pace OAuth app. The app remains in Testing for the pilot.
To enable Google sign-in on your own deployment, add a Google Client ID:

1. Go to console.cloud.google.com, create a project (e.g. "Pace").
2. **APIs & Services → OAuth consent screen**: choose **External**, fill in the app name and
   your email, and add your testers' Google accounts under **Test users** (fine for a pilot).
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**, type **Web
   application**. Under **Authorized JavaScript origins** add `http://localhost:8000`,
   `http://localhost`, and your Render URL (e.g. `https://pace-xxxx.onrender.com`).
4. Copy the Client ID into `.env` as `GOOGLE_CLIENT_ID=...` (and into Render's Environment tab).
   Restart the server.

Pace checks each Google sign-in with Google's `tokeninfo` endpoint, then keeps only Google's
account number (`sub`). The email and name in the token are thrown away. A new Google sign-in
claims the plan already in that browser; signing in on another device brings the same plan back.

### Google Calendar import

Settings → **Google Calendar** → **Import from Google Calendar** reads the next 2 weeks of your
primary calendar (read-only) and adds the events as busy time Pace plans around. Imported events
show as "Busy" unless you tick **Keep event names**. All-day events, events marked free and
events you declined are skipped. Importing again replaces the earlier import; **Remove imported
events** takes them all out. The token is revoked right after reading.

It needs the **Google Calendar API** enabled in the same Google Cloud project as the Client ID,
and the `.../auth/calendar.events.readonly` scope on the consent screen (Data Access).

### Google Tasks import

Settings → **Google Tasks** → **Choose Google Tasks** reads unfinished items from the user's
Google Task lists. If the student chooses **with AI suggestions**, task titles and list names
go to Claude for suggested subject, assignment type, and time estimate; **without AI** uses
local rules instead. If the AI key is unavailable, local rules also provide suggestions.
The student selects items and reviews every field before copying them into Pace. Google Tasks
supplies a scheduled date but no actual
due time; Pace never assumes that date is a deadline without showing it for review. Reimporting
skips items already copied, preserving edits and logged work in Pace. This is a one-time,
read-only copy, not a live sync. The browser revokes the Google token after reading; the server
never receives it.

Enable the **Google Tasks API** in the same Google Cloud project and add
`https://www.googleapis.com/auth/tasks.readonly` to the OAuth consent screen's Data Access
scopes. Google Calendar import needs its separate scope and API as described above.

## First-time setup

New users get a six-step walkthrough: nickname, school, sleep (with a live "in bed by" preview),
weekly shifts and activities, study limits, and an optional account. People who already have
an account can sign in from the welcome screen.
