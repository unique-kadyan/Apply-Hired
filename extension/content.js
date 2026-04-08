// Content script — auto-fills job application forms on any page

let profileData = null;

// Listen for fill command from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "fillForm") {
    profileData = msg.data;
    fillAllFields();
    sendResponse({ filled: true });
  }
  if (msg.action === "submitForm") {
    clickSubmitButton();
    sendResponse({ submitted: true });
  }
});

function fillAllFields() {
  if (!profileData) return;

  const fieldMap = [
    { keys: ["first_name", "firstname", "first name", "given name", "fname"], value: profileData.first_name },
    { keys: ["last_name", "lastname", "last name", "surname", "family name", "lname"], value: profileData.last_name },
    { keys: ["full_name", "fullname", "your name", "candidate name", "applicant name"], value: profileData.full_name },
    { keys: ["name"], value: profileData.full_name },
    { keys: ["email", "e-mail", "email address"], value: profileData.email },
    { keys: ["phone", "mobile", "telephone", "contact number", "phone number"], value: profileData.phone },
    { keys: ["city", "town"], value: profileData.city },
    { keys: ["location", "address", "current location"], value: profileData.location },
    { keys: ["linkedin", "linked in", "linkedin url", "linkedin profile"], value: profileData.linkedin },
    { keys: ["github", "github url", "github profile"], value: profileData.github },
    { keys: ["website", "portfolio", "personal site", "personal website", "url"], value: profileData.website },
    { keys: ["years of experience", "years experience", "total experience", "experience year", "yrs"], value: profileData.years_of_experience },
    { keys: ["current company", "employer", "company name", "current employer"], value: "" },
    { keys: ["current title", "job title", "current role", "headline", "current position", "designation"], value: profileData.title },
    { keys: ["salary", "expected salary", "desired salary", "compensation", "ctc", "expected ctc"], value: "" },
    { keys: ["notice period", "notice", "availability"], value: "Immediate / 15 days" },
  ];

  // Fill input fields
  const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]):not([type="file"])');
  inputs.forEach(inp => {
    if (!inp.offsetParent) return; // skip hidden
    const identifiers = getIdentifiers(inp);
    for (const mapping of fieldMap) {
      if (mapping.value && mapping.keys.some(k => identifiers.includes(k))) {
        if (!inp.value.trim()) {
          setFieldValue(inp, mapping.value);
        }
        break;
      }
    }
  });

  // Fill textareas with cover letter or summary
  const textareas = document.querySelectorAll("textarea");
  textareas.forEach(ta => {
    if (!ta.offsetParent) return;
    const identifiers = getIdentifiers(ta);
    const isCoverLetter = ["cover", "letter", "message", "note", "why", "about", "motivation", "additional", "summary", "intro"]
      .some(kw => identifiers.includes(kw));
    if (isCoverLetter && !ta.value.trim()) {
      const text = profileData.cover_letter || profileData.summary || "";
      if (text) setFieldValue(ta, text);
    }
  });

  showNotification("JobBot: Form filled! Review and submit.");
}

function getIdentifiers(el) {
  return [
    el.getAttribute("name") || "",
    el.getAttribute("id") || "",
    el.getAttribute("placeholder") || "",
    el.getAttribute("aria-label") || "",
    el.getAttribute("autocomplete") || "",
    el.getAttribute("data-testid") || "",
    el.getAttribute("formcontrolname") || "",
    getLabelText(el),
  ].join(" ").toLowerCase();
}

function getLabelText(el) {
  // Check for associated label
  const id = el.getAttribute("id");
  if (id) {
    const label = document.querySelector(`label[for="${id}"]`);
    if (label) return label.textContent || "";
  }
  // Check parent label
  const parentLabel = el.closest("label");
  if (parentLabel) return parentLabel.textContent || "";
  return "";
}

function setFieldValue(el, value) {
  // Set value and trigger React/Angular change events
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, "value"
  )?.set || Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, "value"
  )?.set;

  if (nativeInputValueSetter) {
    nativeInputValueSetter.call(el, value);
  } else {
    el.value = value;
  }

  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur", { bubbles: true }));
}

function clickSubmitButton() {
  // Try common submit button selectors
  const selectors = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button[data-testid*="submit"]',
    'button[aria-label*="submit"]',
  ];

  for (const sel of selectors) {
    const btn = document.querySelector(sel);
    if (btn && btn.offsetParent) {
      btn.click();
      showNotification("JobBot: Application submitted!");
      // Notify extension to mark as applied
      chrome.runtime.sendMessage({ action: "formSubmitted", url: window.location.href });
      return;
    }
  }

  // Fallback: find button with submit-like text
  const buttons = document.querySelectorAll("button, a[role='button']");
  for (const btn of buttons) {
    const text = (btn.textContent || "").trim().toLowerCase();
    if (["submit", "apply", "submit application", "apply now", "send application"]
        .some(t => text === t || text.startsWith(t))) {
      if (btn.offsetParent) {
        btn.click();
        showNotification("JobBot: Application submitted!");
        chrome.runtime.sendMessage({ action: "formSubmitted", url: window.location.href });
        return;
      }
    }
  }

  showNotification("JobBot: No submit button found. Please submit manually.");
}

function showNotification(text) {
  const existing = document.getElementById("jobbot-notify");
  if (existing) existing.remove();

  const div = document.createElement("div");
  div.id = "jobbot-notify";
  div.style.cssText = `
    position: fixed; bottom: 20px; right: 20px; z-index: 999999;
    background: #1e293b; color: #e2e8f0; padding: 12px 20px;
    border-radius: 10px; font-family: system-ui, sans-serif;
    font-size: 14px; box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    border: 1px solid #334155; animation: fadeIn 0.3s ease;
  `;
  div.textContent = text;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 5000);
}
