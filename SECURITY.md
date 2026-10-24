# Pace security notes (Take9 pledge)

As a Congressional App Challenge participant I took the Take9 pledge (https://pausetake9.org/):
to consider the cybersecurity of my app and its users, including what data the app collects,
how that data is protected, and how the app can be designed to reduce security risks.

## What Pace collects

| Data | Why | Notes |
| --- | --- | --- |
| Nickname (optional) | Say hi | Never sent to the AI |
| Username + password hash (optional) | Sign in on other devices | No email, no real name |
| Google account number (`sub`, optional) | Sign in with Google | Email and name from Google are thrown away |
| Parent email (under-13 only) | Send consent notices and handle parent rights | Collected before a child plan; unapproved requests expire after seven days |
| School hours, wake times, shifts, tasks | Build the plan | |
| Check-ins (sleep, energy, stress 1–5) | Pick the coach mode | AI sees the resulting mode, not individual answers |
| Google Calendar event times (optional) | Plan around existing commitments | Shown as "Busy" unless titles are opted in |
| Selected Google Tasks (optional) | Turn to-do items into assignments | Titles and list names go to Claude only if the user chooses AI suggestions; the Google token is not sent to Pace |

Not collected: students' real names or email addresses, school names, location, contacts.

## Already in place

- [x] Passwords hashed with scrypt + per-user salt; never stored or logged in plain text.
- [x] Session tokens are random; only their SHA-256 is stored. Sessions expire after 90 days.
- [x] 5 wrong passwords lock that username for 15 minutes.
- [x] An account's plan can't be read with just its ID; it needs a real sign-in.
- [x] Google sign-in is verified with Google before it's trusted; only the account number is kept.
- [x] API keys live in `.env` / Render's environment, never in the repo (`.gitignore`).
- [x] The AI only receives plan facts and the resulting mode (task names, times). No nickname, no individual check-in answers, nothing the
      safety filter flagged. AI replies are safety-checked before they're shown.
- [x] Decide coach chat checks messages before AI, sends only broad sleep and energy bands from
      check-ins, checks replies, and stores only a daily request count (not chat text).
- [x] All user text is shown with `textContent`, not HTML, so typed text can't run as code.
- [x] Every input has a length limit; times and dates are validated on the server.
- [x] "Delete my data" removes every row for the user, including the account.
- [x] Same-origin app: no CORS opened to other sites.
- [x] **Security headers** on every response: Content-Security-Policy (only Pace's own files,
      Google Fonts and Google's sign-in), `frame-ancestors 'none'` + `X-Frame-Options: DENY`,
      `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy` (no camera,
      mic, location), `Cross-Origin-Opener-Policy`. Tested in `test_security.py`.
- [x] `Strict-Transport-Security` (HTTPS from then on) whenever the site is reached over HTTPS.
- [x] API responses are `Cache-Control: no-store`, so personal plans never sit in a cache.
- [x] The shared demo plan (`?as=demo`) can never be turned into an account.
- [x] `?as=` accepts only the shared demo; it cannot switch a browser to another user's plan ID.
- [x] Anonymous plan IDs come from the browser's cryptographic random source, including the
      fallback when `crypto.randomUUID` is unavailable.
- [x] Render deployment refuses to start without a durable PostgreSQL connection; Supabase
      tables are in a private `pace` schema and connections require TLS.
- [x] **"What Pace stores" page** (`#/privacy`), linked from welcome, setup, Settings and sign-in.
- [x] **Google profile photo stays in the browser**: read from the sign-in token on the device,
      kept in localStorage, loaded with `referrerpolicy="no-referrer"`, cleared on sign-out. Only
      `https://*.googleusercontent.com` links are accepted. The server never receives it.
- [x] **Google Calendar import is read-only and one-shot**: the browser gets a short-lived
      `calendar.events.readonly` token, reads 2 weeks of events, sends Pace only times (titles
      only if the person opts in), then revokes the token. The server never sees or stores it.
- [x] **Take9 tip** on every password form: "Pause before you share. Only type your Pace
      password on this page."

## Public deployment

- Render redirects HTTP to HTTPS, and Pace sends HSTS on HTTPS responses.
- Sign-up, sign-in, Google sign-in, and Something came up have shared per-IP rate limits.
- Account sessions use HttpOnly, Secure, SameSite cookies. Settings offers **Sign out of all devices**.
- New passwords are checked against a 1,000-entry common-password list.
- Dependencies are pinned, and Render runs `pip-audit` during each build. Uvicorn access logs
  are disabled so request URLs and query strings do not enter application logs. Application
  code does not log passwords, session tokens, or Google credentials.
- The public service uses Supabase PostgreSQL for durable plan storage. Automated off-site
  backups are not configured on the Free database plan.
- Google sign-in is enabled on the public site for listed test users. The OAuth app remains in
  Testing until Google's verification is complete.
