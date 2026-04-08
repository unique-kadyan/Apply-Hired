"""Import profile data from GitHub and LinkedIn."""

import re
import logging
import requests

logger = logging.getLogger(__name__)


def import_github(username: str) -> dict:
    """Fetch public profile + repos from GitHub. Returns enrichment dict."""
    if not username:
        return {}

    username = username.strip().strip("/").split("/")[-1]  # handle full URLs

    try:
        # User profile
        user = requests.get(
            f"https://api.github.com/users/{username}",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        ).json()

        if user.get("message") == "Not Found":
            return {"error": "GitHub user not found"}

        # Top repos (by stars)
        repos = requests.get(
            f"https://api.github.com/users/{username}/repos?sort=stars&per_page=20",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        ).json()

        # Extract languages from repos
        languages = {}
        for repo in (repos if isinstance(repos, list) else []):
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1

        top_languages = sorted(languages, key=languages.get, reverse=True)[:10]

        # Top projects
        top_repos = []
        for repo in (repos if isinstance(repos, list) else [])[:5]:
            if repo.get("fork"):
                continue
            top_repos.append({
                "name": repo.get("name", ""),
                "description": repo.get("description", "") or "",
                "url": repo.get("html_url", ""),
                "language": repo.get("language", ""),
                "stars": repo.get("stargazers_count", 0),
            })

        # Extract topics/skills from repos
        all_topics = []
        for repo in (repos if isinstance(repos, list) else []):
            all_topics.extend(repo.get("topics", []))
        unique_topics = list(dict.fromkeys(all_topics))[:20]

        return {
            "github_username": username,
            "github_url": user.get("html_url", ""),
            "name": user.get("name", ""),
            "bio": user.get("bio", ""),
            "location": user.get("location", ""),
            "company": user.get("company", ""),
            "blog": user.get("blog", ""),
            "public_repos": user.get("public_repos", 0),
            "followers": user.get("followers", 0),
            "languages": top_languages,
            "topics": unique_topics,
            "top_repos": top_repos,
        }
    except Exception as e:
        logger.error(f"GitHub import failed: {e}")
        return {"error": str(e)}


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
