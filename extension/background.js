// Background service worker — handles API calls to JobBot server

const DEFAULT_SERVER = "https://apply-hired.onrender.com";

async function getServerUrl() {
  const data = await chrome.storage.sync.get("serverUrl");
  return data.serverUrl || DEFAULT_SERVER;
}

async function getSessionCookie() {
  const data = await chrome.storage.sync.get("sessionCookie");
  return data.sessionCookie || "";
}

// Fetch autofill data from JobBot API
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "getAutofillData") {
    (async () => {
      try {
        const server = await getServerUrl();
        const cookie = await getSessionCookie();
        const resp = await fetch(`${server}/api/profile/autofill-data`, {
          credentials: "include",
          headers: cookie ? { Cookie: cookie } : {},
        });
        if (!resp.ok) {
          sendResponse({ error: "Not logged in. Open JobBot and sign in first." });
          return;
        }
        const data = await resp.json();
        sendResponse({ data });
      } catch (e) {
        sendResponse({ error: e.message });
      }
    })();
    return true; // async response
  }

  if (msg.action === "markApplied") {
    (async () => {
      try {
        const server = await getServerUrl();
        const cookie = await getSessionCookie();
        const resp = await fetch(`${server}/api/jobs/${msg.jobId}/status`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            ...(cookie ? { Cookie: cookie } : {}),
          },
          body: JSON.stringify({ status: "applied" }),
        });
        const data = await resp.json();
        sendResponse({ success: resp.ok, data });
      } catch (e) {
        sendResponse({ error: e.message });
      }
    })();
    return true;
  }
});
