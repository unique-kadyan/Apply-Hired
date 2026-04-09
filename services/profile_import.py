"""Import profile data from GitHub and LinkedIn."""

import logging
import os

import requests

logger = logging.getLogger(__name__)


def _github_headers(user_token: str = "") -> dict:
    """Return GitHub API headers. User-supplied token takes priority over env token."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = (user_token or "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_github_username(raw: str) -> str:
    """Extract bare username from a URL or plain username string."""
    raw = raw.strip().rstrip("/")
    # Handle URLs like https://github.com/username or github.com/username
    if "github.com" in raw:
        parts = raw.split("github.com/")
        if len(parts) > 1:
            # Take the first path segment only (ignore /repos, /starred, etc.)
            return parts[1].split("/")[0].strip()
    return raw.split("/")[-1].strip()


def import_github(username: str, token: str = "") -> dict:
    """Fetch public profile + repos from GitHub. Returns enrichment dict."""
    if not username:
        return {"error": "GitHub username or URL is required"}

    username = _extract_github_username(username)
    if not username:
        return {"error": "Could not extract GitHub username from the provided input"}

    headers = _github_headers(user_token=token)

    try:
        # User profile
        resp = requests.get(
            f"https://api.github.com/users/{username}",
            headers=headers,
            timeout=15,
        )
        user = resp.json()

        # Detect API errors
        msg = user.get("message", "")
        if "Not Found" in msg or resp.status_code == 404:
            return {"error": f"GitHub user '{username}' not found. Check the username/URL."}
        if "rate limit" in msg.lower() or resp.status_code == 403:
            hint = " Add a GITHUB_TOKEN to your .env to increase the limit." if not os.environ.get("GITHUB_TOKEN") else ""
            return {"error": f"GitHub API rate limit exceeded.{hint}"}
        if resp.status_code != 200:
            return {"error": f"GitHub API error {resp.status_code}: {msg}"}

        # Repos sorted by most recently pushed (recency-first)
        repos_resp = requests.get(
            f"https://api.github.com/users/{username}/repos?sort=pushed&direction=desc&per_page=50",
            headers=headers,
            timeout=15,
        )
        repos = repos_resp.json() if repos_resp.status_code == 200 else []

        # Extract languages from repos
        languages = {}
        for repo in (repos if isinstance(repos, list) else []):
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1

        top_languages = sorted(languages, key=languages.get, reverse=True)[:10]

        # All non-fork repos with topics (for full list in frontend)
        top_repos = []
        for repo in (repos if isinstance(repos, list) else []):
            if repo.get("fork"):
                continue
            top_repos.append({
                "name": repo.get("name", ""),
                "description": repo.get("description", "") or "",
                "url": repo.get("html_url", ""),
                "language": repo.get("language", "") or "",
                "stars": repo.get("stargazers_count", 0),
                "topics": repo.get("topics", []),
                "pushed_at": repo.get("pushed_at", ""),
            })

        # Extract topics/skills from repos
        all_topics = []
        for repo in (repos if isinstance(repos, list) else []):
            all_topics.extend(repo.get("topics", []))
        unique_topics = list(dict.fromkeys(all_topics))[:20]

        github_url = user.get("html_url") or f"https://github.com/{username}"
        return {
            "github_username": username,
            "github_url": github_url,
            "name": user.get("name") or "",
            "bio": user.get("bio") or "",
            "location": user.get("location") or "",
            "company": user.get("company") or "",
            "blog": user.get("blog") or "",
            "public_repos": user.get("public_repos", 0),
            "followers": user.get("followers", 0),
            "languages": top_languages,
            "topics": unique_topics,
            "top_repos": top_repos,
        }
    except requests.exceptions.Timeout:
        return {"error": "GitHub API timed out. Please try again."}
    except requests.exceptions.ConnectionError:
        return {"error": "Could not reach GitHub API. Check your internet connection."}
    except Exception as e:
        logger.error(f"GitHub import failed: {e}")
        return {"error": f"Import failed: {str(e)}"}


def import_linkedin_url(url: str) -> dict:
    """Extract what we can from a LinkedIn profile URL.

    LinkedIn blocks scraping, so we just store the URL and
    ask the user to paste their LinkedIn summary.
    """
    if not url:
        return {}

    # Normalize URL
    url = url.strip()
    if "linkedin.com" not in url:
        url = f"https://www.linkedin.com/in/{url}"

    return {
        "linkedin_url": url,
    }


def merge_github_into_profile(profile: dict, github_data: dict) -> dict:
    """Merge GitHub data into existing profile without overwriting user edits."""
    if github_data.get("error"):
        return profile

    # Add GitHub URL
    profile["github"] = github_data.get("github_url", "")
    profile["github_username"] = github_data.get("github_username", "")

    # Add blog/portfolio if not set
    if not profile.get("website") and github_data.get("blog"):
        profile["website"] = github_data["blog"]

    # Merge languages into skills
    lang_map = {
        "JavaScript": "languages", "TypeScript": "languages", "Python": "languages",
        "Java": "languages", "Go": "languages", "Rust": "languages", "C++": "languages",
        "C#": "languages", "Ruby": "languages", "PHP": "languages", "Kotlin": "languages",
        "Swift": "languages", "Scala": "languages", "Shell": "languages",
    }
    framework_map = {
        "react": "frontend", "vue": "frontend", "angular": "frontend", "nextjs": "frontend",
        "svelte": "frontend", "tailwindcss": "frontend",
        "django": "backend", "flask": "backend", "fastapi": "backend", "spring-boot": "backend",
        "express": "backend", "nestjs": "backend", "rails": "backend",
        "docker": "cloud_devops", "kubernetes": "cloud_devops", "terraform": "cloud_devops",
        "aws": "cloud_devops", "gcp": "cloud_devops", "azure": "cloud_devops",
        "postgresql": "databases", "mongodb": "databases", "redis": "databases",
        "mysql": "databases", "elasticsearch": "databases",
    }

    skills = profile.get("skills", {})
    for lang in github_data.get("languages", []):
        group = lang_map.get(lang, "languages")
        if group not in skills:
            skills[group] = []
        if lang not in skills[group]:
            skills[group].append(lang)

    for topic in github_data.get("topics", []):
        topic_lower = topic.lower().replace("-", "").replace("_", "")
        for key, group in framework_map.items():
            if key.replace("-", "") in topic_lower:
                if group not in skills:
                    skills[group] = []
                display = topic.replace("-", " ").title()
                if display not in skills[group]:
                    skills[group].append(display)
                break

    profile["skills"] = skills

    # Add top repos as projects
    if github_data.get("top_repos"):
        profile["projects"] = github_data["top_repos"]

    # Fill name/location if empty
    if not profile.get("name") and github_data.get("name"):
        profile["name"] = github_data["name"]
    if not profile.get("location") and github_data.get("location"):
        profile["location"] = github_data["location"]

    return profile
