"""Job scrapers for multiple free job boards and APIs."""

import os
import re
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
from functools import lru_cache

import pycountry
import requests
from bs4 import BeautifulSoup

from config import (
    SEARCH_PREFERENCES,
    JSEARCH_API_KEY,
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    LOCATION_PREFERENCES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    description: str = ""
    salary: str = ""
    tags: list[str] = field(default_factory=list)
    date_posted: str = ""
    job_type: str = "remote"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Base scraper
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


class BaseScraper:
    name: str = "base"
    base_url: str = ""

    def fetch_jobs(self, query: str) -> list[Job]:
        raise NotImplementedError

    def _safe_get(
        self, url: str, params: dict = None, headers: dict = None, timeout: int = 15
    ) -> Optional[requests.Response]:
        merged_headers = dict(_DEFAULT_HEADERS)
        if headers:
            merged_headers.update(headers)
        for attempt in range(2):
            try:
                resp = requests.get(
                    url, params=params, headers=merged_headers, timeout=timeout
                )
                if resp.status_code == 429:
                    time.sleep(2)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                logger.warning(f"[{self.name}] Request failed for url: {url}: {e}")
                return None
        return None

    def _safe_json(self, resp) -> Optional[dict]:
        """Safely parse JSON from a response. Returns None if not JSON."""
        if not resp:
            return None
        content_type = resp.headers.get("content-type", "")
        if "json" not in content_type and "javascript" not in content_type:
            # Check if body looks like JSON anyway
            text = resp.text.strip()
            if not text or (not text.startswith("{") and not text.startswith("[")):
                return None
        try:
            return resp.json()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# RemoteOK — free JSON API
# ---------------------------------------------------------------------------


class RemoteOKScraper(BaseScraper):
    name = "RemoteOK"
    base_url = "https://remoteok.com/api"

    def fetch_jobs(self, query: str) -> list[Job]:
        resp = self._safe_get(
            self.base_url,
            headers={"User-Agent": "JobBot/1.0 (rajeshsinghkadyan@gmail.com)"},
        )
        if not resp:
            return []

        data = resp.json()
        # First item is metadata, skip it
        if isinstance(data, list) and len(data) > 1:
            data = data[1:]

        jobs = []
        query_lower = query.lower()
        keywords = query_lower.split()

        for item in data:
            title = item.get("position", "")
            company = item.get("company", "")
            description = item.get("description", "")
            tags = item.get("tags", [])

            # Filter by query keywords
            searchable = f"{title} {company} {description} {' '.join(tags)}".lower()
            if not any(kw in searchable for kw in keywords):
                continue

            # Skip excluded keywords
            if any(ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=item.get("location", "Remote"),
                    url=item.get(
                        "url", f"https://remoteok.com/remote-jobs/{item.get('id', '')}"
                    ),
                    source=self.name,
                    description=_clean_html(description),
                    salary=item.get("salary", ""),
                    tags=tags if isinstance(tags, list) else [],
                    date_posted=item.get("date", ""),
                    job_type="remote",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# Remotive — free JSON API
# ---------------------------------------------------------------------------


class RemotiveScraper(BaseScraper):
    name = "Remotive"
    base_url = "https://remotive.com/api/remote-jobs"

    CATEGORY_MAP = {
        "java": "software-dev",
        "python": "software-dev",
        "spring": "software-dev",
        "backend": "software-dev",
        "frontend": "software-dev",
        "react": "software-dev",
        "devops": "devops-sysadmin",
        "data": "data",
    }

    def fetch_jobs(self, query: str) -> list[Job]:
        category = "software-dev"
        for kw, cat in self.CATEGORY_MAP.items():
            if kw in query.lower():
                category = cat
                break

        resp = self._safe_get(
            self.base_url, params={"category": category, "limit": 100}
        )
        parsed = self._safe_json(resp)
        if not parsed:
            return []

        data = parsed.get("jobs", [])
        jobs = []
        query_lower = query.lower()
        keywords = query_lower.split()

        for item in data:
            title = item.get("title", "")
            company = item.get("company_name", "")
            description = item.get("description", "")
            tags = item.get("tags", [])

            searchable = f"{title} {company} {description} {' '.join(tags)}".lower()
            if not any(kw in searchable for kw in keywords):
                continue

            if any(ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            salary_text = ""
            if item.get("salary"):
                salary_text = item["salary"]

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=item.get("candidate_required_location", "Remote"),
                    url=item.get("url", ""),
                    source=self.name,
                    description=_clean_html(description),
                    salary=salary_text,
                    tags=tags if isinstance(tags, list) else [],
                    date_posted=item.get("publication_date", ""),
                    job_type=item.get("job_type", "remote"),
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# Arbeitnow — free JSON API (remote-friendly European + global jobs)
# ---------------------------------------------------------------------------


class ArbeitnowScraper(BaseScraper):
    name = "Arbeitnow"
    base_url = "https://www.arbeitnow.com/api/job-board-api"

    def fetch_jobs(self, query: str) -> list[Job]:
        jobs = []
        page = 1
        keywords = query.lower().split()

        while page <= 1:  # single page for speed
            resp = self._safe_get(self.base_url, params={"page": page})
            if not resp:
                break

            data = resp.json()
            items = data.get("data", [])
            if not items:
                break

            for item in items:
                if not item.get("remote", False):
                    continue

                title = item.get("title", "")
                company = item.get("company_name", "")
                description = item.get("description", "")
                tags = item.get("tags", [])

                searchable = f"{title} {company} {description} {' '.join(tags)}".lower()
                if not any(kw in searchable for kw in keywords):
                    continue

                if any(
                    ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]
                ):
                    continue

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        location=item.get("location", "Remote"),
                        url=item.get("url", ""),
                        source=self.name,
                        description=_clean_html(description),
                        tags=tags if isinstance(tags, list) else [],
                        date_posted=item.get("created_at", ""),
                        job_type="remote",
                    )
                )

            if not data.get("links", {}).get("next"):
                break
            page += 1
            time.sleep(0.5)

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# JSearch (RapidAPI) — LinkedIn, Indeed, Glassdoor aggregator (needs API key)
# ---------------------------------------------------------------------------


class JSearchScraper(BaseScraper):
    name = "JSearch"
    base_url = "https://jsearch.p.rapidapi.com/search"

    def fetch_jobs(self, query: str) -> list[Job]:
        if not JSEARCH_API_KEY:
            logger.info(f"[{self.name}] Skipped — no JSEARCH_API_KEY set")
            return []

        headers = {
            "X-RapidAPI-Key": JSEARCH_API_KEY,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        # Detect if query already contains location info
        is_remote = "remote" in query.lower()
        params = {
            "query": query if is_remote else f"{query} remote",
            "num_pages": 2,
            "remote_jobs_only": "true" if is_remote else "false",
        }

        resp = self._safe_get(self.base_url, params=params, headers=headers, timeout=30)
        if not resp:
            return []

        data = resp.json().get("data", [])
        jobs = []

        for item in data:
            title = item.get("job_title", "")
            description = item.get("job_description", "")
            searchable = f"{title} {description}".lower()

            if any(ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            # Build salary string from structured fields
            salary_parts = []
            min_sal = item.get("job_min_salary")
            max_sal = item.get("job_max_salary")
            sal_currency = item.get("job_salary_currency") or "USD"
            sal_period = (item.get("job_salary_period") or "").lower()
            sym = {
                "USD": "$",
                "GBP": "£",
                "EUR": "€",
                "INR": "₹",
                "CAD": "C$",
                "AUD": "A$",
            }.get(sal_currency, "$")
            if min_sal is not None and float(min_sal) > 0:
                salary_parts.append(f"{sym}{float(min_sal):,.0f}")
            if max_sal is not None and float(max_sal) > 0 and max_sal != min_sal:
                salary_parts.append(f"{sym}{float(max_sal):,.0f}")
            salary = " – ".join(salary_parts)
            if (
                salary
                and sal_period
                and sal_period not in ("yearly", "annual", "year", "")
            ):
                period_label = {
                    "monthly": "/mo",
                    "monthly ": "/mo",
                    "hourly": "/hr",
                    "weekly": "/wk",
                }.get(sal_period, f"/{sal_period[:2]}")
                salary += period_label

            # Build location from city + state + country
            city = (item.get("job_city") or "").strip()
            state = (item.get("job_state") or "").strip()
            country = (item.get("job_country") or "").strip()
            loc_parts = [p for p in [city, state, country] if p]
            location = ", ".join(loc_parts) if loc_parts else "Remote"

            jobs.append(
                Job(
                    title=title,
                    company=item.get("employer_name", ""),
                    location=location,
                    url=item.get("job_apply_link", ""),
                    source=self.name,
                    description=description[:2000],
                    salary=salary,
                    tags=[],
                    date_posted=item.get("job_posted_at_datetime_utc", ""),
                    job_type="remote",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# We Work Remotely — scrape HTML (no API key needed)
# ---------------------------------------------------------------------------


class WeWorkRemotelyScraper(BaseScraper):
    name = "WeWorkRemotely"
    base_url = "https://weworkremotely.com/remote-jobs/search"

    def fetch_jobs(self, query: str) -> list[Job]:
        resp = self._safe_get(
            self.base_url,
            params={"term": query},
            headers={"User-Agent": "JobBot/1.0"},
        )
        if not resp:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []

        for li in soup.select("li.feature, li:not(.ad)")[:50]:
            link = li.select_one("a")
            if not link or not link.get("href"):
                continue
            href = link["href"]
            if not href.startswith("/remote-jobs/"):
                continue

            title_el = li.select_one(".title")
            company_el = li.select_one(".company")
            region_el = li.select_one(".region")

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            location = region_el.get_text(strip=True) if region_el else "Remote"

            if not title:
                continue

            searchable = f"{title} {company}".lower()
            if any(ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=location,
                    url=f"https://weworkremotely.com{href}",
                    source=self.name,
                    description="",
                    tags=[],
                    job_type="remote",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# Jobicy — free JSON API (remote jobs)
# ---------------------------------------------------------------------------


class JobicyScraper(BaseScraper):
    name = "Jobicy"
    base_url = "https://jobicy.com/api/v2/remote-jobs"

    def fetch_jobs(self, query: str) -> list[Job]:
        params = {"count": 50, "tag": query}
        resp = self._safe_get(self.base_url, params=params)
        if not resp:
            return []

        try:
            data = resp.json().get("jobs", [])
        except Exception:
            return []

        jobs = []
        keywords = query.lower().split()

        for item in data:
            title = item.get("jobTitle", "")
            company = item.get("companyName", "")
            description = item.get("jobDescription", "")
            location = item.get("jobGeo", "Remote")

            searchable = f"{title} {company} {description}".lower()
            if not any(kw in searchable for kw in keywords):
                continue
            if any(ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            salary_text = ""
            if item.get("annualSalaryMin") and item.get("annualSalaryMax"):
                currency = item.get("salaryCurrency", "USD")
                salary_text = f"{currency} {item['annualSalaryMin']:,} – {item['annualSalaryMax']:,}/yr"
            elif item.get("annualSalaryMin"):
                currency = item.get("salaryCurrency", "USD")
                salary_text = f"{currency} {item['annualSalaryMin']:,}+/yr"

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=location,
                    url=item.get("url", ""),
                    source=self.name,
                    description=_clean_html(description),
                    salary=salary_text,
                    tags=(
                        item.get("jobIndustry", [])
                        if isinstance(item.get("jobIndustry"), list)
                        else []
                    ),
                    date_posted=item.get("pubDate", ""),
                    job_type="remote",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# FindWork.dev — free API for developer jobs
# ---------------------------------------------------------------------------


class FindWorkScraper(BaseScraper):
    name = "FindWork"
    base_url = "https://findwork.dev/api/jobs/"

    def fetch_jobs(self, query: str) -> list[Job]:
        resp = self._safe_get(
            self.base_url,
            params={"search": query, "remote": "true", "order_by": "-date_posted"},
            headers={"User-Agent": "JobBot/1.0"},
        )
        if not resp:
            return []

        try:
            data = resp.json().get("results", [])
        except Exception:
            return []

        jobs = []
        for item in data:
            title = item.get("role", "")
            company = item.get("company_name", "")
            description = item.get("text", "")
            keywords_list = item.get("keywords", [])

            searchable = f"{title} {company} {description}".lower()
            if any(ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            salary_text = ""
            if item.get("salary_min") and item.get("salary_max"):
                salary_text = f"${item['salary_min']:,} – ${item['salary_max']:,}"
            elif item.get("salary_min"):
                salary_text = f"${item['salary_min']:,}+"

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=item.get("location", "Remote"),
                    url=item.get("url", ""),
                    source=self.name,
                    description=_clean_html(description) if description else "",
                    salary=salary_text,
                    tags=keywords_list if isinstance(keywords_list, list) else [],
                    date_posted=item.get("date_posted", ""),
                    job_type="remote" if item.get("remote") else "onsite",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# Adzuna — free API (requires app_id + app_key, 250 free calls/month)
# ---------------------------------------------------------------------------


class AdzunaScraper(BaseScraper):
    name = "Adzuna"
    base_url = "https://api.adzuna.com/v1/api/jobs"

    # Map country to Adzuna country code
    COUNTRY_MAP = {
        "india": "in",
        "us": "us",
        "usa": "us",
        "united states": "us",
        "uk": "gb",
        "united kingdom": "gb",
        "canada": "ca",
        "australia": "au",
        "germany": "de",
        "france": "fr",
        "netherlands": "nl",
        "spain": "es",
        "italy": "it",
        "brazil": "br",
        "singapore": "sg",
        "poland": "pl",
    }

    def fetch_jobs(self, query: str) -> list[Job]:
        if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
            logger.info(f"[{self.name}] Skipped — no ADZUNA credentials set")
            return []

        country = LOCATION_PREFERENCES.get("default_country", "India").lower()
        country_code = self.COUNTRY_MAP.get(country, "gb")

        resp = self._safe_get(
            f"{self.base_url}/{country_code}/search/1",
            params={
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": query,
                "what_or": "remote",
                "results_per_page": 50,
                "content-type": "application/json",
            },
        )
        if not resp:
            return []

        try:
            data = resp.json().get("results", [])
        except Exception:
            return []

        jobs = []
        for item in data:
            title = item.get("title", "")
            description = item.get("description", "")
            company = item.get("company", {}).get("display_name", "")
            location = item.get("location", {}).get("display_name", "Remote")

            searchable = f"{title} {description}".lower()
            if any(ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            salary_text = ""
            if item.get("salary_min") and item.get("salary_max"):
                salary_text = (
                    f"${item['salary_min']:,.0f} – ${item['salary_max']:,.0f}/yr"
                )
            elif item.get("salary_min"):
                salary_text = f"${item['salary_min']:,.0f}+/yr"

            jobs.append(
                Job(
                    title=_clean_html(title),
                    company=company,
                    location=location,
                    url=item.get("redirect_url", ""),
                    source=self.name,
                    description=_clean_html(description),
                    salary=salary_text,
                    tags=(
                        [item.get("category", {}).get("label", "")]
                        if item.get("category")
                        else []
                    ),
                    date_posted=item.get("created", ""),
                    job_type="remote",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# The Muse — free JSON API
# ---------------------------------------------------------------------------


class TheMuseScraper(BaseScraper):
    name = "TheMuse"
    base_url = "https://www.themuse.com/api/public/jobs"

    def fetch_jobs(self, query: str) -> list[Job]:
        resp = self._safe_get(
            self.base_url,
            params={
                "page": 1,
                "descending": "true",
                "location": "Flexible / Remote",
                "category": "Engineering",
            },
        )
        if not resp:
            return []

        try:
            data = resp.json().get("results", [])
        except Exception:
            return []

        jobs = []
        keywords = query.lower().split()

        for item in data:
            title = item.get("name", "")
            company = item.get("company", {}).get("name", "")
            description = item.get("contents", "")
            locations = item.get("locations", [])
            location = (
                ", ".join(loc.get("name", "") for loc in locations)
                if locations
                else "Remote"
            )

            searchable = f"{title} {company} {description}".lower()
            if not any(kw in searchable for kw in keywords):
                continue
            if any(ex in searchable for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            levels = item.get("levels", [])
            level_names = [lvl.get("name", "") for lvl in levels]

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=location,
                    url=item.get("refs", {}).get("landing_page", ""),
                    source=self.name,
                    description=_clean_html(description),
                    salary="",
                    tags=level_names,
                    date_posted=item.get("publication_date", ""),
                    job_type="remote",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# HackerNews Who's Hiring — scrape monthly thread
# ---------------------------------------------------------------------------


class HackerNewsScraper(BaseScraper):
    name = "HackerNews"
    base_url = "https://hacker-news.firebaseio.com/v0"

    def fetch_jobs(self, query: str) -> list[Job]:
        # Search for the latest "Who is hiring?" thread
        resp = self._safe_get(
            f"{self.base_url}/user/whoishiring.json",
        )
        if not resp:
            return []

        try:
            user_data = resp.json()
            submitted = user_data.get("submitted", [])[:3]  # latest 3 posts
        except Exception:
            return []

        # Find the "Who is hiring" thread
        thread_id = None
        for post_id in submitted:
            post_resp = self._safe_get(f"{self.base_url}/item/{post_id}.json")
            if not post_resp:
                continue
            post = post_resp.json()
            if post and "who is hiring" in post.get("title", "").lower():
                thread_id = post_id
                break

        if not thread_id:
            return []

        # Get thread comments (job posts)
        thread_resp = self._safe_get(f"{self.base_url}/item/{thread_id}.json")
        if not thread_resp:
            return []

        kids = thread_resp.json().get("kids", [])[:100]  # limit to first 100 comments
        keywords = query.lower().split()
        jobs = []

        for kid_id in kids:
            comment_resp = self._safe_get(f"{self.base_url}/item/{kid_id}.json")
            if not comment_resp:
                continue

            comment = comment_resp.json()
            if not comment or comment.get("deleted") or comment.get("dead"):
                continue

            text = comment.get("text", "")
            if not text:
                continue

            clean_text = _clean_html(text)
            text_lower = clean_text.lower()

            if not any(kw in text_lower for kw in keywords):
                continue
            if any(ex in text_lower for ex in SEARCH_PREFERENCES["exclude_keywords"]):
                continue

            # Only include REMOTE jobs
            if "remote" not in text_lower:
                continue

            # Parse the first line as title | company
            first_line = clean_text.split(".")[0].split("|")[0].strip()[:100]
            parts = clean_text.split("|")
            company = parts[0].strip()[:60] if parts else "HN Posting"
            title = parts[1].strip()[:100] if len(parts) > 1 else first_line

            # Try to extract salary from text
            salary = _extract_salary_from_text(clean_text)

            jobs.append(
                Job(
                    title=title or first_line,
                    company=company,
                    location="Remote",
                    url=f"https://news.ycombinator.com/item?id={kid_id}",
                    source=self.name,
                    description=clean_text[:2000],
                    salary=salary,
                    tags=[],
                    date_posted="",
                    job_type="remote",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} matching jobs")
        return jobs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_html(text: str) -> str:
    """Strip HTML tags from text."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=" ", strip=True)
    clean = re.sub(r"\s+", " ", clean)
    return clean[:3000]


def _extract_salary_from_text(text: str) -> str:
    """Try to extract salary/compensation from free-form text."""
    patterns = [
        # $120k-$180k or $120K - $180K
        r"\$[\d,]+[kK]?\s*[-–]\s*\$[\d,]+[kK]?(?:\s*/?\s*(?:yr|year|annual|pa))?",
        # $120,000 - $180,000
        r"\$[\d,]{4,}\s*[-–]\s*\$[\d,]{4,}(?:\s*/?\s*(?:yr|year|annual|pa))?",
        # €80k-€120k or £80k-£120k
        r"[€£₹][\d,]+[kK]?\s*[-–]\s*[€£₹][\d,]+[kK]?",
        # USD 120k - 180k
        r"(?:USD|EUR|GBP|INR)\s*[\d,]+[kK]?\s*[-–]\s*[\d,]+[kK]?",
        # 120k-180k salary or comp
        r"[\d,]+[kK]\s*[-–]\s*[\d,]+[kK]\s*(?:USD|EUR|GBP|INR)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group().strip()
    return ""


# ---------------------------------------------------------------------------
# Country lookup — powered by pycountry (ISO 3166-1)
# ---------------------------------------------------------------------------

# Terms that mean "open to the whole world" — always accept
_GLOBAL_REMOTE_TERMS = {
    "worldwide",
    "global",
    "anywhere",
    "international",
    "distributed",
    "fully remote",
}

# Extra common-language names/abbreviations not in ISO that pycountry won't know
_EXTRA_ALIASES: dict[str, str] = {
    "usa": "US",
    "u.s.": "US",
    "america": "US",
    "uk": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "england": "GB",
    "britain": "GB",
    "holland": "NL",
    "deutschland": "DE",
    "uae": "AE",
    "emirates": "AE",
    "dubai": "AE",
    "abu dhabi": "AE",
    "korea": "KR",
}

# Country aliases for remote work filtering
_COUNTRY_ALIASES = _EXTRA_ALIASES


def _canonical_country(country_name: str) -> str | None:
    """
    Convert a country name to its ISO 3166-1 alpha-2 code.
    E.g., "India" → "IN", "USA" → "US", "UK" → "GB"
    """
    return _resolve_alpha2(country_name)


@lru_cache(maxsize=512)
def _resolve_alpha2(raw: str) -> str | None:
    """
    Return the ISO 3166-1 alpha-2 code for a country name / code string.
    Returns None if not recognised.
    """
    s = raw.strip().lower()
    if not s:
        return None

    # 1. Check extra aliases first
    extra = _EXTRA_ALIASES.get(s)
    if extra:
        return extra

    # 2. Try direct alpha-2 lookup (e.g. "us", "in", "gb")
    try:
        c = pycountry.countries.get(alpha_2=s.upper())
        if c:
            return c.alpha_2
    except Exception:
        pass

    # 3. Try alpha-3 (e.g. "usa", "ind", "gbr")
    try:
        c = pycountry.countries.get(alpha_3=s.upper())
        if c:
            return c.alpha_2
    except Exception:
        pass

    # 4. Fuzzy search by common / official name
    try:
        results = pycountry.countries.search_fuzzy(s)
        if results:
            return results[0].alpha_2
    except LookupError:
        pass

    return None


def _loc_contains_alpha2(loc_lower: str, alpha2: str) -> bool:
    """
    Check whether loc_lower contains a reference to the given ISO alpha-2 country.
    Builds patterns from all known names/codes for that country + extra aliases.
    Short codes (≤2 chars) require word-boundary isolation to avoid false matches
    (e.g. "us" inside "business", "in" inside "engineering").
    """
    try:
        country = pycountry.countries.get(alpha_2=alpha2)
    except Exception:
        return False
    if not country:
        return False

    # Build candidate strings: alpha-2, alpha-3, common name, official name
    candidates = {
        country.alpha_2.lower(),
        country.alpha_3.lower(),
        country.name.lower(),
    }
    if hasattr(country, "common_name"):
        candidates.add(country.common_name.lower())
    if hasattr(country, "official_name"):
        candidates.add(country.official_name.lower())

    # Add any extra aliases that map to this alpha-2
    for alias, a2 in _EXTRA_ALIASES.items():
        if a2 == alpha2:
            candidates.add(alias.lower())

    for token in candidates:
        if not token:
            continue
        if len(token) <= 2:
            # Standalone token: preceded/followed by non-alpha characters
            pattern = r"(?<![a-z])" + re.escape(token) + r"(?![a-z])"
        else:
            pattern = r"\b" + re.escape(token) + r"\b"
        if re.search(pattern, loc_lower):
            return True

    return False


def _matches_location_preference(job_location: str, user_country: str) -> bool:
    """
    Return True if the job's location is acceptable for the user's country preference.

    Rules (in order):
    1. Empty / placeholder → accept (assume open remote).
    2. "Worldwide", "Global", "Anywhere", etc. → always accept.
    3. Location contains user's country → accept.
    4. Location contains "remote" + a DIFFERENT country → reject.
       e.g. "Remote, USA" is rejected when user_country == "India".
    5. Location contains "remote" with NO country qualifier → accept.
    6. Specific foreign location → reject.
    """
    loc_lower = (job_location or "").lower().strip()

    # Rule 1 — empty or bare "remote" placeholder
    if not loc_lower or loc_lower in ("n/a", "not specified", "tbd", "-", "remote"):
        return True

    # Rule 2 — globally open
    if any(term in loc_lower for term in _GLOBAL_REMOTE_TERMS):
        return True

    user_alpha2 = _resolve_alpha2(user_country) if user_country else None

    # Rule 3 — location mentions user's country
    if user_alpha2 and _loc_contains_alpha2(loc_lower, user_alpha2):
        return True
    if user_country and user_country.lower() in loc_lower:
        return True

    has_remote = "remote" in loc_lower

    # Rule 4 — "remote" + a different country → reject
    if has_remote and user_alpha2:
        for country in pycountry.countries:
            if country.alpha_2 == user_alpha2:
                continue
            if _loc_contains_alpha2(loc_lower, country.alpha_2):
                return False

    # Rule 5 — "remote" with no country qualifier → accept
    if has_remote:
        return True

    # Rule 6 — specific foreign location → reject
    return False


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Reed.co.uk — UK job board with free API (requires API key, basic auth)
# ---------------------------------------------------------------------------


class ReedScraper(BaseScraper):
    name = "Reed"
    base_url = "https://www.reed.co.uk/api/1.0/search"

    def fetch_jobs(self, query: str) -> list[Job]:
        api_key = os.environ.get("REED_API_KEY", "")
        if not api_key:
            return []
        import base64

        auth = base64.b64encode(f"{api_key}:".encode()).decode()
        resp = self._safe_get(
            self.base_url,
            params={"keywords": query, "resultsToTake": 25},
            headers={"Authorization": f"Basic {auth}"},
        )
        if not resp:
            return []
        jobs = []
        for item in resp.json().get("results", []):
            jobs.append(
                Job(
                    title=item.get("jobTitle", ""),
                    company=item.get("employerName", ""),
                    location=item.get("locationName", ""),
                    url=item.get("jobUrl", ""),
                    source=self.name,
                    description=item.get("jobDescription", ""),
                    salary=(
                        f"{item.get('minimumSalary', '')} - {item.get('maximumSalary', '')}"
                        if item.get("minimumSalary")
                        else ""
                    ),
                    date_posted=item.get("date", ""),
                )
            )
        return jobs


# ---------------------------------------------------------------------------
# LinkedIn Jobs (via RapidAPI — uses existing JSEARCH or separate key)
# ---------------------------------------------------------------------------


class LinkedInJobsScraper(BaseScraper):
    name = "LinkedIn"
    base_url = "https://linkedin-jobs-search.p.rapidapi.com/"

    def fetch_jobs(self, query: str) -> list[Job]:
        api_key = os.environ.get("RAPIDAPI_KEY", os.environ.get("JSEARCH_API_KEY", ""))
        if not api_key:
            return []
        resp = self._safe_get(
            self.base_url,
            params={"search_terms": query, "location": "remote", "page": "1"},
            headers={
                "X-RapidAPI-Key": api_key,
                "X-RapidAPI-Host": "linkedin-jobs-search.p.rapidapi.com",
            },
        )
        if not resp:
            return []
        jobs = []
        for item in resp.json() if isinstance(resp.json(), list) else []:
            jobs.append(
                Job(
                    title=item.get("job_title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("job_location", "Remote"),
                    url=item.get("job_url", ""),
                    source=self.name,
                    description=item.get("job_description", ""),
                    date_posted=item.get("posted_date", ""),
                )
            )
        return jobs


# ---------------------------------------------------------------------------
# Himalayas.app — remote job board with free public JSON API
# ---------------------------------------------------------------------------


class HimalayasScraper(BaseScraper):
    name = "Himalayas"
    base_url = "https://himalayas.app/jobs/api"

    def fetch_jobs(self, query: str) -> list[Job]:
        resp = self._safe_get(self.base_url, params={"limit": 25, "q": query})
        parsed = self._safe_json(resp)
        if not parsed:
            return []
        jobs = []
        for item in parsed.get("jobs", []):
            tags = item.get("categories", []) or []
            salary = ""
            if item.get("salaryCurrency") and item.get("salaryMin"):
                salary = f"{item['salaryCurrency']} {item.get('salaryMin', '')} - {item.get('salaryMax', '')}"
            jobs.append(
                Job(
                    title=item.get("title", ""),
                    company=item.get("companyName", ""),
                    location=item.get("location", "Remote"),
                    url=f"https://himalayas.app/jobs/{item.get('slug', '')}",
                    source=self.name,
                    description=item.get("description", "")[:2000],
                    salary=salary,
                    tags=tags if isinstance(tags, list) else [],
                    date_posted=item.get("pubDate", ""),
                )
            )
        return jobs


# ---------------------------------------------------------------------------
# Jooble — global job aggregator with free API
# ---------------------------------------------------------------------------


class JoobleScraper(BaseScraper):
    name = "Jooble"
    base_url = "https://jooble.org/api/"

    def fetch_jobs(self, query: str) -> list[Job]:
        api_key = os.environ.get("JOOBLE_API_KEY", "")
        if not api_key:
            return []
        try:
            resp = requests.post(
                f"{self.base_url}{api_key}",
                json={"keywords": query, "location": "remote", "page": 1},
                headers=_DEFAULT_HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            jobs = []
            for item in resp.json().get("jobs", []):
                jobs.append(
                    Job(
                        title=item.get("title", ""),
                        company=item.get("company", ""),
                        location=item.get("location", "Remote"),
                        url=item.get("link", ""),
                        source=self.name,
                        description=item.get("snippet", ""),
                        salary=item.get("salary", ""),
                        date_posted=item.get("updated", ""),
                    )
                )
            return jobs
        except Exception as e:
            logger.warning(f"[{self.name}] Request failed: {e}")
            return []


# ---------------------------------------------------------------------------
# Arbeitsagentur (German Federal Employment Agency) — free public API
# ---------------------------------------------------------------------------


class ArbeitsagenturScraper(BaseScraper):
    name = "Arbeitsagentur"
    base_url = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

    def fetch_jobs(self, query: str) -> list[Job]:
        resp = self._safe_get(
            self.base_url,
            params={"was": query, "size": 25, "page": 0},
            headers={"X-API-Key": "jobboerse-jobsuche"},
        )
        if not resp:
            return []
        jobs = []
        for item in resp.json().get("stellenangebote", []):
            jobs.append(
                Job(
                    title=item.get("titel", ""),
                    company=item.get("arbeitgeber", ""),
                    location=item.get("arbeitsort", {}).get("ort", "Germany"),
                    url=f"https://www.arbeitsagentur.de/jobsuche/suche?id={item.get('hashId', '')}",
                    source=self.name,
                    description=item.get("titel", ""),
                    date_posted=item.get("eintrittsdatum", ""),
                )
            )
        return jobs


# ---------------------------------------------------------------------------
# USAJobs — US government jobs (free, public API)
# ---------------------------------------------------------------------------


class USAJobsScraper(BaseScraper):
    name = "USAJobs"
    base_url = "https://data.usajobs.gov/api/Search"

    def fetch_jobs(self, query: str) -> list[Job]:
        api_key = os.environ.get("USAJOBS_API_KEY", "")
        email = os.environ.get("USAJOBS_EMAIL", "")
        if not api_key or not email:
            return []
        resp = self._safe_get(
            self.base_url,
            params={"Keyword": query, "ResultsPerPage": 25, "RemoteIndicator": "True"},
            headers={
                "Authorization-Key": api_key,
                "User-Agent": email,
                "Host": "data.usajobs.gov",
            },
        )
        if not resp:
            return []
        jobs = []
        for item in resp.json().get("SearchResult", {}).get("SearchResultItems", []):
            pos = item.get("MatchedObjectDescriptor", {})
            salary_min = (
                pos.get("PositionRemuneration", [{}])[0].get("MinimumRange", "")
                if pos.get("PositionRemuneration")
                else ""
            )
            salary_max = (
                pos.get("PositionRemuneration", [{}])[0].get("MaximumRange", "")
                if pos.get("PositionRemuneration")
                else ""
            )
            jobs.append(
                Job(
                    title=pos.get("PositionTitle", ""),
                    company=pos.get("OrganizationName", "US Government"),
                    location=pos.get("PositionLocationDisplay", ""),
                    url=pos.get("PositionURI", ""),
                    source=self.name,
                    description=pos.get("QualificationSummary", ""),
                    salary=f"${salary_min} - ${salary_max}" if salary_min else "",
                    date_posted=pos.get("PublicationStartDate", ""),
                )
            )
        return jobs


# ---------------------------------------------------------------------------
# SerpAPI — Google Jobs (Official API · serpapi.com)
# Aggregates Indeed, LinkedIn, Glassdoor, Naukri, Monster and more
# Free tier: 100 searches/month  |  Paid: from $50/mo for 5,000 searches
# Register: https://serpapi.com/users/sign_up
# ---------------------------------------------------------------------------


class SerpApiGoogleJobsScraper(BaseScraper):
    """
    Official SerpAPI endpoint for Google Jobs.
    Covers Indeed, LinkedIn, Glassdoor, Naukri, ZipRecruiter and ~20 other
    boards in a single query — all through Google's own job index.
    """

    name = "GoogleJobs"
    base_url = "https://serpapi.com/search.json"

    def fetch_jobs(self, query: str) -> list[Job]:
        api_key = os.environ.get("SERPAPI_KEY", "").strip()
        if not api_key:
            return []

        params = {
            "engine": "google_jobs",
            "q": query,
            "api_key": api_key,
            "num": 10,  # max per request on free tier
            "hl": "en",
        }

        resp = self._safe_get(self.base_url, params=params, timeout=30)
        if not resp:
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        if data.get("error"):
            logger.warning(f"[{self.name}] API error: {data['error']}")
            return []

        jobs = []
        for item in data.get("jobs_results", []):
            title = item.get("title", "")
            company = item.get("company_name", "")
            loc = item.get("location", "Remote")

            # Apply link — prefer direct, fall back to the first option
            apply_opts = item.get("apply_options") or []
            url = apply_opts[0].get("link", "") if apply_opts else ""
            if not url:
                # Google Jobs redirect link
                url = f"https://www.google.com/search?q={quote_plus(title + ' ' + company)}&ibp=htl;jobs"

            description = item.get("description", "")

            # Salary + date from detected_extensions dict or extensions list
            salary = ""
            date_posted = ""
            ext = item.get("detected_extensions") or {}
            if isinstance(ext, dict):
                salary = ext.get("salary", "")
                date_posted = ext.get("posted_at", "")
            elif isinstance(ext, list):
                for token in ext:
                    tl = token.lower()
                    if any(
                        c in tl
                        for c in ["$", "£", "€", "₹", "lpa", "salary", "salary range"]
                    ):
                        salary = token
                    elif any(
                        w in tl
                        for w in ["day", "week", "month", "hour", "ago", "just posted"]
                    ):
                        date_posted = token

            # Extensions list also carries job_type hints
            job_type = "remote"
            for token in item.get("extensions") or []:
                tl = token.lower()
                if "full-time" in tl:
                    job_type = "full-time"
                elif "part-time" in tl:
                    job_type = "part-time"
                elif "contract" in tl:
                    job_type = "contract"

            # Tags from job highlights
            highlights = item.get("job_highlights") or []
            tags: list[str] = []
            for h in highlights:
                for line in h.get("items") or []:
                    tags += [
                        w.strip() for w in line.split(",") if 3 < len(w.strip()) < 30
                    ]
            tags = list(dict.fromkeys(tags))[:10]

            if not title or not url:
                continue

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=loc,
                    url=url,
                    source=self.name,
                    description=description[:3000],
                    salary=salary,
                    tags=tags,
                    date_posted=date_posted,
                    job_type=job_type,
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} jobs for '{query}'")
        return jobs


# ---------------------------------------------------------------------------
# CareerJet — Free Official Affiliate API (careerjet.com)
# Covers 90+ countries including India, aggregates from 2,500+ job boards
# Register (free): https://www.careerjet.com/partners/
# Get affid from: https://www.careerjet.com/partners/api/
# ---------------------------------------------------------------------------


class CareerJetScraper(BaseScraper):
    """
    CareerJet's free official partner API.
    No per-request cost; requires free affiliate ID registration.
    Strong India, UK, and APAC coverage via 2,500+ aggregated job boards.
    """

    name = "CareerJet"
    base_url = "http://public.api.careerjet.net/search"

    # Locale codes for major supported countries
    _LOCALE_MAP = {
        "india": "en_IN",
        "in": "en_IN",
        "united states": "en_US",
        "us": "en_US",
        "usa": "en_US",
        "united kingdom": "en_GB",
        "uk": "en_GB",
        "canada": "en_CA",
        "ca": "en_CA",
        "australia": "en_AU",
        "au": "en_AU",
        "germany": "de_DE",
        "de": "de_DE",
        "singapore": "en_SG",
        "sg": "en_SG",
        "uae": "en_AE",
        "ae": "en_AE",
    }

    def fetch_jobs(self, query: str) -> list[Job]:
        affid = os.environ.get("CAREERJET_AFFID", "").strip()
        if not affid:
            return []

        country = LOCATION_PREFERENCES.get("default_country", "India").lower()
        locale = self._LOCALE_MAP.get(country, "en_IN")

        params = {
            "affid": affid,
            "keywords": query,
            "location": "remote",
            "locale_code": locale,
            "pagesize": 20,
            "page": 1,
            # Required fields per CareerJet TOS
            "user_ip": "1.1.1.1",  # client IP (1.1.1.1 = anonymous placeholder)
            "url": "https://jobbot.app",
            "user_agent": "JobBot/1.0",
        }

        resp = self._safe_get(self.base_url, params=params, timeout=20)
        if not resp:
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        if data.get("type") == "ERROR":
            logger.warning(f"[{self.name}] API error: {data.get('status')}")
            return []

        jobs = []
        for item in data.get("jobs") or []:
            title = item.get("title", "")
            company = item.get("company", "")
            loc = item.get("locations", "Remote")
            url = item.get("url", "")
            desc = item.get("description", "")
            salary = item.get("salary", "")
            date_posted = item.get("date", "")

            if not title or not url:
                continue

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=loc,
                    url=url,
                    source=self.name,
                    description=desc[:3000],
                    salary=salary,
                    tags=[],
                    date_posted=date_posted,
                    job_type="remote",
                )
            )

        logger.info(f"[{self.name}] Found {len(jobs)} jobs for '{query}'")
        return jobs


# ---------------------------------------------------------------------------
# All scrapers
# ---------------------------------------------------------------------------

ALL_SCRAPERS: list[BaseScraper] = [
    # ── Free public APIs (no key needed) ─────────────────────────────────
    ArbeitnowScraper(),  # remote-first, EU + global
    JobicyScraper(),  # remote jobs aggregator
    TheMuseScraper(),  # curated tech & creative roles
    HackerNewsScraper(),  # HN Who's Hiring thread
    RemotiveScraper(),  # remote-only board
    HimalayasScraper(),  # remote-first, high quality listings
    # ── API key required ─────────────────────────────────────────────────
    JSearchScraper(),  # RapidAPI · aggregates Indeed + LinkedIn + Glassdoor
    AdzunaScraper(),  # Adzuna official API · strong India + UK coverage
    JoobleScraper(),  # Jooble official API · 71-country aggregator
    ReedScraper(),  # Reed.co.uk official API · strong UK + remote
    USAJobsScraper(),  # USAJobs.gov · US federal / remote-US roles
    # ── New legitimate APIs ───────────────────────────────────────────────
    SerpApiGoogleJobsScraper(),  # SerpAPI Google Jobs · aggregates Indeed + LinkedIn + Glassdoor + Naukri (SERPAPI_KEY)
    CareerJetScraper(),  # CareerJet official API · 2,500+ boards, strong India coverage (CAREERJET_AFFID)
]


# ---------------------------------------------------------------------------
# In-memory scraper result cache — avoids hammering APIs on repeated searches
# ---------------------------------------------------------------------------

_SCRAPER_CACHE: dict[str, tuple[float, list]] = {}
_CACHE_TTL = 7200  # 2 hours in seconds


def _scrape_task(scraper: BaseScraper, query: str, location: str) -> list[Job]:
    """Single scrape task with 2-hour in-memory cache per (scraper, query, location)."""
    cache_key = f"{scraper.name}|{query.lower().strip()}|{location.lower().strip()}"
    now = time.time()

    # Check cache
    if cache_key in _SCRAPER_CACHE:
        ts, cached_jobs = _SCRAPER_CACHE[cache_key]
        if now - ts < _CACHE_TTL:
            logger.debug(f"[{scraper.name}] Cache hit for '{query}'")
            return cached_jobs

    try:
        jobs = scraper.fetch_jobs(query)
        _SCRAPER_CACHE[cache_key] = (now, jobs)
        return jobs
    except Exception as e:
        logger.error(f"[{scraper.name}] Error: {e}")
        return []


def search_all_boards(
    queries: list[str] = None, location: str = "remote", country: str = ""
) -> list[Job]:
    """Search all job boards in parallel with user-provided queries and location.

    Args:
        queries: Search query strings
        location: Location filter (e.g. "remote", "remote in India", city name)
        country: Country name for remote-in-country filtering (defaults to LOCATION_PREFERENCES)
    """
    if queries is None:
        queries = SEARCH_PREFERENCES["target_roles"][:5]

    # Limit queries to avoid excessive API calls
    queries = queries[:5]

    # Resolve country for location filtering
    user_country = country or LOCATION_PREFERENCES.get("default_country", "India")

    all_jobs: list[Job] = []
    seen_urls: set[str] = set()

    # Build all (scraper, query) tasks
    tasks = []
    for query in queries:
        search_query = query
        if location and location.lower() != "remote":
            search_query = f"{query} {location}"
        for scraper in ALL_SCRAPERS:
            tasks.append((scraper, search_query))

    # Run all tasks in parallel (max 12 threads for more scrapers)
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {
            executor.submit(_scrape_task, scraper, query, location): (
                scraper.name,
                query,
            )
            for scraper, query in tasks
        }

        for future in as_completed(futures):
            jobs = future.result()
            for job in jobs:
                # Primary location filter: uses country-aware logic
                if not _matches_location_preference(job.location, user_country):
                    # Secondary fallback: description explicitly says "remote" AND
                    # mentions the user's country — then accept despite ambiguous location.
                    # We do NOT accept just because the word "remote" appears in the
                    # description — that would let through "Remote, USA" for India users.
                    desc_lower = job.description.lower()
                    country_mentioned = user_country.lower() in desc_lower or any(
                        alias in desc_lower
                        for alias, canon in _COUNTRY_ALIASES.items()
                        if canon == _canonical_country(user_country)
                    )
                    if not (("remote" in desc_lower) and country_mentioned):
                        continue

                if job.url and job.url not in seen_urls:
                    seen_urls.add(job.url)
                    # Normalize salary if present in description but not in salary field
                    if not job.salary and job.description:
                        extracted = _extract_salary_from_text(job.description)
                        if extracted:
                            job.salary = extracted
                    all_jobs.append(job)

    logger.info(
        f"Total unique jobs found: {len(all_jobs)} (country filter: {user_country})"
    )
    return all_jobs
