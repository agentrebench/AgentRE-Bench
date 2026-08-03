(function () {
  const config = window.AgentREChallengeConfig || {};
  let leaderboard = window.AgentREChallengeLeaderboard || { summary: {}, entries: [] };

  function getConfig(path) {
    return path.split(".").reduce((value, key) => {
      if (value && Object.prototype.hasOwnProperty.call(value, key)) {
        return value[key];
      }
      return "";
    }, config);
  }

  function setText(selector, text) {
    document.querySelectorAll(selector).forEach((node) => {
      node.textContent = text;
    });
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function safeUrl(value) {
    if (!value) return "";
    try {
      const url = new URL(value, window.location.origin);
      if (url.protocol === "https:" && url.hostname === "github.com") return url.href;
    } catch (error) {
      return "";
    }
    return "";
  }

  function statusLabel() {
    const status = config.competitionStatus || "upcoming";
    return (config.statusLabels && config.statusLabels[status]) || status;
  }

  function populateConfigValues() {
    document.querySelectorAll("[data-config]").forEach((node) => {
      const value = getConfig(node.dataset.config);
      node.textContent = value;
    });

    document.querySelectorAll("[data-config-href]").forEach((node) => {
      const value = getConfig(node.dataset.configHref);
      if (value) node.setAttribute("href", value);
    });

    setText("[data-status-label]", statusLabel());
    const organizerUsername = config.organizerGithubUsername || "agentrebench";
    setText("[data-organizer-username]", organizerUsername);
    setText("[data-organizer-handle]", "@" + organizerUsername);
    document.documentElement.dataset.challengeStatus = config.competitionStatus || "upcoming";
  }

  function renderTimeline() {
    const timeline = document.querySelector("[data-render='timeline']");
    if (!timeline || !Array.isArray(config.timeline)) return;

    timeline.innerHTML = config.timeline.map((item) => {
      const date = Array.isArray(item.dateKeys)
        ? item.dateKeys.map((key) => config.dates && config.dates[key]).filter(Boolean).join(" | ")
        : item.dateKey && config.dates ? config.dates[item.dateKey] : "";
      return `
        <article class="timeline-item">
          <div class="timeline-label">${escapeHtml(item.label)}</div>
          <div>
            <h3>${escapeHtml(item.title)}</h3>
            <p class="timeline-date">${escapeHtml(date)}</p>
            <p>${escapeHtml(item.description)}</p>
          </div>
        </article>
      `;
    }).join("");
  }

  function renderScoring() {
    const scoring = document.querySelector("[data-render='scoring']");
    if (!scoring || !Array.isArray(config.scoringWeights)) return;

    scoring.innerHTML = config.scoringWeights.map((item) => `
      <article class="score-card">
        <div class="score-weight">${escapeHtml(item.weight)}%</div>
        <h3>${escapeHtml(item.name)}</h3>
        <p>${escapeHtml(item.description)}</p>
      </article>
    `).join("");
  }

  function renderAllowedTools() {
    const toolLists = document.querySelectorAll("[data-render=\"allowed-tools\"]");
    const tools = config.officialToolEnvironment && Array.isArray(config.officialToolEnvironment.allowedTools)
      ? config.officialToolEnvironment.allowedTools
      : [];
    if (!toolLists.length || !tools.length) return;

    toolLists.forEach((toolList) => {
      toolList.innerHTML = tools.map((tool) => `
        <article class="card compact-card">
          <h3><code>${escapeHtml(tool.name)}</code></h3>
          <p>${escapeHtml(tool.description)}</p>
        </article>
      `).join("");
    });
  }

  function renderDisallowedTools() {
    const lists = document.querySelectorAll("[data-render=\"disallowed-tools\"]");
    const items = config.officialToolEnvironment && Array.isArray(config.officialToolEnvironment.disallowedTools)
      ? config.officialToolEnvironment.disallowedTools
      : [];
    if (!lists.length || !items.length) return;

    lists.forEach((list) => {
      list.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    });
  }

  function renderModelPanel() {
    const panel = document.querySelector("[data-render=\"model-panel\"]");
    if (!panel || !Array.isArray(config.officialModelPanel)) return;

    panel.innerHTML = config.officialModelPanel.map((model) => `
      <article class="card compact-card">
        <h3>${escapeHtml(model)}</h3>
        <p>Official Season 1 panel member</p>
      </article>
    `).join("");
  }

  function renderScoreMetrics() {
    const metrics = document.querySelector("[data-render=\"score-metrics\"]");
    if (!metrics || !Array.isArray(config.scoreReportingMetrics)) return;

    metrics.innerHTML = config.scoreReportingMetrics.map((metric) => `
      <li>${escapeHtml(metric)}</li>
    `).join("");
  }

  function renderTieBreakers() {
    const tieBreakers = document.querySelector("[data-render=\"tie-breaks\"]");
    if (!tieBreakers || !Array.isArray(config.tieBreakOrder)) return;

    tieBreakers.innerHTML = config.tieBreakOrder.map((item) => `
      <li>${escapeHtml(item)}</li>
    `).join("");
  }

  function renderJsonTemplates() {
    const submissionTemplate = document.querySelector("[data-render=\"submission-json-template\"]");
    if (submissionTemplate) {
      submissionTemplate.textContent = JSON.stringify({
        github_handle: "example-user",
        challenge_title: "Example Challenge",
        architecture: "linux-x86_64",
        binary_path: "challenge.elf",
        final_tag: config.finalSubmissionTag || "agentre-season-1-final",
        final_commit_sha: "RESOLVED_FULL_40_CHARACTER_COMMIT_SHA",
        binary_sha256: "SHA256_OF_BINARY",
        public_handle: true,
        public_title: true
      }, null, 2);
    }

    const registrationTemplate = document.querySelector("[data-render=\"registration-json-template\"]");
    if (registrationTemplate) {
      registrationTemplate.textContent = JSON.stringify({
        entry_id: "PENDING",
        github_handle: "@example-user",
        challenge_title: "Withheld until judging",
        public_handle: true,
        public_title: false,
        private_repository_name: config.privateRepositoryName || "agentre-challenge-entry",
        entrant_submission_number: 1,
        final_tag: config.finalSubmissionTag || "agentre-season-1-final",
        final_commit_sha: "RESOLVED_FULL_40_CHARACTER_COMMIT_SHA",
        binary_sha256: "SHA256_OF_BINARY",
        registration_status: "Registered",
        validation_status: "Pending",
        evaluation_status: "Pending",
        repo_private_confirmed: true,
        organizer_invited: true,
        required_files_confirmed: true,
        rules_read: true,
        age_18_or_older_confirmed: true,
        us_eligibility_confirmed: true,
        free_entry_confirmed: true,
        designated_prize_recipient_confirmed: true,
        original_work_or_rights_confirmed: true,
        no_private_urls_or_artifacts_in_pr: true
      }, null, 2);
    }
  }

  function statusMatches(entry, field, status) {
    return String(entry[field] || "").toLowerCase() === status;
  }

  function deriveSummary(entries) {
    return {
      registered: entries.length,
      validated: entries.filter((entry) => statusMatches(entry, "validation_status", "validated")).length,
      evaluated: entries.filter((entry) => {
        const status = String(entry.evaluation_status || "").toLowerCase();
        return status.includes("complete") || entry.rank !== null && entry.rank !== undefined;
      }).length
    };
  }

  function normalizedEntries() {
    const entries = Array.isArray(leaderboard.entries) ? leaderboard.entries : [];
    return entries.map((entry, index) => Object.assign({
      entry_id: "PENDING-" + String(index + 1).padStart(3, "0"),
      challenge_title: "Withheld until judging",
      registration_status: "Registered",
      validation_status: "Pending",
      evaluation_status: "Pending",
      models_tested: null,
      average_model_correctness: null,
      median_model_correctness: null,
      model_panel_wins: null,
      models_below_passing_threshold: null,
      complete_failures: null,
      difficulty_score: null,
      rank: null,
      award: null,
      public_summary: null,
      public_repository_url: null
    }, entry || {}));
  }

  function renderSummary() {
    const entries = normalizedEntries();
    const summary = entries.length ? deriveSummary(entries) : (leaderboard.summary || {});
    setText("[data-summary='registered']", String(summary.registered || 0));
    setText("[data-summary='validated']", String(summary.validated || 0));
    setText("[data-summary='evaluated']", String(summary.evaluated || 0));
  }

  function hasFinalResults(entry) {
    return entry.rank !== null && entry.rank !== undefined ||
      entry.difficulty_score !== null && entry.difficulty_score !== undefined ||
      entry.average_model_correctness !== null && entry.average_model_correctness !== undefined ||
      entry.median_model_correctness !== null && entry.median_model_correctness !== undefined ||
      entry.model_panel_wins !== null && entry.model_panel_wins !== undefined ||
      entry.models_tested !== null && entry.models_tested !== undefined ||
      entry.models_below_passing_threshold !== null && entry.models_below_passing_threshold !== undefined ||
      entry.complete_failures !== null && entry.complete_failures !== undefined ||
      Boolean(entry.award || entry.public_summary || entry.public_repository_url);
  }

  function creatorName(entry) {
    if (entry.public_handle === false) return "Withheld";
    return entry.github_handle || "Withheld";
  }

  function challengeTitle(entry) {
    if (entry.public_title === false) return "Withheld until judging";
    return entry.challenge_title || "Withheld until judging";
  }

  function optionalValue(value) {
    if (value === null || value === undefined || value === "") return "Pending";
    return String(value);
  }

  function renderResultCells(entry, showFinalColumns) {
    if (!showFinalColumns) return "";
    const repoUrl = safeUrl(entry.public_repository_url);
    const repoLink = repoUrl
      ? `<a href="${escapeHtml(repoUrl)}">Approved repo</a>`
      : "Not published";
    return `
      <td>${escapeHtml(optionalValue(entry.rank))}</td>
      <td>${escapeHtml(optionalValue(entry.models_tested))}</td>
      <td>${escapeHtml(optionalValue(entry.average_model_correctness))}</td>
      <td>${escapeHtml(optionalValue(entry.median_model_correctness))}</td>
      <td>${escapeHtml(optionalValue(entry.model_panel_wins))}</td>
      <td>${escapeHtml(optionalValue(entry.difficulty_score))}</td>
      <td>${escapeHtml(optionalValue(entry.models_below_passing_threshold))}</td>
      <td>${escapeHtml(optionalValue(entry.complete_failures))}</td>
      <td>${escapeHtml(optionalValue(entry.award))}</td>
      <td>${escapeHtml(optionalValue(entry.public_summary))}</td>
      <td>${repoLink}</td>
    `;
  }

  function renderLeaderboard() {
    const table = document.querySelector("[data-render='leaderboard-table']");
    const cards = document.querySelector("[data-render='leaderboard-cards']");
    const empty = document.querySelector("[data-empty-state]");
    const locked = document.querySelector("[data-locked-state]");
    if (!table || !cards) return;

    const entries = normalizedEntries();
    const status = config.competitionStatus || "upcoming";
    const showLocked = status === "validation" || status === "judging";
    const showFinalColumns = status === "complete" || status === "archived" || entries.some(hasFinalResults);

    if (locked) locked.hidden = !showLocked;
    if (empty) empty.hidden = entries.length !== 0;

    const finalHeaders = showFinalColumns
      ? "<th>Rank</th><th>Models Tested</th><th>Avg Correctness</th><th>Median Correctness</th><th>Panel Wins</th><th>Difficulty Score</th><th>Models Below Pass</th><th>Complete Failures</th><th>Award</th><th>Summary</th><th>Public Repo</th>"
      : "";

    table.innerHTML = `
      <thead>
        <tr>
          <th>Entry ID</th>
          <th>Creator</th>
          <th>Challenge Title</th>
          <th>Registration</th>
          <th>Validation</th>
          <th>Evaluation</th>
          ${finalHeaders}
        </tr>
      </thead>
      <tbody>
        ${entries.map((entry) => `
          <tr>
            <td class="mono">${escapeHtml(entry.entry_id)}</td>
            <td>${escapeHtml(creatorName(entry))}</td>
            <td>${escapeHtml(challengeTitle(entry))}</td>
            <td>${escapeHtml(optionalValue(entry.registration_status))}</td>
            <td>${escapeHtml(optionalValue(entry.validation_status))}</td>
            <td>${escapeHtml(optionalValue(entry.evaluation_status))}</td>
            ${renderResultCells(entry, showFinalColumns)}
          </tr>
        `).join("")}
      </tbody>
    `;

    cards.innerHTML = entries.map((entry) => {
      const finalFields = showFinalColumns ? `
        <dl>
          <div><dt>Rank</dt><dd>${escapeHtml(optionalValue(entry.rank))}</dd></div>
          <div><dt>Models tested</dt><dd>${escapeHtml(optionalValue(entry.models_tested))}</dd></div>
          <div><dt>Avg correctness</dt><dd>${escapeHtml(optionalValue(entry.average_model_correctness))}</dd></div>
          <div><dt>Median correctness</dt><dd>${escapeHtml(optionalValue(entry.median_model_correctness))}</dd></div>
          <div><dt>Panel wins</dt><dd>${escapeHtml(optionalValue(entry.model_panel_wins))}</dd></div>
          <div><dt>Difficulty score</dt><dd>${escapeHtml(optionalValue(entry.difficulty_score))}</dd></div>
          <div><dt>Models below pass</dt><dd>${escapeHtml(optionalValue(entry.models_below_passing_threshold))}</dd></div>
          <div><dt>Complete failures</dt><dd>${escapeHtml(optionalValue(entry.complete_failures))}</dd></div>
          <div><dt>Award</dt><dd>${escapeHtml(optionalValue(entry.award))}</dd></div>
        </dl>
        <p>${escapeHtml(optionalValue(entry.public_summary))}</p>
        ${safeUrl(entry.public_repository_url) ? `<a href="${escapeHtml(safeUrl(entry.public_repository_url))}">Approved public repository</a>` : ""}
      ` : "";

      return `
        <article class="leaderboard-card">
          <div class="leaderboard-card-top">
            <span class="mono">${escapeHtml(entry.entry_id)}</span>
            <span>${escapeHtml(optionalValue(entry.evaluation_status))}</span>
          </div>
          <h3>${escapeHtml(challengeTitle(entry))}</h3>
          <p>${escapeHtml(creatorName(entry))}</p>
          <dl>
            <div><dt>Registration</dt><dd>${escapeHtml(optionalValue(entry.registration_status))}</dd></div>
            <div><dt>Validation</dt><dd>${escapeHtml(optionalValue(entry.validation_status))}</dd></div>
            <div><dt>Evaluation</dt><dd>${escapeHtml(optionalValue(entry.evaluation_status))}</dd></div>
          </dl>
          ${finalFields}
        </article>
      `;
    }).join("");
  }

  function registrationFileUrl(manifestUrl, file) {
    try {
      return new URL(file, new URL(manifestUrl, window.location.origin)).href;
    } catch (error) {
      return "";
    }
  }

  async function loadRegistrationManifest() {
    if (!config.registrationManifestUrl) return;
    try {
      const manifestUrl = new URL(config.registrationManifestUrl, window.location.origin).href;
      const manifestResponse = await fetch(manifestUrl, { headers: { "Accept": "application/json" } });
      if (!manifestResponse.ok) throw new Error("Registration manifest request failed");
      const manifest = await manifestResponse.json();
      const files = Array.isArray(manifest.files) ? manifest.files : [];
      const loadedEntries = await Promise.all(files.map(async (file) => {
        const url = registrationFileUrl(manifestUrl, file);
        if (!url) return null;
        const response = await fetch(url, { headers: { "Accept": "application/json" } });
        if (!response.ok) throw new Error("Registration file request failed: " + file);
        return response.json();
      }));
      leaderboard = {
        summary: deriveSummary(loadedEntries.filter(Boolean)),
        entries: loadedEntries.filter(Boolean)
      };
      renderSummary();
      renderLeaderboard();
    } catch (error) {
      console.warn("AgentRE registration manifest unavailable; using static fallback.", error);
    }
  }

  function initThemeToggle() {
    const themeToggle = document.querySelector(".theme-toggle");
    if (!themeToggle) return;

    const themeStorageKey = "agentre-theme-v2";
    const savedTheme = localStorage.getItem(themeStorageKey) || "light";
    document.documentElement.dataset.theme = savedTheme;
    themeToggle.textContent = savedTheme === "dark" ? "Light" : "Dark";

    themeToggle.addEventListener("click", () => {
      const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = nextTheme;
      localStorage.setItem(themeStorageKey, nextTheme);
      themeToggle.textContent = nextTheme === "dark" ? "Light" : "Dark";
    });
  }

  function init() {
    initThemeToggle();
    populateConfigValues();
    renderTimeline();
    renderScoring();
    renderAllowedTools();
    renderDisallowedTools();
    renderModelPanel();
    renderScoreMetrics();
    renderTieBreakers();
    renderJsonTemplates();
    renderSummary();
    renderLeaderboard();
    loadRegistrationManifest();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
