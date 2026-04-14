const DEFAULT_SERVER = "https://apply-hired.onrender.com";

let autofillData = null;

document.addEventListener("DOMContentLoaded", async () => {
  const statusEl = document.getElementById("status");
  const userInfoEl = document.getElementById("userInfo");
  const loginEl = document.getElementById("loginSection");
  const actionEl = document.getElementById("actionSection");
  const messageEl = document.getElementById("message");

  // Load saved server URL
  const stored = await chrome.storage.sync.get(["serverUrl"]);
  const serverUrl = stored.serverUrl || DEFAULT_SERVER;
  document.getElementById("serverUrl").value = serverUrl;

  // Try to fetch profile
  try {
    const resp = await fetch(`${serverUrl}/api/profile/autofill-data`, {
      credentials: "include",
    });

    if (resp.ok) {
      autofillData = await resp.json();
      statusEl.textContent = "Connected";
      statusEl.style.color = "#6ee7b7";
      userInfoEl.style.display = "block";
      document.getElementById("userName").textContent = autofillData.full_name || "User";
      document.getElementById("userEmail").textContent = autofillData.email || "";
      actionEl.style.display = "block";
    } else {
      statusEl.textContent = "Not signed in";
      statusEl.style.color = "#fca5a5";
      loginEl.style.display = "block";
    }
  } catch (e) {
    statusEl.textContent = "Cannot reach server";
    statusEl.style.color = "#fca5a5";
    loginEl.style.display = "block";
  }

  // Connect button
  document.getElementById("connectBtn").addEventListener("click", async () => {
    const url = document.getElementById("serverUrl").value.trim().replace(/\/$/, "");
    await chrome.storage.sync.set({ serverUrl: url });

    // Open Kalibr in new tab to sign in
    chrome.tabs.create({ url: url });
    messageEl.textContent = "Sign in to Kalibr, then click the extension again.";
  });

  // Fill button
  document.getElementById("fillBtn").addEventListener("click", async () => {
    if (!autofillData) return;
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    chrome.tabs.sendMessage(tab.id, { action: "fillForm", data: autofillData });
    messageEl.textContent = "Form filled! Review and submit.";
    messageEl.style.color = "#6ee7b7";
  });

  // Fill & Submit button
  document.getElementById("submitBtn").addEventListener("click", async () => {
    if (!autofillData) return;
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // Fill first
    chrome.tabs.sendMessage(tab.id, { action: "fillForm", data: autofillData }, () => {
      // Then submit after a short delay
      setTimeout(() => {
        chrome.tabs.sendMessage(tab.id, { action: "submitForm" });
        messageEl.textContent = "Submitted! The job will be marked as applied.";
        messageEl.style.color = "#6ee7b7";
      }, 1500);
    });
  });

  // Disconnect
  document.getElementById("disconnectBtn").addEventListener("click", async () => {
    await chrome.storage.sync.remove(["serverUrl", "sessionCookie"]);
    statusEl.textContent = "Disconnected";
    actionEl.style.display = "none";
    userInfoEl.style.display = "none";
    loginEl.style.display = "block";
  });
});
