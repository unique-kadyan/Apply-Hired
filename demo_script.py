"""
Demo Automation Script for JobBot — Screen Recording Ready
===========================================================
Run this script while screen-recording to create a polished product demo video.

Usage:
    1. Start the Flask app:  python app.py
    2. Run the demo:         python demo_script.py

The script walks through every feature with smooth animations,
visual annotations (overlay banners), and realistic timing.
"""

import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:5000"
TYPING_DELAY = 0.06        # seconds between keystrokes (realistic typing)
STEP_PAUSE = 2.0           # pause between major steps
SHORT_PAUSE = 1.0           # pause between minor actions
SEARCH_TIMEOUT = 120        # max wait for search to finish (seconds)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_driver():
    """Create a Chrome driver sized for 1080p recording."""
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("detach", True)

    svc = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    # Set a clean 1920x1080 window for recording
    driver.set_window_size(1920, 1080)
    driver.set_window_position(0, 0)
    return driver


def slow_type(element, text, delay=None):
    """Type text character-by-character for a realistic demo look."""
    delay = delay or TYPING_DELAY
    element.click()
    for ch in text:
        element.send_keys(ch)
        time.sleep(delay)


def show_banner(driver, text, sub="", duration=3):
    """Show a full-width overlay banner at the top — great for section titles."""
    js = f"""
    (function() {{
        var old = document.getElementById('demo-banner');
        if (old) old.remove();

        var d = document.createElement('div');
        d.id = 'demo-banner';
        d.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; z-index: 99999;
            background: linear-gradient(135deg, #1e40af, #7c3aed);
            color: #fff; text-align: center;
            padding: 18px 24px; font-family: 'Segoe UI', system-ui, sans-serif;
            box-shadow: 0 4px 24px rgba(0,0,0,0.4);
            animation: bannerIn 0.4s ease;
        `;
        d.innerHTML = `
            <div style="font-size:22px;font-weight:700;letter-spacing:0.5px">{text}</div>
            <div style="font-size:14px;opacity:0.85;margin-top:4px">{sub}</div>
        `;

        var style = document.createElement('style');
        style.textContent = '@keyframes bannerIn {{ from {{ transform:translateY(-100%) }} to {{ transform:translateY(0) }} }}';
        d.appendChild(style);

        document.body.appendChild(d);
        setTimeout(function() {{
            d.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            d.style.opacity = '0';
            d.style.transform = 'translateY(-100%)';
            setTimeout(function() {{ d.remove(); }}, 600);
        }}, {int(duration * 1000)});
    }})();
    """
    driver.execute_script(js)
    time.sleep(0.3)


def highlight_element(driver, element, duration=1.5):
    """Draw a glowing border around an element to draw attention."""
    js = """
    var el = arguments[0];
    var dur = arguments[1];
    el.style.transition = 'box-shadow 0.3s ease';
    el.style.boxShadow = '0 0 0 3px #3b82f6, 0 0 20px rgba(59,130,246,0.5)';
    el.scrollIntoView({behavior: 'smooth', block: 'center'});
    setTimeout(function() { el.style.boxShadow = ''; }, dur * 1000);
    """
    driver.execute_script(js, element, duration)
    time.sleep(0.4)


def click_with_highlight(driver, element, pause=None):
    """Highlight an element, then click it."""
    pause = pause or SHORT_PAUSE
    highlight_element(driver, element)
    time.sleep(0.3)
    element.click()
    time.sleep(pause)


def wait_for(driver, xpath, timeout=10):
    """Wait for an element to be present and return it."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )


def wait_clickable(driver, xpath, timeout=10):
    """Wait for an element to be clickable and return it."""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )


def nav_to(driver, page_name):
    """Click a navbar button by text."""
    btn = wait_clickable(driver, f"//button[contains(text(), '{page_name}')]")
    btn.click()
    time.sleep(SHORT_PAUSE)


def step(msg):
    """Print a step to the console for the person running the demo."""
    print(f"\n  >>> {msg}")


# ---------------------------------------------------------------------------
# Demo Scenes
# ---------------------------------------------------------------------------

def scene_intro(driver):
    """Scene 1: Open the app, show dashboard overview."""
    step("SCENE 1 — Dashboard Overview")
    driver.get(BASE_URL)
    time.sleep(2)

    show_banner(driver,
                "JobBot — AI-Powered Job Application Automation",
                "Find, match, and apply to jobs in minutes", 4)
    time.sleep(4.5)

    show_banner(driver, "Dashboard",
                "Real-time stats on your job search progress", 3)
    time.sleep(3.5)

    # Highlight the stats cards
    try:
        cards = driver.find_elements(By.XPATH,
            "//div[contains(text(),'Total Jobs') or contains(text(),'New') "
            "or contains(text(),'Applied') or contains(text(),'Interview')]/..")
        for card in cards[:4]:
            highlight_element(driver, card, duration=1)
            time.sleep(0.6)
    except Exception:
        pass

    time.sleep(STEP_PAUSE)


def scene_profile(driver):
    """Scene 2: Show profile page."""
    step("SCENE 2 — Profile & Resume")
    nav_to(driver, "Profile")

    show_banner(driver, "Your Profile",
                "Auto-parsed from your resume — skills, experience, education", 3)
    time.sleep(3.5)

    # Scroll through profile sections
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'})")
    time.sleep(1.5)

    # Highlight skills section
    try:
        skills_section = driver.find_element(
            By.XPATH, "//div[contains(text(),'Technical Skills')]/..")
        highlight_element(driver, skills_section, 2)
        time.sleep(2)
    except Exception:
        pass

    # Scroll to experience
    driver.execute_script("window.scrollTo({top: 500, behavior: 'smooth'})")
    time.sleep(2)

    # Scroll to education
    driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
    time.sleep(2)

    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'})")
    time.sleep(STEP_PAUSE)


def scene_search(driver):
    """Scene 3: Configure and run a job search."""
    step("SCENE 3 — Smart Job Search")
    nav_to(driver, "Search")

    show_banner(driver, "Job Search",
                "Configure your ideal role — AI matches jobs to your profile", 3)
    time.sleep(3.5)

    # Type job title
    try:
        title_input = driver.find_element(
            By.XPATH, "//input[@placeholder*='Senior Backend Engineer' or @placeholder*='senior' or @placeholder*='Backend']")
        highlight_element(driver, title_input)
        title_input.clear()
        slow_type(title_input, "Senior Backend Engineer")
        time.sleep(SHORT_PAUSE)
    except Exception:
        step("  (skipped job title — input not found)")

    # Select Remote Worldwide
    try:
        remote_label = driver.find_element(
            By.XPATH, "//label[contains(text(),'Remote')]")
        click_with_highlight(driver, remote_label, 0.5)
    except Exception:
        pass

    # Select skills
    time.sleep(0.5)
    show_banner(driver, "Select Your Skills", "Pick technologies you're proficient in", 2.5)
    time.sleep(2.5)

    skills_to_click = ["Java", "Python", "Spring Boot", "PostgreSQL", "AWS", "Docker", "Kafka", "React"]
    for skill_name in skills_to_click:
        try:
            chip = driver.find_element(By.XPATH, f"//button[text()='{skill_name}']")
            chip.scrollIntoView = True
            driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", chip)
            time.sleep(0.3)
            click_with_highlight(driver, chip, 0.4)
        except Exception:
            pass

    time.sleep(SHORT_PAUSE)

    # Select experience level
    try:
        senior_chip = driver.find_element(By.XPATH, "//button[text()='Senior']")
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", senior_chip)
        time.sleep(0.5)
        click_with_highlight(driver, senior_chip, 0.5)
    except Exception:
        pass

    # Set salary slider
    try:
        salary_slider = driver.find_element(By.XPATH, "//input[@type='range' and @max='300000']")
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", salary_slider)
        time.sleep(0.5)
        highlight_element(driver, salary_slider)
        # Animate the slider
        for val in range(0, 100001, 10000):
            driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                salary_slider, val)
            time.sleep(0.05)
        time.sleep(0.5)
    except Exception:
        pass

    time.sleep(SHORT_PAUSE)

    # Click Start Search
    show_banner(driver, "Starting Search...",
                "Scanning RemoteOK, Remotive, WeWorkRemotely, and more", 3)

    try:
        search_btn = driver.find_element(
            By.XPATH, "//button[contains(text(),'Start Search') or contains(text(),'Searching')]")
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", search_btn)
        time.sleep(0.5)
        click_with_highlight(driver, search_btn, 1)
    except Exception:
        step("  (skipped search button — not found)")
        return

    # Wait for search to complete (poll the status)
    step("  Waiting for search to complete...")
    start = time.time()
    while time.time() - start < SEARCH_TIMEOUT:
        try:
            # Check for the "Done!" message or progress
            status_els = driver.find_elements(
                By.XPATH, "//*[contains(text(),'Done!') or contains(text(),'Found')]")
            for el in status_els:
                if "Done!" in el.text:
                    step(f"  Search complete: {el.text}")
                    time.sleep(STEP_PAUSE)
                    return
        except Exception:
            pass
        time.sleep(2)

    step("  Search timed out — continuing demo")
    time.sleep(SHORT_PAUSE)


def scene_jobs_list(driver):
    """Scene 4: Browse and filter jobs."""
    step("SCENE 4 — Browse & Filter Jobs")
    nav_to(driver, "Jobs")

    show_banner(driver, "Your Matched Jobs",
                "AI-scored and ranked by how well they fit your profile", 3)
    time.sleep(3.5)

    # Highlight filter bar
    try:
        selects = driver.find_elements(By.TAG_NAME, "select")
        if selects:
            highlight_element(driver, selects[0], 1.5)
            time.sleep(1)
    except Exception:
        pass

    # Demo: filter by score 50%+
    show_banner(driver, "Filter by Match Score", "Show only jobs with 50%+ match", 2.5)
    time.sleep(2)
    try:
        score_select = driver.find_elements(By.TAG_NAME, "select")[1]
        highlight_element(driver, score_select)
        score_select.click()
        time.sleep(0.5)
        # Select 50%+ option
        options = score_select.find_elements(By.TAG_NAME, "option")
        for opt in options:
            if "50" in opt.text:
                opt.click()
                break
        time.sleep(SHORT_PAUSE)
    except Exception:
        pass

    # Reset filters
    time.sleep(1)
    try:
        reset_btn = driver.find_element(By.XPATH, "//button[text()='Reset']")
        click_with_highlight(driver, reset_btn, 0.5)
    except Exception:
        pass

    time.sleep(SHORT_PAUSE)

    # Select a few jobs with checkboxes
    show_banner(driver, "Bulk Select Jobs",
                "Select up to 10 jobs to apply in one click", 2.5)
    time.sleep(2.5)
    try:
        checkboxes = driver.find_elements(
            By.XPATH, "//table/tbody//input[@type='checkbox']")
        for cb in checkboxes[:3]:
            driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", cb)
            time.sleep(0.3)
            click_with_highlight(driver, cb, 0.5)
        time.sleep(SHORT_PAUSE)
    except Exception:
        pass

    # Show the floating action bar
    show_banner(driver, "Bulk Actions",
                "Mark Applied or Auto-Apply to all selected jobs at once", 2.5)
    time.sleep(3)

    # Deselect (click Clear if available)
    try:
        clear_btn = driver.find_element(By.XPATH, "//button[text()='Clear']")
        click_with_highlight(driver, clear_btn, 0.5)
    except Exception:
        pass

    time.sleep(STEP_PAUSE)


def scene_job_detail(driver):
    """Scene 5: View a job detail, generate cover letter."""
    step("SCENE 5 — Job Detail & Cover Letter")

    # Click the first job title in the table
    try:
        first_job = driver.find_element(
            By.XPATH, "//table/tbody/tr[1]//a[contains(@style,'fontWeight')]"
            " | //table/tbody/tr[1]//span[contains(@style,'fontWeight')]"
            " | //table/tbody/tr[1]/td[3]")
        job_text = first_job.text
        click_with_highlight(driver, first_job, 1)
    except Exception:
        step("  (no jobs in table — skipping detail scene)")
        return

    time.sleep(SHORT_PAUSE)

    show_banner(driver, "Job Detail",
                f"AI-powered match analysis for: {job_text[:50]}", 3)
    time.sleep(3.5)

    # Scroll through the detail page
    driver.execute_script("window.scrollTo({top: 300, behavior: 'smooth'})")
    time.sleep(1.5)

    # Highlight match score section
    try:
        score_section = driver.find_element(
            By.XPATH, "//div[contains(text(),'Match Analysis') or contains(text(),'Score')]/..")
        highlight_element(driver, score_section, 2)
        time.sleep(2)
    except Exception:
        pass

    # Generate cover letter
    show_banner(driver, "AI Cover Letter Generation",
                "Tailored cover letter generated for this specific role", 2.5)
    time.sleep(2.5)

    try:
        gen_btn = driver.find_element(
            By.XPATH, "//button[contains(text(),'Generate') or contains(text(),'Regenerate')]")
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", gen_btn)
        time.sleep(0.5)
        click_with_highlight(driver, gen_btn, 1)

        # Wait for cover letter to appear
        step("  Generating cover letter...")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[text()='Copy' or contains(text(),'Regenerate')]")
                )
            )
            time.sleep(1)

            # Scroll to show the letter
            driver.execute_script(
                "window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
            time.sleep(2)

            show_banner(driver, "Cover Letter Ready!",
                        "Personalized and ready to send", 2.5)
            time.sleep(3)
        except Exception:
            step("  Cover letter generation timed out")
    except Exception:
        pass

    # Update status to "saved"
    try:
        status_select = driver.find_element(
            By.XPATH, "//select[.//option[text()='saved'] or .//option[text()='new']]")
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", status_select)
        highlight_element(driver, status_select)
        from selenium.webdriver.support.ui import Select
        sel = Select(status_select)
        sel.select_by_value("saved")
        time.sleep(0.5)

        update_btn = driver.find_element(By.XPATH, "//button[text()='Update']")
        click_with_highlight(driver, update_btn, 1)
    except Exception:
        pass

    time.sleep(STEP_PAUSE)

    # Go back to jobs
    try:
        back_btn = driver.find_element(
            By.XPATH, "//button[contains(text(),'Back')] | //a[contains(text(),'Back')]")
        click_with_highlight(driver, back_btn, 1)
    except Exception:
        nav_to(driver, "Jobs")


def scene_auto_apply(driver):
    """Scene 6: Demonstrate the auto-apply flow."""
    step("SCENE 6 — Auto-Apply Demo")
    nav_to(driver, "Jobs")
    time.sleep(SHORT_PAUSE)

    show_banner(driver, "One-Click Auto-Apply",
                "Selenium opens each job page, fills forms, and uploads your resume", 3.5)
    time.sleep(4)

    # Select first 2 jobs
    try:
        checkboxes = driver.find_elements(
            By.XPATH, "//table/tbody//input[@type='checkbox']")
        for cb in checkboxes[:2]:
            click_with_highlight(driver, cb, 0.4)

        time.sleep(SHORT_PAUSE)

        # Highlight the Auto-Apply button
        auto_btn = driver.find_element(
            By.XPATH, "//button[contains(text(),'Auto-Apply')]")
        highlight_element(driver, auto_btn, 2)
        time.sleep(2)

        show_banner(driver, "Auto-Apply in Action",
                    "Opens job pages, detects form fields, fills your info, uploads resume", 3)
        time.sleep(3)

        # NOTE: We don't actually click Auto-Apply in the demo to avoid
        # opening external pages. Uncomment the line below for a live demo:
        # click_with_highlight(driver, auto_btn, 2)

        # Deselect
        try:
            clear_btn = driver.find_element(By.XPATH, "//button[text()='Clear']")
            click_with_highlight(driver, clear_btn, 0.5)
        except Exception:
            pass

    except Exception:
        step("  (no jobs to select for auto-apply)")

    time.sleep(STEP_PAUSE)


def scene_outro(driver):
    """Scene 7: Final outro with feature summary."""
    step("SCENE 7 — Outro")
    nav_to(driver, "Dashboard")
    time.sleep(1)

    # Show feature summary overlay
    js = """
    (function() {
        var overlay = document.createElement('div');
        overlay.id = 'demo-overlay';
        overlay.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            z-index: 99999; display: flex; align-items: center; justify-content: center;
            background: rgba(15, 23, 42, 0.92);
            animation: fadeIn 0.6s ease;
        `;
        overlay.innerHTML = `
            <div style="text-align:center;color:#fff;font-family:'Segoe UI',system-ui,sans-serif;max-width:700px;padding:40px">
                <div style="font-size:48px;font-weight:800;
                    background:linear-gradient(135deg,#3b82f6,#a855f7);
                    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                    margin-bottom:24px">
                    JobBot
                </div>
                <div style="font-size:20px;color:#94a3b8;margin-bottom:40px">
                    AI-Powered Job Application Automation
                </div>

                <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;text-align:left;margin-bottom:40px">
                    <div style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:12px;padding:16px">
                        <div style="font-size:18px;font-weight:600;margin-bottom:4px">Smart Search</div>
                        <div style="font-size:13px;color:#94a3b8">Scans 10+ job boards simultaneously</div>
                    </div>
                    <div style="background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.3);border-radius:12px;padding:16px">
                        <div style="font-size:18px;font-weight:600;margin-bottom:4px">AI Matching</div>
                        <div style="font-size:13px;color:#94a3b8">Scores every job against your profile</div>
                    </div>
                    <div style="background:rgba(5,150,105,0.1);border:1px solid rgba(5,150,105,0.3);border-radius:12px;padding:16px">
                        <div style="font-size:18px;font-weight:600;margin-bottom:4px">Auto-Apply</div>
                        <div style="font-size:13px;color:#94a3b8">Fills forms & uploads resume automatically</div>
                    </div>
                    <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:12px;padding:16px">
                        <div style="font-size:18px;font-weight:600;margin-bottom:4px">Cover Letters</div>
                        <div style="font-size:13px;color:#94a3b8">AI-generated, tailored to each role</div>
                    </div>
                </div>

                <div style="font-size:14px;color:#64748b;margin-top:20px">
                    Built with Python, Flask, React, Selenium & OpenAI
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    })();
    """
    driver.execute_script(js)
    time.sleep(8)

    # Fade out the overlay
    driver.execute_script("""
        var overlay = document.getElementById('demo-overlay');
        if (overlay) {
            overlay.style.transition = 'opacity 1s ease';
            overlay.style.opacity = '0';
            setTimeout(function() { overlay.remove(); }, 1200);
        }
    """)
    time.sleep(2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  JobBot — Demo Automation Script")
    print("  Start screen recording, then press Enter...")
    print("=" * 60)
    input()

    driver = create_driver()

    try:
        scene_intro(driver)
        scene_profile(driver)
        scene_search(driver)
        scene_jobs_list(driver)
        scene_job_detail(driver)
        scene_auto_apply(driver)
        scene_outro(driver)

        print("\n" + "=" * 60)
        print("  Demo complete! Stop your screen recording.")
        print("  The browser window will stay open.")
        print("=" * 60 + "\n")

    except KeyboardInterrupt:
        print("\n  Demo interrupted by user.")
    except Exception as e:
        print(f"\n  Demo error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
