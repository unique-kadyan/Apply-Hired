# Apply-Hired (JobBot)

Full-stack job search automation platform. Searches 13+ job boards in parallel, scores every listing against your profile, generates AI cover letters, and tracks your application pipeline from discovery through offer.

---

## Stack

- Backend: Python Flask, MongoDB (pymongo), APScheduler
- Frontend: Next.js 14 (App Router, static export), React 18, Chart.js, jsPDF
- Deployment: Render.com (free tier, kept alive via GitHub Actions)
- Auth: Session-based (Flask sessions), Google OAuth

---

## Architecture

```
job_apply/
├── app.py                      Flask app factory, registers blueprints, serves Next.js static build from frontend/build/
├── setup.py                    Triggers npm build automatically during pip install
├── routes/
│   ├── auth.py                 Email/password auth, Google OAuth, OTP reset
│   ├── jobs.py                 Job CRUD, status, cover letter, interview, offer
│   ├── search.py               Background search orchestration + schedule
│   ├── profile.py              Profile, resume upload, GitHub/LinkedIn/portfolio
│   ├── gmail.py                Gmail OAuth, sync, interview/offer auto-detection
│   └── payment.py              Razorpay payment routes
├── scrapers.py                 Multi-board job scrapers (LinkedIn, Indeed, HackerNews, Glassdoor, etc.)
├── matcher.py                  Job scoring/ranking against user profile
├── tracker.py                  MongoDB operations for jobs, users, profiles
├── cover_letter.py             Claude AI cover letter generation
├── services/
│   ├── scheduler.py            Auto-search + stale job pruner
│   ├── search_service.py       Background search thread, salary/date filtering
│   ├── profile_import.py       GitHub API import (parallel language fetching)
│   └── currency.py             Multi-currency detection and USD conversion
├── frontend/
│   ├── src/app/                App Router entry (layout.jsx, page.jsx, globals.css)
│   ├── src/components/         Feature components (Auth, Dashboard, Jobs, Profile, Search, WelcomeOverlay, shared)
│   └── src/lib/                api.js (fetch wrapper), styles.js (shared style objects)
├── requirements.txt
└── .env.example
```

---

## Development Setup

```bash
# Backend
python -m venv venv && source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # fill in MONGO_URI, SECRET_KEY, ANTHROPIC_API_KEY
python app.py   # Flask on :5000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev     # Next.js on :3000 — proxies API calls to Flask on :5000
```

---

## Production Build (Render)

`pip install -r requirements.txt` builds everything — Python dependencies and the Next.js frontend — via the `setup.py` post-install hook. No separate build script needed.

**Render settings:**

| Setting | Value |
| --- | --- |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT --timeout 120` |

**Environment variables required:**

| Variable | Description |
| --- | --- |
| `MONGO_URI` | MongoDB Atlas connection string |
| `SECRET_KEY` | Flask session secret |
| `ANTHROPIC_API_KEY` | Claude AI for cover letters |
| `RENDER_EXTERNAL_URL` | Set by Render automatically |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `SESSION_LIFETIME_HOURS` | Session duration (default 720 hrs) |
| `RAZORPAY_KEY_ID` | Razorpay key for resume optimizer |
| `RAZORPAY_KEY_SECRET` | Razorpay secret |
| `SMTP_HOST` / `SMTP_EMAIL` / `SMTP_PASSWORD` | SMTP for password reset emails |
| `JSEARCH_API_KEY` | RapidAPI key (aggregates LinkedIn/Indeed/Glassdoor) |
| `SERPAPI_KEY` | Google Jobs via SerpAPI |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna job board |

---

## Key Features

- Multi-board job search: LinkedIn, Indeed, HackerNews Hiring, Glassdoor, Wellfound, RemoteOK, Remotive, Arbeitnow, WeWorkRemotely, Jobicy, FindWork, Adzuna, TheMuse, JSearch, SerpAPI Google Jobs, CareerJet, Dice
- AI-powered job scoring and match analysis (local keyword + optional AI deep-score)
- Cover letter generation (Claude AI) with A/B tone tracking (formal vs casual)
- Saved jobs, applied tracking, interview/offer pipeline with detailed fields
- Auto-search scheduler (configurable interval, stored per user)
- GitHub profile import with parallel language fetching across all repos
- Gmail OAuth for automatic interview and offer email parsing
- Resume upload + AI parsing + ATS optimizer (Razorpay payment gate)
- Remote job country filtering using ISO code matching via pycountry
- Dashboard with charts: status breakdown (donut), activity line (14 days), score distribution (bar), application funnel, top companies, source conversion rate, cover letter A/B rate
- GitHub Actions keep-alive pings to prevent Render free-tier suspension

---

## Frontend Architecture

- SPA with client-side routing using a `visited` map and CSS `display:none` keep-alive (avoids re-mounting components on tab switch)
- Dashboard data pre-fetched at App level and cached in `sessionStorage`; silent background refresh on every visit
- Search progress uses 2-second polling with immediate optimistic UI feedback
- Jobs component lazy-loads only when first visited (`isVisible` prop gates the initial API call)
- `api.js` wraps `fetch` with a configurable `NEXT_PUBLIC_API_BASE` prefix for dev/prod parity
- All shared inline styles live in `styles.js` as plain objects; no CSS-in-JS runtime overhead
