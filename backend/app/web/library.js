"use strict";
(() => {
  const el = id => document.getElementById(id);
  const token = document.querySelector('meta[name="control-token"]').content;
  let busy = false;
  function formatBytes(bytes) {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = Math.max(0, bytes || 0), unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
    return `${value.toLocaleString(undefined, {maximumFractionDigits: unit ? 2 : 0})} ${units[unit]}`;
  }
  async function request(url, body) {
    const response = await fetch(url, {cache: "no-store", ...(body !== undefined ? {
      method: "POST", headers: {"X-Shutdown-Token": token, "Content-Type": "application/json"}, body: JSON.stringify(body)
    } : {})});
    if (!response.ok) { const error = await response.json(); throw new Error(error.detail || "Library request failed"); }
    return response.json();
  }
  function button(label, action) {
    const node = document.createElement("button"); node.type = "button"; node.textContent = label;
    node.addEventListener("click", () => perform(action)); return node;
  }
  async function perform(action) {
    if (busy) return;
    busy = true; el("library-message").textContent = "Working…";
    try { await action(); el("library-message").textContent = "Saved. Reopen the folder in VirtualDJ to refresh it."; await refresh(); }
    catch (error) { el("library-message").textContent = error.message; }
    finally { busy = false; }
  }
  const trackAction = (track, action) => request(`/api/library/tracks/${encodeURIComponent(track)}/${action}`, {});
  function row(title, detail, buttons) {
    const container = document.createElement("div"); container.className = "library-row";
    const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = title;
    const description = document.createElement("p"); description.className = "hint"; description.textContent = detail;
    copy.append(name, description); const actions = document.createElement("div"); actions.className = "library-actions";
    actions.append(...buttons); container.append(copy, actions); return container;
  }
  function fill(id, rows) {
    el(id).replaceChildren(...rows);
    if (!rows.length) { const note = document.createElement("p"); note.className = "hint"; note.textContent = "No tracks yet."; el(id).append(note); }
  }
  async function refresh() {
    const state = await request("/api/library");
    if (!el("playback-mode").disabled && !el("playback-mode").matches(":focus")) el("playback-mode").value = state.playbackMode;
    el("active-setlist").replaceChildren(...state.lists.map(list => {
      const option = document.createElement("option"); option.value = list.id; option.textContent = list.name; return option;
    }));
    el("active-setlist").value = state.active;
    el("delete-setlist").disabled = state.active === "default";
    el("export-setlist").href = `/api/library/setlists/${state.active}/export`;
    el("library-storage").textContent = `${formatBytes(state.usedBytes)} used`;
    el("library-free-space").textContent = `Unlimited storage · ${formatBytes(state.freeBytes)} free on disk`;
    const tracks = await request(`/api/library/folders/set-${state.active}`);
    fill("setlist-tracks", tracks.map(t => row(t.title, `${t.artist}${t.video ? " · Video" : ""}`, [
      button("Download audio", () => trackAction(t.id, "audio")), button("Download video", () => trackAction(t.id, "video")),
      button("Remove from setlist", () => trackAction(t.id, "remove"))])));
    fill("download-tracks", state.downloads.map(t => {
      const actions = [];
      if (["queued", "downloading"].includes(t.state)) actions.push(button("Cancel", () => trackAction(t.track, "cancel")));
      else if (t.state !== "ready") actions.push(button("Retry", () => trackAction(t.track, t.track.startsWith("video:") ? "video" : "audio")));
      actions.push(button("Add to setlist", () => trackAction(t.track, "add")));
      actions.push(button("Remove download", async () => {
        if (confirm("Remove the saved file? Unload this track from VirtualDJ first. Your setlists will be kept.")) await trackAction(t.track, "delete");
      }));
      return row(t.title, `${t.track.startsWith("video:") ? "Video" : "Audio"} · ${t.state}${t.error ? " · " + t.error : ""}`, actions);
    }));
    fill("history-tracks", state.history.map(t => row(t.title, t.artist, [button("Add to setlist", () => trackAction(t.id, "add"))])));
  }
  el("active-setlist").addEventListener("change", () => perform(() => request(`/api/library/setlists/${el("active-setlist").value}/activate`, {})));
  el("playback-mode").addEventListener("change", async () => {
    const select = el("playback-mode");
    select.disabled = true;
    try {
      await request("/api/library/playback", {mode: select.value});
      el("library-message").textContent = "Playback preference saved. Search again or reopen Last search in VirtualDJ.";
    } catch (error) {
      el("library-message").textContent = error.message;
      try { select.value = (await request("/api/library")).playbackMode; } catch (_) { /* Keep the error visible if offline. */ }
    } finally { select.disabled = false; }
  });
  el("delete-setlist").addEventListener("click", () => {
    if (confirm("Delete this setlist? Downloaded files will be kept.")) perform(() => request(`/api/library/setlists/${el("active-setlist").value}/delete`, {}));
  });
  el("new-setlist").addEventListener("submit", event => {
    event.preventDefault(); perform(async () => { await request("/api/library/setlists", {name: el("setlist-name").value}); el("setlist-name").value = ""; });
  });
  el("library-refresh").addEventListener("click", () => perform(() => request("/api/library/history/refresh", {})));
  el("open-download-folder").addEventListener("click", async () => {
    const opener = el("open-download-folder");
    opener.disabled = true;
    try {
      await request("/api/library/open-download-folder", {});
      el("library-message").textContent = "Download folder opened on this computer.";
    } catch (error) { el("library-message").textContent = error.message; }
    finally { opener.disabled = false; }
  });
  refresh().catch(error => { el("library-message").textContent = error.message; });
  setInterval(() => { if (!busy && !document.hidden && !el("active-setlist").matches(":focus")) refresh().catch(() => {}); }, 5000);
})();
