"use strict";

const state = { catalog: null, mapData: null, map: null, mapLayer: null };
const outcomeColors = {
  confirmed: "#1f7a4d",
  probable: "#3b82a0",
  plausible: "#7b68a6",
  unverified: "#8a8f8b",
  contested: "#d1841d",
  misleading: "#b04b7a",
  refuted: "#a32924",
};

function byId(id) { return document.getElementById(id); }
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
function formatDate(value, options = {}) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: options.short ? "short" : "long",
    day: "2-digit",
    ...(options.time ? { hour: "2-digit", minute: "2-digit", timeZoneName: "short" } : {}),
  }).format(date);
}
function formatPeriod(period) {
  if (!period?.start || !period?.end) return "Unspecified period";
  return `${formatDate(period.start, { short: true })} — ${formatDate(period.end, { short: true })}`;
}
function label(value) {
  return String(value ?? "unknown").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
function safeUrl(value) {
  const url = String(value ?? "").trim();
  if (/^(https?:\/\/|\.\.?\/|\/|#)/i.test(url)) return url;
  return "#";
}
function renderInline(value) {
  let html = escapeHtml(value);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, text, url) => {
    const href = escapeHtml(safeUrl(url));
    const external = /^https?:\/\//i.test(url) ? ' target="_blank" rel="noopener noreferrer"' : "";
    return `<a href="${href}"${external}>${text}</a>`;
  });
  return html;
}
function renderMarkdown(markdown) {
  const lines = String(markdown ?? "").replaceAll("\r\n", "\n").split("\n");
  const output = [];
  let paragraph = [];
  let listType = null;
  let inCode = false;
  let code = [];
  const flushParagraph = () => {
    if (paragraph.length) output.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (listType) output.push(`</${listType}>`);
    listType = null;
  };
  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      flushParagraph();
      closeList();
      if (inCode) {
        output.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        code = [];
      }
      inCode = !inCode;
      continue;
    }
    if (inCode) { code.push(line); continue; }
    if (!line.trim()) { flushParagraph(); closeList(); continue; }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = Math.min(heading[1].length + 1, 5);
      output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) { closeList(); listType = nextType; output.push(`<${listType}>`); }
      output.push(`<li>${renderInline((unordered || ordered)[1])}</li>`);
      continue;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      closeList();
      output.push(`<blockquote>${renderInline(quote[1])}</blockquote>`);
      continue;
    }
    paragraph.push(line.trim());
  }
  if (inCode) output.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
  flushParagraph();
  closeList();
  return output.join("\n");
}
async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}
async function fetchText(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.text();
}
function reportTitle(report) {
  return `${label(report.report_type)} — ${formatDate(report.period?.start || report.as_of)}`;
}
function renderReportCard(report) {
  const searchText = [report.report_id, report.report_type, report.language, report.as_of, report.period?.start].join(" ").toLowerCase();
  return `<a class="report-card" href="#/report/${encodeURIComponent(report.report_id)}" data-language="${escapeHtml(report.language)}" data-type="${escapeHtml(report.report_type)}" data-search="${escapeHtml(searchText)}">
    <div><h3>${escapeHtml(reportTitle(report))}</h3><div class="report-card__meta">
      <span class="badge">${escapeHtml(report.language)}</span>
      <span>${escapeHtml(formatPeriod(report.period))}</span>
      <span>${report.claim_count} claims</span><span>${report.assessment_count} assessments</span>
    </div></div><span class="report-card__arrow" aria-hidden="true">→</span>
  </a>`;
}
function populateFilters() {
  for (const item of state.catalog.languages || []) {
    byId("language-filter").insertAdjacentHTML("beforeend", `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`);
  }
  for (const item of state.catalog.report_types || []) {
    byId("type-filter").insertAdjacentHTML("beforeend", `<option value="${escapeHtml(item)}">${escapeHtml(label(item))}</option>`);
  }
}
function renderArchive() {
  const reports = state.catalog.reports || [];
  const list = byId("report-list");
  if (!reports.length) {
    list.innerHTML = '<div class="panel empty-state"><strong>No approved reports are published yet.</strong><br>The archive will populate automatically after an approved report manifest and its Markdown content reach main.</div>';
    return;
  }
  list.innerHTML = reports.map(renderReportCard).join("");
  applyArchiveFilters();
}
function applyArchiveFilters() {
  const language = byId("language-filter").value;
  const type = byId("type-filter").value;
  const query = byId("report-search").value.trim().toLowerCase();
  let visible = 0;
  document.querySelectorAll(".report-card").forEach((card) => {
    const matches = (!language || card.dataset.language === language)
      && (!type || card.dataset.type === type)
      && (!query || card.dataset.search.includes(query));
    card.hidden = !matches;
    if (matches) visible += 1;
  });
  let empty = byId("filter-empty");
  if (!visible) {
    if (!empty) {
      empty = document.createElement("div");
      empty.id = "filter-empty";
      empty.className = "panel empty-state";
      empty.textContent = "No reports match the current filters.";
      byId("report-list").append(empty);
    }
  } else if (empty) empty.remove();
}
function renderLatest() {
  const target = byId("latest-report");
  const report = state.catalog.reports?.[0];
  if (!report) {
    target.className = "panel empty-state";
    target.innerHTML = "<strong>No approved report is published yet.</strong><br>The latest view will appear automatically after the first approved report build.";
    return;
  }
  target.className = "";
  target.innerHTML = renderReportCard(report);
}
async function renderReport(reportId) {
  const report = state.catalog.reports.find((item) => item.report_id === reportId);
  const body = byId("report-body");
  if (!report) {
    byId("report-title").textContent = "Report not found";
    byId("report-kicker").textContent = "Missing publication";
    byId("report-meta").innerHTML = "";
    body.className = "prose error-state";
    body.textContent = "This report is not present in the approved publication catalog.";
    return;
  }
  byId("report-kicker").textContent = `${label(report.report_type)} · ${report.language}`;
  byId("report-title").textContent = reportTitle(report);
  byId("report-meta").innerHTML = [
    `<span>${escapeHtml(formatPeriod(report.period))}</span>`,
    `<span>As of ${escapeHtml(formatDate(report.as_of, { time: true }))}</span>`,
    `<span>${report.claim_count} claims</span>`,
    `<span>${report.assessment_count} assessments</span>`,
    `<a href="${escapeHtml(report.manifest_url)}">Manifest JSON</a>`,
  ].join("");
  body.className = "prose loading-panel";
  body.textContent = "Loading report content…";
  try {
    const markdown = await fetchText(report.content_url);
    body.className = "prose";
    body.innerHTML = renderMarkdown(markdown);
  } catch (error) {
    body.className = "prose error-state";
    body.textContent = `Report content could not be loaded: ${error.message}`;
  }
}
function featureColor(feature) {
  return outcomeColors[feature.properties?.assessment_outcome] || "#59635e";
}
function popupHtml(feature) {
  const properties = feature.properties || {};
  const entries = [
    ["Type", label(properties.feature_type)],
    ["Assessment", label(properties.assessment_outcome)],
    ["Valid from", formatDate(properties.valid_from, { time: true })],
    ["Assessed", formatDate(properties.assessed_at, { time: true })],
    ["Precision", properties.precision_m ? `${properties.precision_m} m` : "Unknown"],
    ["Publication", label(properties.publication_status)],
    ["Claims", (properties.claim_ids || []).join(", ") || "None"],
  ];
  return `<div class="map-popup"><h3>${escapeHtml(feature.id)}</h3><dl>${entries.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl></div>`;
}
function filteredMapFeatures() {
  const type = byId("map-type-filter").value;
  const outcome = byId("map-outcome-filter").value;
  return (state.mapData?.features || []).filter((feature) => {
    const properties = feature.properties || {};
    return (!type || properties.feature_type === type) && (!outcome || properties.assessment_outcome === outcome);
  });
}
function populateMapFilters() {
  const features = state.mapData?.features || [];
  const types = [...new Set(features.map((item) => item.properties?.feature_type).filter(Boolean))].sort();
  const outcomes = [...new Set(features.map((item) => item.properties?.assessment_outcome).filter(Boolean))].sort();
  byId("map-type-filter").insertAdjacentHTML("beforeend", types.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(label(item))}</option>`).join(""));
  byId("map-outcome-filter").insertAdjacentHTML("beforeend", outcomes.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(label(item))}</option>`).join(""));
  byId("map-legend").innerHTML = outcomes.map((item) => `<div class="legend__item"><span class="legend__swatch" style="background:${escapeHtml(outcomeColors[item] || "#59635e")}"></span>${escapeHtml(label(item))}</div>`).join("");
}
function renderMapFallback(features, reason = "") {
  const fallback = byId("map-fallback");
  fallback.hidden = false;
  if (!features.length) {
    fallback.innerHTML = `<strong>No public map features match the current filters.</strong>${reason ? `<p>${escapeHtml(reason)}</p>` : ""}`;
    return;
  }
  fallback.innerHTML = `${reason ? `<p>${escapeHtml(reason)}</p>` : ""}<table><thead><tr><th>ID</th><th>Type</th><th>Assessment</th><th>Valid from</th></tr></thead><tbody>${features.map((feature) => `<tr><td>${escapeHtml(feature.id)}</td><td>${escapeHtml(label(feature.properties?.feature_type))}</td><td>${escapeHtml(label(feature.properties?.assessment_outcome))}</td><td>${escapeHtml(formatDate(feature.properties?.valid_from, { time: true }))}</td></tr>`).join("")}</tbody></table>`;
}
function updateMap() {
  const features = filteredMapFeatures();
  if (!window.L) {
    byId("map").hidden = true;
    renderMapFallback(features, "Interactive map library unavailable; showing the publication-safe feature table instead.");
    return;
  }
  byId("map-fallback").hidden = true;
  if (!state.map) {
    state.map = window.L.map("map", { preferCanvas: true }).setView([48.5, 31.2], 6);
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(state.map);
  }
  if (state.mapLayer) state.mapLayer.remove();
  state.mapLayer = window.L.geoJSON({ type: "FeatureCollection", features }, {
    style: (feature) => ({ color: featureColor(feature), weight: 3, fillColor: featureColor(feature), fillOpacity: 0.25 }),
    pointToLayer: (feature, latlng) => window.L.circleMarker(latlng, { radius: 7, color: featureColor(feature), fillColor: featureColor(feature), fillOpacity: 0.72, weight: 2 }),
    onEachFeature: (feature, layer) => layer.bindPopup(popupHtml(feature)),
  }).addTo(state.map);
  if (features.length) {
    const bounds = state.mapLayer.getBounds();
    if (bounds.isValid()) state.map.fitBounds(bounds.pad(0.12), { maxZoom: 11 });
  } else {
    state.map.setView([48.5, 31.2], 6);
    renderMapFallback([], "");
  }
  setTimeout(() => state.map.invalidateSize(), 0);
}
function renderMapSummary() {
  const snapshot = state.catalog.map;
  byId("map-summary").textContent = snapshot
    ? `${snapshot.snapshot_id} · as of ${formatDate(snapshot.as_of, { time: true })} · ${snapshot.feature_count} public features`
    : "No approved map snapshot is published yet.";
}
function route() {
  const raw = location.hash.replace(/^#\//, "") || "latest";
  const [name, encodedId] = raw.split("/");
  const routeName = name === "report" ? "report" : ["latest", "daily", "map", "about"].includes(name) ? name : "latest";
  document.querySelectorAll("[data-view]").forEach((view) => { view.hidden = view.dataset.view !== routeName; });
  document.querySelectorAll("[data-route]").forEach((link) => {
    if (link.dataset.route === routeName) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (routeName === "report") renderReport(decodeURIComponent(encodedId || ""));
  if (routeName === "map") updateMap();
  window.scrollTo({ top: 0, behavior: "instant" });
}
async function initialize() {
  try {
    state.catalog = await fetchJson("data/catalog.json");
    state.mapData = await fetchJson("data/map.geojson");
  } catch (error) {
    byId("page-summary").textContent = `Publication catalog failed to load: ${error.message}`;
    byId("latest-report").className = "panel error-state";
    byId("latest-report").textContent = "The static site build is incomplete or inaccessible.";
    return;
  }
  byId("stat-reports").textContent = state.catalog.counts?.reports ?? state.catalog.reports.length;
  byId("stat-features").textContent = state.catalog.counts?.map_features ?? state.mapData.features.length;
  byId("stat-built").textContent = formatDate(state.catalog.generated_at, { short: true });
  byId("page-summary").textContent = state.catalog.reports.length
    ? "Approved reports and publication-safe map snapshots, generated directly from versioned repository records."
    : "The publication shell is live. Approved reports and map snapshots will appear automatically when they reach the repository.";
  populateFilters();
  renderArchive();
  renderLatest();
  populateMapFilters();
  renderMapSummary();
  byId("language-filter").addEventListener("change", applyArchiveFilters);
  byId("type-filter").addEventListener("change", applyArchiveFilters);
  byId("report-search").addEventListener("input", applyArchiveFilters);
  byId("map-type-filter").addEventListener("change", updateMap);
  byId("map-outcome-filter").addEventListener("change", updateMap);
  window.addEventListener("hashchange", route);
  route();
}

document.addEventListener("DOMContentLoaded", initialize);
