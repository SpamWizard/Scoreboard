(() => {
  const rowsEl = document.getElementById("rows");
  const emptyEl = document.getElementById("empty");
  const statusEl = document.getElementById("status-line");
  const starsEl = document.getElementById("stars");
  const POLL_MS = 3000;
  let lastFingerprint = "";

  // Build starfield once — never on poll refresh
  if (starsEl) {
    const count = Math.min(120, Math.floor((window.innerWidth * window.innerHeight) / 14000));
    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
      const star = document.createElement("span");
      star.className = "star" + (Math.random() > 0.82 ? " bright" : "");
      star.style.left = `${Math.random() * 100}%`;
      star.style.top = `${Math.random() * 100}%`;
      star.style.setProperty("--dur", `${3 + Math.random() * 5}s`);
      star.style.setProperty("--delay", `${Math.random() * 6}s`);
      frag.appendChild(star);
    }
    starsEl.appendChild(frag);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function formatScore(score) {
    const n = Number(score);
    if (Number.isInteger(n)) return String(n);
    return n.toFixed(1).replace(/\.0$/, "");
  }

  function fingerprint(board) {
    return JSON.stringify(
      (board.entries || []).map((e) => [
        e.rank,
        e.team,
        e.score,
        e.roster_names,
      ])
    );
  }

  function render(board) {
    const fp = fingerprint(board);
    if (fp === lastFingerprint) return;
    lastFingerprint = fp;

    const entries = board.entries || [];
    if (!entries.length) {
      rowsEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
    } else {
      emptyEl.classList.add("hidden");
      rowsEl.innerHTML = entries
        .map((entry) => {
          const roster = (entry.roster_names || []).filter(Boolean).join(" · ");
          return `
            <li class="row">
              <div class="rank">${escapeHtml(entry.rank)}</div>
              <div>
                <p class="team-name">${escapeHtml(entry.team)}</p>
                <p class="roster">${escapeHtml(roster)}</p>
              </div>
              <div class="score">${escapeHtml(formatScore(entry.score))}</div>
            </li>
          `;
        })
        .join("");
    }
  }

  async function refresh() {
    try {
      const res = await fetch("/api/v1/leaderboard", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const board = await res.json();
      render(board);
      statusEl.textContent = "FLIGHT CHECK COMPLETE";
    } catch (err) {
      statusEl.textContent = "SIGNAL LOST — retrying";
      console.error(err);
    }
  }

  refresh();
  setInterval(refresh, POLL_MS);
})();
