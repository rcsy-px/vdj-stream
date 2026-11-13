"use strict";
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="control-token"]').content;
const skippedUpdateKey = "vdj-companion-skipped-update";
let appUpdate = null, updating = false, checking = false, stopped = false, startedAt = null;
let healthTimer, updateTimer, clockTimer;
let diagnosing = false;
const storage = {
  get() { try { return localStorage.getItem(skippedUpdateKey); } catch { return null; } },
  set(value) { try { localStorage.setItem(skippedUpdateKey, value); } catch {} },
  clear() { try { localStorage.removeItem(skippedUpdateKey); } catch {} }
};
function showWelcomeOnce() {
  const welcome = $("welcome");
  const seenKey = "vdj-companion-welcome-seen";
  $("welcome-close").addEventListener("click", () => welcome.close());
  $("welcome-continue").addEventListener("click", () => welcome.close());
  $("welcome-kofi").addEventListener("click", () => welcome.close());
  welcome.addEventListener("close", () => $("check-updates").focus({preventScroll: true}));
  try {
    if (localStorage.getItem(seenKey)) return;
    // Remember the first display, not just dismissal; reloads must not repeat it.
    localStorage.setItem(seenKey, "1");
  } catch {
    // If persistence is blocked, skip the welcome instead of nagging on every visit.
    return;
  }
  welcome.showModal();
}
async function api(path, options = {}) {
  const response = await fetch(path, {cache: "no-store", ...options});
  if (!response.ok) {
    let reason = `Request failed (HTTP ${response.status}).`;
    try { const body = await response.json(); if (typeof body.detail === "string") reason = body.detail; } catch {}
    throw new Error(reason);
  }
  return response.json();
}
function badge(id, text, state = "") { $(id).textContent = text; $(id).className = `badge ${state}`; }
function ready(id, state, text = state ? "Ready" : "Missing") {
  $(id).textContent = text; $(id).className = `readiness ${state ? "ok" : "bad"}`;
}
function uptime() {
  if (!startedAt || stopped) return;
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - startedAt));
  const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60);
  $("uptime").textContent = `${hours ? hours + "h " : ""}${minutes}m ${String(seconds % 60).padStart(2, "0")}s`;
}
async function health() {
  try {
    const result = await api("/api/health");
    if (stopped) return;
    startedAt = result.startedAt; uptime();
    for (const id of ["hero-version", "current-version", "footer-version"]) $(id).textContent = result.version;
    ready("backend-ready", true);
    ready("ytdlp-ready", result.tools.ytDlp);
    ready("ffmpeg-ready", result.tools.ffmpeg);
    ready("chromium-ready", result.tools.chromium);
    $("connection").textContent = result.ok ? "Backend online · ready for VirtualDJ" : "Backend online · setup incomplete";
    $("connection-led").className = "led online";
  } catch {
    ready("backend-ready", false, "Offline");
    $("connection").textContent = "Backend offline · open the launcher";
    $("connection-led").className = "led offline";
  }
}
function renderApp(update) {
  appUpdate = update;
  $("latest-version").textContent = update.latestVersion || "Unavailable";
  $("app-actions").hidden = true;
  $("restore-update").hidden = true;
  $("update-panel").classList.remove("available");
  if (update.error) {
    badge("app-badge", "CHECK FAILED", "error");
    $("update-status").textContent = update.errorDetail || update.error;
  } else if (update.updateAvailable) {
    const skipped = storage.get() === update.latestVersion;
    badge("app-badge", skipped ? "SKIPPED" : "UPDATE AVAILABLE", "warn");
    $("update-status").textContent = skipped ? `Version ${update.latestVersion} skipped. You can show it again below.` : `Version ${update.latestVersion} is available. Open the release page to download and install it.`;
    $("restore-update").hidden = !skipped;
    $("app-actions").hidden = skipped || !update.releaseUrl;
    if (update.releaseUrl) $("view-update").href = update.releaseUrl;
    $("update-panel").classList.toggle("available", !skipped);
  } else {
    badge("app-badge", "UP TO DATE", "good");
    $("update-status").textContent = "You have the latest published release.";
  }
}
function renderEngine(update) {
  const busy = updating || update.updating;
  $("ytdlp-current").textContent = update.currentVersion || (busy ? "Updating…" : "Unavailable");
  $("tool-version").textContent = update.currentVersion || (busy ? "Updating…" : "Version unavailable");
  $("ytdlp-latest").textContent = update.latestVersion || "Unavailable";
  $("update-ytdlp").hidden = !update.updateAvailable && !busy;
  $("update-ytdlp").disabled = busy || diagnosing || stopped;
  $("update-ytdlp").textContent = busy ? "Updating…" : "↧ Update yt-dlp";
  $("ytdlp-panel").classList.toggle("available", !!update.updateAvailable || busy);
  if (busy) {
    badge("ytdlp-badge", "UPDATING", "warn");
    $("ytdlp-status").textContent = "Installing the latest stable engine. Please wait…";
  } else if (update.error || update.lastUpdateError) {
    badge("ytdlp-badge", "CHECK REQUIRED", "error");
    $("ytdlp-status").textContent = update.lastUpdateError || update.errorDetail || update.error;
  } else if (update.updateAvailable) {
    badge("ytdlp-badge", "UPDATE AVAILABLE", "warn");
    $("ytdlp-status").textContent = "A newer engine is available. Update before loading your next track.";
  } else {
    badge("ytdlp-badge", "UP TO DATE", "good");
    $("ytdlp-status").textContent = update.message || "The latest stable engine is installed.";
  }
}
async function checkUpdates(force = false) {
  if (checking || updating || stopped) return;
  checking = true; $("check-updates").disabled = true; $("check-updates").textContent = "Checking…";
  const suffix = force ? "?refresh=true" : "";
  await Promise.all([
    api(`/api/update${suffix}`).then(renderApp).catch(error => renderApp({error: error.message})),
    api(`/api/ytdlp${suffix}`).then(renderEngine).catch(error => renderEngine({error: error.message}))
  ]);
  checking = false; $("check-updates").disabled = stopped; $("check-updates").textContent = "↻ Check again";
}
$("check-updates").addEventListener("click", () => checkUpdates(true));
$("skip-update").addEventListener("click", () => { if (appUpdate) { storage.set(appUpdate.latestVersion); renderApp(appUpdate); } });
$("restore-update").addEventListener("click", () => { storage.clear(); if (appUpdate) renderApp(appUpdate); });
$("update-ytdlp").addEventListener("click", async () => {
  if (updating || diagnosing || stopped) return;
  updating = true;
  $("update-ytdlp").disabled = true; $("update-ytdlp").textContent = "Updating…";
  $("check-updates").disabled = true; $("shutdown").disabled = true;
  $("run-diagnostics").disabled = true;
  badge("ytdlp-badge", "UPDATING", "warn");
  $("ytdlp-status").textContent = "Downloading and installing the official stable release. This may take a few minutes…";
  try {
    const result = await api("/api/ytdlp/update", {method: "POST", headers: {"X-Shutdown-Token": token}});
    updating = false; renderEngine(result);
  } catch (error) {
    updating = false;
    badge("ytdlp-badge", "UPDATE FAILED", "error");
    $("ytdlp-status").textContent = error.message;
    $("update-ytdlp").textContent = "↻ Retry update";
    $("update-ytdlp").disabled = false;
  } finally {
    $("check-updates").disabled = false; $("shutdown").disabled = false;
    $("run-diagnostics").disabled = false;
    health();
  }
});
$("run-diagnostics").addEventListener("click", async () => {
  if (diagnosing || updating || stopped) return;
  diagnosing = true;
  $("run-diagnostics").disabled = true;
  $("run-diagnostics").textContent = "Checking…";
  $("update-ytdlp").disabled = true;
  $("diagnostic-results").textContent = "Checking the engine, both search providers and audio delivery…";
  try {
    const result = await api("/api/diagnostics", {method: "POST", headers: {"X-Shutdown-Token": token}});
    $("diagnostic-results").replaceChildren();
    for (const check of result.checks) {
      const row = document.createElement("p");
      const label = document.createElement("strong");
      label.className = check.ok ? "diagnostic-ok" : "diagnostic-error";
      label.textContent = `${check.ok ? "✓" : "!"} ${check.name}: `;
      row.append(label, document.createTextNode(check.message));
      $("diagnostic-results").append(row);
    }
  } catch (error) { $("diagnostic-results").textContent = error.message; }
  finally {
    diagnosing = false;
    $("run-diagnostics").disabled = stopped;
    $("run-diagnostics").textContent = "Run checks";
    $("update-ytdlp").disabled = stopped || updating;
  }
});
const events = new EventSource("/api/logs/stream");
let logLines = [];
events.onopen = () => { $("log-status").textContent = "● CONNECTED"; };
events.onmessage = event => {
  const logs = $("logs"), atEnd = logs.scrollHeight - logs.scrollTop - logs.clientHeight < 30;
  logLines.push(event.data); logLines = logLines.slice(-300);
  logs.textContent = logLines.join("\n");
  if (atEnd) logs.scrollTop = logs.scrollHeight;
};
events.onerror = () => { $("log-status").textContent = stopped ? "DISCONNECTED" : "RECONNECTING…"; };
$("shutdown").addEventListener("click", async () => {
  if (!confirm("Shut down the VDJ Companion backend? VirtualDJ searches and streams will stop.")) return;
  $("shutdown").disabled = true;
  try {
    await api("/api/shutdown", {method: "POST", headers: {"X-Shutdown-Token": token}});
    stopped = true; events.close();
    clearInterval(healthTimer); clearInterval(updateTimer); clearInterval(clockTimer);
    $("message").textContent = "Backend stopped. Open the launcher to reconnect.";
    $("connection").textContent = "Backend stopped"; $("connection-led").className = "led offline";
    $("log-status").textContent = "DISCONNECTED"; ready("backend-ready", false, "Stopped");
    $("check-updates").disabled = true; $("update-ytdlp").disabled = true;
    $("run-diagnostics").disabled = true;
  } catch (error) { $("message").textContent = error.message; $("shutdown").disabled = false; }
});
health(); checkUpdates();
showWelcomeOnce();
healthTimer = setInterval(health, 15000);
updateTimer = setInterval(() => checkUpdates(), 60000);
clockTimer = setInterval(uptime, 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden && !stopped) { health(); checkUpdates(); } });
