"""Auto-apply module — opens job pages in browser, auto-fills forms using Selenium + AI."""

import os
import time
import json
import logging
import re
import webbrowser

from config import PROFILE, OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Path to resume file for upload (look in uploads/ or project root)
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RESUME_PATH = os.environ.get("RESUME_PATH", "")
if not RESUME_PATH:
    for folder in [os.path.join(_PROJECT_DIR, "uploads"), _PROJECT_DIR]:
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                if f.lower().endswith((".pdf", ".docx")) and "resume" in f.lower():
                    RESUME_PATH = os.path.join(folder, f)
                    break
        if RESUME_PATH:
            break


def _get_driver():
    """Initialize Selenium Chrome driver with anti-detection."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option("detach", True)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        driver.implicitly_wait(5)
        return driver
    except Exception as e:
        logger.error(f"Failed to start Chrome driver: {e}")
        return None


def _wait_for_page_and_forms(driver, timeout=10):
    """Wait for page to fully load and for form elements to appear."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        # Wait for document ready state
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # Extra wait for JS frameworks to render
        time.sleep(2)

        # Wait for at least one input/textarea/form to be present
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input, textarea, form, [role='textbox']")
                )
            )
        except Exception:
            pass  # page may not have forms yet (need to click Apply first)

    except Exception:
        time.sleep(3)  # fallback


def _normalize(text: str) -> str:
    """Normalize text for fuzzy field matching."""
    return re.sub(r"[^a-z0-9]", " ", text.lower()).strip()


def _get_field_identifiers(el) -> str:
    """Extract all identifying attributes from a form element."""
    parts = []
    for attr in ("name", "id", "placeholder", "aria-label", "autocomplete",
                 "data-testid", "data-automation-id", "formcontrolname", "class"):
        val = el.get_attribute(attr)
        if val:
            parts.append(val)

    # Also check parent label text
    try:
        driver = el.parent
        el_id = el.get_attribute("id")
        if el_id:
            from selenium.webdriver.common.by import By
            labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{el_id}']")
            for lbl in labels:
                if lbl.text:
                    parts.append(lbl.text)
    except Exception:
        pass

    # Check closest ancestor label
    try:
        from selenium.webdriver.common.by import By
        parent_label = el.find_element(By.XPATH, "./ancestor::label")
        if parent_label and parent_label.text:
            parts.append(parent_label.text)
    except Exception:
        pass

    return " ".join(parts)


def _safe_fill(el, value: str):
    """Clear and fill a form field safely."""
    try:
        existing = el.get_attribute("value") or ""
        if existing.strip():
            return False  # don't overwrite existing values
        el.click()
        time.sleep(0.1)
        el.clear()
        el.send_keys(value)
        return True
    except Exception:
        return False


def _upload_resume(driver):
    """Find file input fields and upload resume if available."""
    if not RESUME_PATH or not os.path.isfile(RESUME_PATH):
        return False

    from selenium.webdriver.common.by import By

    file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
    uploaded = False
    for fi in file_inputs:
        try:
            identifiers = _get_field_identifiers(fi)
            norm = _normalize(identifiers)
            # Upload to resume/CV fields (not cover letter file uploads)
            if any(kw in norm for kw in ["resume", "cv", "file", "upload", "attach", "document"]):
                fi.send_keys(os.path.abspath(RESUME_PATH))
                uploaded = True
                logger.info(f"Uploaded resume: {RESUME_PATH}")
                break
        except Exception as e:
            logger.debug(f"Resume upload failed: {e}")
    return uploaded


# ---------------------------------------------------------------------------
# Field mapping — maps form field hints to profile values
# ---------------------------------------------------------------------------

def _build_field_map() -> list[tuple[list[str], str]]:
    """Build a list of (keywords, value) for form field matching.

    Returns a list of tuples. Each tuple is (list_of_keywords, value_to_fill).
    Keywords are checked against normalized field identifiers.
    Order matters — first match wins.
    """
    name = PROFILE.get("name", "")
    parts = name.split() if name else ["", ""]
    first_name = parts[0] if parts else ""
    last_name = parts[-1] if len(parts) > 1 else ""

    location = PROFILE.get("location", "")
    city = location.split(",")[0].strip() if location else ""

    experience = PROFILE.get("experience", [])
    current_company = experience[0].get("company", "") if experience else ""

    return [
        (["first name", "first_name", "firstname", "given name"], first_name),
        (["last name", "last_name", "lastname", "surname", "family name"], last_name),
        (["full name", "full_name", "fullname", "your name", "candidate name"], name),
        (["name"], name),  # generic "name" last so first/last name match first
        (["email", "e mail"], PROFILE.get("email", "")),
        (["phone", "mobile", "telephone", "contact number"], PROFILE.get("phone", "")),
        (["city", "town"], city),
        (["location", "address"], location),
        (["linkedin", "linked in"], PROFILE.get("linkedin", "")),
        (["github"], PROFILE.get("github", "")),
        (["website", "portfolio", "personal site", "url"], PROFILE.get("website", "")),
        (["years of experience", "years experience", "total experience", "experience year"],
         str(PROFILE.get("years_of_experience", ""))),
        (["current company", "employer", "company name"], current_company),
        (["current title", "job title", "current role", "headline", "current position"],
         PROFILE.get("title", "")),
        (["salary", "expected salary", "desired salary", "compensation"], ""),
        (["notice period", "notice"], "Immediate / 15 days"),
    ]


def _fill_common_fields(driver, job: dict) -> int:
    """Fill common form fields. Returns count of fields filled."""
    from selenium.webdriver.common.by import By

    field_map = _build_field_map()
    filled_count = 0

    # Fill input fields
    inputs = driver.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']):not([type='submit'])"
                                  ":not([type='button']):not([type='checkbox'])"
                                  ":not([type='radio']):not([type='file'])")
    for inp in inputs:
        try:
            if not inp.is_displayed():
                continue
            identifiers = _get_field_identifiers(inp)
            norm = _normalize(identifiers)

            for keywords, value in field_map:
                if value and any(kw in norm for kw in keywords):
                    if _safe_fill(inp, value):
                        filled_count += 1
                        logger.debug(f"Filled '{identifiers[:50]}' with '{value[:20]}'")
                    break
        except Exception:
            continue

    # Fill textareas (cover letter / additional info)
    textareas = driver.find_elements(By.TAG_NAME, "textarea")
    cover_letter = job.get("cover_letter", "")
    for ta in textareas:
        try:
            if not ta.is_displayed():
                continue
            identifiers = _get_field_identifiers(ta)
            norm = _normalize(identifiers)

            # Cover letter / message fields
            if any(kw in norm for kw in [
                "cover", "letter", "message", "note", "why", "about",
                "motivation", "additional", "summary", "intro",
            ]):
                if cover_letter and _safe_fill(ta, cover_letter):
                    filled_count += 1
            # Generic large text area — fill with summary if nothing else
            elif not (ta.get_attribute("value") or "").strip():
                summary = PROFILE.get("summary", "")
                if summary and _safe_fill(ta, summary):
                    filled_count += 1
        except Exception:
            continue

    # Try to upload resume
    if _upload_resume(driver):
        filled_count += 1

    return filled_count


# ---------------------------------------------------------------------------
# Platform-specific handlers
# ---------------------------------------------------------------------------

def _click_apply_button(driver) -> bool:
    """Find and click an Apply / Easy Apply button on the page."""
    from selenium.webdriver.common.by import By

    # Common apply button selectors (ordered by specificity)
    selectors = [
        # LinkedIn
        "button.jobs-apply-button",
        "button[aria-label*='Easy Apply']",
        # Indeed
        "#indeedApplyButton",
        "button[id*='applyButton']",
        # Greenhouse
        "a#apply_button",
        "a[href*='#app']",
        # Lever
        "a.postings-btn[href*='apply']",
        # Generic
        "a[href*='apply']",
        "button[data-testid*='apply']",
    ]

    for sel in selectors:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for btn in btns:
                if btn.is_displayed():
                    btn.click()
                    time.sleep(2)
                    return True
        except Exception:
            continue

    # Fallback: find any button/link with "apply" text
    for tag in ("button", "a"):
        try:
            elements = driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                text = (el.text or "").strip().lower()
                if text in ("apply", "apply now", "easy apply", "apply for this job",
                            "apply to this job", "submit application", "apply on company site"):
                    if el.is_displayed():
                        el.click()
                        time.sleep(2)
                        return True
        except Exception:
            continue

    return False


def _try_platform_apply(driver, job: dict) -> bool:
    """Platform-specific apply logic for known job sites."""
    current_url = driver.current_url.lower()

    try:
        if "linkedin.com" in current_url:
            return _linkedin_easy_apply(driver, job)
        if "indeed.com" in current_url:
            return _indeed_apply(driver, job)
        if "greenhouse.io" in current_url:
            return _greenhouse_apply(driver, job)
        if "lever.co" in current_url:
            return _lever_apply(driver, job)
        if "workday" in current_url or "myworkdayjobs" in current_url:
            return _workday_apply(driver, job)
    except Exception as e:
        logger.debug(f"Platform apply failed for {current_url}: {e}")

    return False


def _linkedin_easy_apply(driver, job: dict) -> bool:
    """Attempt LinkedIn Easy Apply."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        # Click Easy Apply button
        easy_apply_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 "button.jobs-apply-button, "
                 "button[aria-label*='Easy Apply'], "
                 "button.jobs-apply-button--top-card")
            )
        )
        easy_apply_btn.click()
        time.sleep(2)

        # LinkedIn Easy Apply is a multi-step modal
        filled_total = 0
        max_steps = 10  # safety limit
        for step in range(max_steps):
            filled_total += _fill_common_fields(driver, job)
            time.sleep(1)

            # Look for Next / Review / Submit button
            clicked_next = False
            for btn_text in ("next", "review", "submit application", "submit"):
                try:
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        if btn.is_displayed() and btn_text in (btn.text or "").lower():
                            btn.click()
                            time.sleep(2)
                            clicked_next = True
                            break
                except Exception:
                    continue
                if clicked_next:
                    break

            if not clicked_next:
                break

            # Check if we hit "Submit application"
            try:
                current_text = driver.find_element(
                    By.CSS_SELECTOR, ".artdeco-modal__content, .jobs-easy-apply-content"
                ).text.lower()
                if "application submitted" in current_text or "applied" in current_text:
                    return True
            except Exception:
                pass

        return filled_total > 0
    except Exception as e:
        logger.debug(f"LinkedIn Easy Apply failed: {e}")
        return False


def _indeed_apply(driver, job: dict) -> bool:
    """Attempt Indeed Apply."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        # Click apply button
        try:
            apply_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR,
                     "#indeedApplyButton, "
                     "button[id*='applyButton'], "
                     "button[class*='apply'], "
                     "a[href*='apply']")
                )
            )
            apply_btn.click()
            time.sleep(3)
        except Exception:
            _click_apply_button(driver)

        # Indeed can have multi-step forms too
        filled_total = 0
        for step in range(5):
            filled_total += _fill_common_fields(driver, job)
            time.sleep(1)

            # Click Continue / Submit
            clicked = False
            for text in ("continue", "submit your application", "apply", "submit"):
                try:
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        if btn.is_displayed() and text in (btn.text or "").lower():
                            btn.click()
                            time.sleep(2)
                            clicked = True
                            break
                except Exception:
                    continue
                if clicked:
                    break
            if not clicked:
                break

        return filled_total > 0
    except Exception as e:
        logger.debug(f"Indeed apply failed: {e}")
        return False


def _greenhouse_apply(driver, job: dict) -> bool:
    """Attempt Greenhouse application form fill."""
    from selenium.webdriver.common.by import By

    try:
        # Greenhouse forms are usually on the page directly or behind an "Apply" link
        _click_apply_button(driver)
        _wait_for_page_and_forms(driver)
        filled = _fill_common_fields(driver, job)

        # Try to click submit
        try:
            submit = driver.find_element(
                By.CSS_SELECTOR, "input[type='submit'], button[type='submit']"
            )
            if submit.is_displayed():
                submit.click()
        except Exception:
            pass

        return filled > 0
    except Exception:
        return False


def _lever_apply(driver, job: dict) -> bool:
    """Attempt Lever application form fill."""
    try:
        _click_apply_button(driver)
        _wait_for_page_and_forms(driver)
        filled = _fill_common_fields(driver, job)
        return filled > 0
    except Exception:
        return False


def _workday_apply(driver, job: dict) -> bool:
    """Attempt Workday application form fill."""
    try:
        _click_apply_button(driver)
        _wait_for_page_and_forms(driver, timeout=15)  # Workday is slow
        filled = _fill_common_fields(driver, job)
        return filled > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Generic auto-fill
# ---------------------------------------------------------------------------

def _try_autofill(driver, job: dict) -> bool:
    """Try to auto-fill application form fields on the current page."""
    try:
        # First try clicking an apply button to open the form
        _click_apply_button(driver)
        _wait_for_page_and_forms(driver)

        filled = _fill_common_fields(driver, job)
        return filled > 0
    except Exception as e:
        logger.debug(f"Auto-fill attempt failed: {e}")
        return False


def _try_ai_autofill(driver, job: dict) -> bool:
    """Use AI to analyze page structure and intelligently fill forms."""
    from selenium.webdriver.common.by import By

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        # Collect form field info from the page
        form_fields = []
        inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, select")

        for el in inputs[:30]:
            try:
                if not el.is_displayed():
                    continue
                tag = el.tag_name
                el_type = el.get_attribute("type") or ""
                if el_type in ("hidden", "submit", "button"):
                    continue

                name = el.get_attribute("name") or ""
                el_id = el.get_attribute("id") or ""
                placeholder = el.get_attribute("placeholder") or ""
                label = _get_field_identifiers(el)
                required = el.get_attribute("required") is not None
                current_val = (el.get_attribute("value") or "").strip()

                # For select elements, get options
                options = []
                if tag == "select":
                    from selenium.webdriver.support.ui import Select
                    sel = Select(el)
                    options = [o.text for o in sel.options[:20]]

                form_fields.append({
                    "tag": tag, "type": el_type, "name": name,
                    "id": el_id, "placeholder": placeholder,
                    "label": label, "required": required,
                    "has_value": bool(current_val),
                    "options": options if options else None,
                })
            except Exception:
                continue

        if not form_fields:
            return False

        skills_text = ", ".join(
            skill for group in PROFILE.get("skills", {}).values() for skill in group
        )

        prompt = f"""You are filling out a job application form. Given the form fields and candidate profile, return a JSON object mapping field "name" or "id" to values to fill in.

CANDIDATE:
- Name: {PROFILE.get('name', '')}
- Email: {PROFILE.get('email', '')}
- Phone: {PROFILE.get('phone', '')}
- Location: {PROFILE.get('location', '')}
- Title: {PROFILE.get('title', '')}
- Experience: {PROFILE.get('years_of_experience', '')} years
- Skills: {skills_text}
- Summary: {PROFILE.get('summary', '')[:500]}

JOB: {job.get('title', '')} at {job.get('company', '')}

FORM FIELDS:
{json.dumps(form_fields, indent=2)}

Rules:
- Return ONLY a JSON object. Keys = field "name" or "id". Values = what to type/select.
- Skip fields with has_value=true, file uploads, checkboxes, radio buttons.
- For select fields, use one of the provided options text exactly.
- For screening questions, give honest professional answers.
- For "yes/no" or boolean-like questions about eligibility/authorization, answer positively if reasonable.
- Return ONLY the JSON, no other text."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.choices[0].message.content
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return False

        field_values = json.loads(json_match.group())
        filled = False

        for key, value in field_values.items():
            if not value:
                continue
            try:
                el = None
                for selector in (f"[name='{key}']", f"[id='{key}']",
                                 f"[data-testid='{key}']", f"[formcontrolname='{key}']"):
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, selector)
                        if el.is_displayed():
                            break
                        el = None
                    except Exception:
                        continue

                if not el:
                    continue

                # Handle select elements
                if el.tag_name == "select":
                    from selenium.webdriver.support.ui import Select
                    sel = Select(el)
                    try:
                        sel.select_by_visible_text(str(value))
                        filled = True
                    except Exception:
                        # Try partial match
                        for opt in sel.options:
                            if str(value).lower() in opt.text.lower():
                                sel.select_by_visible_text(opt.text)
                                filled = True
                                break
                else:
                    if _safe_fill(el, str(value)):
                        filled = True
            except Exception:
                continue

        return filled

    except Exception as e:
        logger.debug(f"AI auto-fill failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Main batch processor
# ---------------------------------------------------------------------------

def auto_apply_batch(jobs_with_letters: list[dict]) -> dict:
    """
    Auto-apply to a batch of jobs.
    Each item: {"id", "title", "company", "url", "cover_letter", "description"}
    """
    results = {
        "total": len(jobs_with_letters),
        "opened": 0,
        "auto_filled": 0,
        "failed": 0,
        "details": [],
    }

    if not jobs_with_letters:
        return results

    driver = _get_driver()

    if driver:
        try:
            for i, job in enumerate(jobs_with_letters):
                try:
                    url = job.get("url", "")
                    if not url:
                        results["failed"] += 1
                        results["details"].append({"id": job["id"], "status": "no_url"})
                        continue

                    logger.info(f"[{i+1}/{len(jobs_with_letters)}] Applying: {job.get('title')} at {job.get('company')}")

                    # Open job URL
                    if i == 0:
                        driver.get(url)
                    else:
                        driver.execute_script(f"window.open('{url}', '_blank');")
                        driver.switch_to.window(driver.window_handles[-1])

                    results["opened"] += 1

                    # Wait for page + forms to load
                    _wait_for_page_and_forms(driver)

                    # Try platform-specific auto-apply first
                    platform_filled = _try_platform_apply(driver, job)

                    if platform_filled:
                        results["auto_filled"] += 1
                        results["details"].append({
                            "id": job["id"], "status": "auto_filled",
                            "title": job["title"], "company": job["company"],
                        })
                        continue

                    # Try generic auto-fill (clicks Apply + fills forms)
                    filled = _try_autofill(driver, job)

                    # Try AI-powered form analysis if generic fill didn't work
                    if not filled and OPENAI_API_KEY:
                        filled = _try_ai_autofill(driver, job)

                    status = "auto_filled" if filled else "opened"
                    if filled:
                        results["auto_filled"] += 1

                    results["details"].append({
                        "id": job["id"], "status": status,
                        "title": job["title"], "company": job["company"],
                    })

                except Exception as e:
                    logger.warning(f"Error applying to job {job.get('id')}: {e}")
                    results["details"].append({
                        "id": job["id"], "status": "error", "error": str(e)
                    })

        except Exception as e:
            logger.error(f"Selenium batch error: {e}")
    else:
        # Fallback: just open URLs in default browser
        logger.warning("Selenium unavailable — falling back to webbrowser.open()")
        for job in jobs_with_letters:
            url = job.get("url", "")
            if url:
                webbrowser.open(url)
                results["opened"] += 1
                results["details"].append({
                    "id": job["id"], "status": "opened_browser",
                    "title": job["title"], "company": job["company"],
                })
                time.sleep(0.5)
            else:
                results["failed"] += 1
                results["details"].append({"id": job["id"], "status": "no_url"})

    return results


def generate_application_answers(job_description: str, questions: list[str]) -> list[str]:
    """Use OpenAI to generate answers for application screening questions."""
    if not OPENAI_API_KEY or not questions:
        return []

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        skills_text = ", ".join(
            skill for group in PROFILE["skills"].values() for skill in group
        )

        prompt = f"""Answer these job application screening questions based on the candidate profile.
Keep answers concise (1-3 sentences each), professional, and honest.

CANDIDATE:
- Name: {PROFILE['name']}
- Title: {PROFILE['title']}
- Experience: {PROFILE['years_of_experience']} years
- Skills: {skills_text}
- Location: {PROFILE['location']}

JOB DESCRIPTION (for context):
{job_description[:1500]}

QUESTIONS:
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(questions))}

Return answers as a JSON array of strings, one per question. Return ONLY the JSON array.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.choices[0].message.content
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        logger.warning(f"Failed to generate answers: {e}")

    return []
