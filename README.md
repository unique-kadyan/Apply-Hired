# JobBot — AI-Powered Job Application Platform

> **Automate your job search. Track every application. Never miss an interview.**

JobBot is a full-stack AI job application platform that searches 13+ job boards simultaneously, scores every listing against your resume, generates personalised cover letters, and automatically tracks your application pipeline — from discovery through offer.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Job Board Coverage](#job-board-coverage)
- [How It Works](#how-it-works)

---

## Features

### Job Discovery

- **13+ board search** — Searches RemoteOK, Remotive, Arbeitnow, WeWorkRemotely, Jobicy, FindWork, Adzuna, TheMuse, HackerNews Hiring, JSearch, Dice, SerpAPI Google Jobs, and CareerJet in parallel
- **Smart location filtering** — ISO 3166-1 country resolution via `pycountry`; correctly handles remote/worldwide vs country-specific roles
- **Salary filtering** — Multi-currency support with automatic USD conversion; filters by minimum salary threshold
- **Freshness filter** — Automatically excludes listings older than 4 months

### AI-Powered Matching

- **Local keyword scoring** — Instant match score based on skills, title relevance, and seniority level
- **AI scoring** — Optional deep evaluation via OpenAI / Groq / Cerebras with reasons, missing skills, and recommendation label
- **Seniority check** — Filters out roles below or above your experience level (Junior / Mid / Senior / Lead / Staff / Principal)
- **Required experience extraction** — Highlights minimum years required directly in the job card

### Cover Letters

- **AI-generated** — Personalised cover letter for each role using your full profile
- **One-click PDF export** — Downloads as `cover_letter_company_job_title.pdf` (no print dialog)
- **Auto-saved** — Stored per job; regenerate at any time

### Application Tracking

- **Pipeline statuses** — `New → Saved → Applied → Interview → Offer → Not Interested`
- **Interview details** — Round, date, time, timezone, platform, meeting link, interviewer name
- **Offer details** — Salary/CTC, currency, joining date, acceptance deadline, benefits, work location
- **Notes & reasons** — Per-job notes and structured not-interested reasons

### Gmail Auto-Detection _(New)_

- **Read-only OAuth** — Connects to Gmail with `gmail.readonly` scope only
- **Interview detection** — Scans for invitation keywords; extracts date, time, platform, meeting link, round, interviewer
- **Offer detection** — Extracts CTC/salary, currency, joining date, acceptance deadline, location, benefits
- **Smart merge** — Never overwrites manually entered data; enriches with parsed email content
- **Status auto-upgrade** — Updates job status Applied → Interview → Offer automatically; never downgrades

### Smart Filtering

- **Skip topics (display only)** — Track custom reasons for "not interested" jobs; no longer filter searches
- **Tab counts** — Live counts for Not Applied / Applied / Not Interested tabs
- **Full-text search** — Search by title, company, location, or skill tag

### Profile & Integrations

- **Resume parsing** — Upload PDF/DOCX; AI extracts skills, experience, education, summary
- **GitHub import** — Connects via GitHub API; imports repos, languages, contribution stats
- **LinkedIn, Portfolio** — URL scraping for additional profile context
- **Experience timeline** — Visual horizontal timeline with proportional date bars

### Dashboard & Analytics

- **7 stat cards** — Total, New, Applied, Interviews, Offers, Skipped, Avg Match
- **Donut chart** — Status distribution
- **Bar chart** — Top companies by application count
- **Funnel chart** — Discovery → Applied → Interview → Offer conversion
- **Activity chart** — 14-day application activity line chart
- **Recent panels** — Grouped by New / Applied / Interview with inline job cards

### Authentication

- **Email / Password** — Secure bcrypt hashing
- **Google OAuth** — One-click sign-in
- **OTP password reset** — Email-based reset flow
- **Session management** — Persistent sessions (configurable lifetime)

### Payments

- **Razorpay integration** — Subscription / one-time payment support

---

## Tech Stack

| Layer            | Technology                                                        |
| ---------------- | ----------------------------------------------------------------- |
| **Backend**      | Python 3.11+, Flask                                               |
| **Database**     | MongoDB Atlas (pymongo)                                           |
| **Frontend**     | React 18 (CDN, single HTML file), Chart.js 4.4, jsPDF 2.5         |
| **AI / Scoring** | OpenAI GPT-4o-mini, Groq, Cerebras (with failover)                |
| **Job APIs**     | JSearch (RapidAPI), SerpAPI, CareerJet, Adzuna, FindWork, TheMuse |
| **Auth**         | Google OAuth 2.0, bcrypt, Flask sessions                          |
| **Location**     | pycountry (ISO 3166-1)                                            |
| **Email**        | Gmail API (OAuth 2.0, read-only), SMTP (password reset)           |
| **Payments**     | Razorpay                                                          |
| **PDF**          | jsPDF (client-side, direct download)                              |

---

## Quick Start

### Prerequisites

- Python 3.11+
- MongoDB Atlas account (free tier works)
- Node.js not required — frontend is a single HTML file

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/unique-kadyan/Apply-Hired.git
cd Apply-Hired

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum set MONGO_URI and SECRET_KEY

# 5. Start the server
python app.py

# 6. Open in browser
open http://localhost:5000
```

---

## Environment Variables

Create a `.env` file in the project root. Required variables are marked \*.

```env
# ── Database ──────────────────────────────────────────────────────────────────
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/jobbot   # *

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY=your-random-secret-key-here                         # *

# ── Google OAuth (login + Gmail integration) ──────────────────────────────────
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
BASE_URL=http://localhost:5000      # set to your production URL when deployed

# ── AI Scoring (at least one recommended) ─────────────────────────────────────
OPENAI_API_KEY=                     # GPT-4o-mini scoring + cover letters
GROQ_API_KEY=                       # Groq failover
CEREBRAS_API_KEY=                   # Cerebras failover

# ── Job Board APIs ────────────────────────────────────────────────────────────
JSEARCH_API_KEY=                    # RapidAPI — aggregates LinkedIn/Indeed/Glassdoor
SERPAPI_KEY=                        # Google Jobs via SerpAPI
CAREERJET_AFFID=                    # CareerJet affiliate ID (free)
ADZUNA_APP_ID=                      # Adzuna app ID
ADZUNA_APP_KEY=                     # Adzuna app key
FINDWORK_API_KEY=                   # FindWork.dev
THEMUSE_API_KEY=                    # The Muse (optional — works without key)

# ── GitHub Integration ────────────────────────────────────────────────────────
GITHUB_TOKEN=                       # Personal access token (optional, avoids rate limits)

# ── Email / SMTP (password reset) ─────────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=
SMTP_PASSWORD=

# ── Payments ──────────────────────────────────────────────────────────────────
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
```

---

## Project Structure

```
job_apply/
├── app.py                      # Flask app factory — blueprint registration, SPA serving
├── config.py                   # Location preferences, API key defaults
├── tracker.py                  # MongoDB CRUD — jobs, users, stats, skip filters
├── scrapers.py                 # 13 job board scrapers + location/salary filters
├── matcher.py                  # Job scoring engine (local keyword + AI)
├── cover_letter.py             # AI cover letter generator
├── resume_parser.py            # PDF/DOCX resume parser with AI extraction
│
├── routes/
│   ├── auth.py                 # Email/password auth, Google OAuth, OTP reset
│   ├── jobs.py                 # Job CRUD, status, cover letter, interview, offer
│   ├── profile.py              # Profile, resume upload, GitHub/LinkedIn/Portfolio
│   ├── search.py               # Background search orchestration, stats
│   ├── gmail.py                # Gmail OAuth, sync, interview/offer auto-detection
│   └── payment.py              # Razorpay payment routes
│
├── services/
│   ├── search_service.py       # Background search thread, salary/date filtering
│   ├── profile_import.py       # GitHub API import, LinkedIn/portfolio scraping
│   └── currency.py             # Multi-currency detection and USD conversion
│
├── middleware.py               # login_required decorator, session user helpers
│
├── frontend/
│   └── build/
│       └── index.html          # React 18 SPA — all pages in one file
│
├── uploads/                    # Uploaded resumes (gitignored)
├── requirements.txt
├── .env.example
└── README.md
```

---

## API Reference

### Authentication

| Method | Endpoint                    | Description                    |
| ------ | --------------------------- | ------------------------------ |
| `POST` | `/api/auth/register`        | Register with email + password |
| `POST` | `/api/auth/login`           | Login with email + password    |
| `POST` | `/api/auth/logout`          | Logout                         |
| `GET`  | `/api/auth/google`          | Start Google OAuth flow        |
| `GET`  | `/api/auth/google/callback` | Google OAuth callback          |
| `POST` | `/api/auth/forgot-password` | Send OTP reset email           |
| `POST` | `/api/auth/reset-password`  | Reset password with OTP        |

### Profile

| Method | Endpoint                         | Description                  |
| ------ | -------------------------------- | ---------------------------- |
| `GET`  | `/api/profile`                   | Get current user profile     |
| `PUT`  | `/api/profile`                   | Update profile fields        |
| `POST` | `/api/profile/upload-resume`     | Upload PDF/DOCX and parse    |
| `POST` | `/api/profile/connect/github`    | Import GitHub repos + skills |
| `POST` | `/api/profile/connect/linkedin`  | Scrape LinkedIn profile      |
| `POST` | `/api/profile/connect/portfolio` | Scrape portfolio site        |

### Jobs

| Method | Endpoint                                  | Description                                            |
| ------ | ----------------------------------------- | ------------------------------------------------------ |
| `GET`  | `/api/jobs`                               | List jobs (paginated, filtered, sorted)                |
| `GET`  | `/api/jobs/tab-counts`                    | Count per tab (not_applied / applied / not_interested) |
| `GET`  | `/api/jobs/<id>`                          | Get single job detail                                  |
| `PUT`  | `/api/jobs/<id>/status`                   | Update job status + notes                              |
| `POST` | `/api/jobs/<id>/cover-letter`             | Generate / regenerate cover letter                     |
| `GET`  | `/api/jobs/<id>/cover-letter`             | Fetch stored cover letter                              |
| `PUT`  | `/api/jobs/<id>/interview`                | Save interview scheduling details                      |
| `PUT`  | `/api/jobs/<id>/offer`                    | Save offer letter details                              |
| `GET`  | `/api/jobs/skip-keywords`                 | Get active skip filter keywords (display only)         |
| `POST` | `/api/jobs/not-interested-reasons`        | Add custom skip reason                                 |
| `POST` | `/api/jobs/not-interested-reasons/delete` | Remove skip reason                                     |
| `POST` | `/api/jobs/clear`                         | Delete non-applied jobs                                |
| `POST` | `/api/mark-applied-by-url`                | Mark applied by URL (Chrome Extension)                 |

### Search

| Method | Endpoint             | Description                        |
| ------ | -------------------- | ---------------------------------- |
| `POST` | `/api/search`        | Start background job search        |
| `GET`  | `/api/search/status` | Poll search progress               |
| `GET`  | `/api/stats`         | Dashboard statistics + charts data |

### Gmail

| Method | Endpoint                | Description                                      |
| ------ | ----------------------- | ------------------------------------------------ |
| `GET`  | `/api/gmail/auth`       | Start Gmail OAuth (read-only scope)              |
| `GET`  | `/api/gmail/callback`   | Gmail OAuth callback                             |
| `GET`  | `/api/gmail/status`     | Check connection status + last sync              |
| `POST` | `/api/gmail/sync`       | Scan Gmail; auto-update interview/offer statuses |
| `POST` | `/api/gmail/disconnect` | Remove Gmail tokens                              |

### Auto-Apply

| Method | Endpoint          | Description                             |
| ------ | ----------------- | --------------------------------------- |
| `POST` | `/api/apply`      | Mark jobs as applied                    |
| `POST` | `/api/auto-apply` | Generate cover letters + open job pages |

---

## Job Board Coverage

| Source                   | Type                                                                | Auth Required     |
| ------------------------ | ------------------------------------------------------------------- | ----------------- |
| RemoteOK                 | Remote-first                                                        | Free              |
| Remotive                 | Remote-first                                                        | Free              |
| Arbeitnow                | EU + Global remote                                                  | Free              |
| WeWorkRemotely           | Remote-first                                                        | Free              |
| Jobicy                   | Remote-first                                                        | Free              |
| FindWork                 | Tech-focused                                                        | API key (free)    |
| Adzuna                   | 12+ countries                                                       | API key (free)    |
| TheMuse                  | Company culture-focused                                             | Optional          |
| HackerNews Hiring        | Tech/startup                                                        | Free              |
| JSearch (RapidAPI)       | LinkedIn + Indeed + Glassdoor aggregator                            | RapidAPI key      |
| Dice                     | Tech-specific (US)                                                  | Free              |
| **GoogleJobs (SerpAPI)** | Google Jobs index — covers Indeed, Naukri, ZipRecruiter + 20 boards | SerpAPI key       |
| **CareerJet**            | 2,500+ boards — strong India/APAC coverage                          | Free affiliate ID |

---

## How It Works

### Job Search Pipeline

```
User triggers search
        │
        ▼
Build search queries from title + skills + location
        │
        ▼
Parallel scrape across 13 job boards
        │
        ▼
Filter: date (< 4 months) + salary threshold + location preference
        │
        ▼
Score each job: local keyword match + optional AI evaluation
        │
        ▼
Save new jobs to MongoDB (deduplicated by user + URL)
        │
        ▼
Notify frontend via polling
```

### Gmail Auto-Detection Pipeline

```
User connects Gmail (read-only OAuth)
        │
        ▼
Sync triggered → search last 90 days for interview/offer keywords
        │
        ▼
Classify each email: strong phrase match → weak signal scoring
        │
        ▼
Extract company from sender domain → match to applied job in DB
        │
        ▼
Parse details from email body:
  Interview → date, time, timezone, round, platform, meeting link, interviewer
  Offer     → CTC/salary, currency, joining date, deadline, location, benefits
        │
        ▼
Merge extracted details into job record (never overwrites manual data)
Status upgraded: Applied → Interview or Offer (never downgraded)
```

---

## License

Private — all rights reserved. © 2026 Rajesh Singh Kadyan
