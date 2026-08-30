"use strict";

const state = { catalog: null, dashboard: null, journey: null, currentCase: null };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const h = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");
const fmt = (value, digits = 3) => value == null ? "n/a" : Number(value).toFixed(digits);
const pct = (value, digits = 1) => value == null ? "n/a" : `${Number(value).toFixed(digits)}%`;

async function getJSON(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  window.setTimeout(() => element.classList.remove("show"), 3500);
}

function switchView(view) {
  $$(".view").forEach((element) => element.classList.toggle("active", element.id === `view-${view}`));
  $$(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  document.location.hash = view;
  window.scrollTo({ top: view === "product" ? 430 : 360, behavior: "smooth" });
}

function populateCatalog() {
  const trackSelect = $("#track-select");
  trackSelect.innerHTML = state.catalog.tracks.map((track) =>
    `<option value="${h(track.track_id)}">${h(track.label)}</option>`
  ).join("");
  trackSelect.value = state.catalog.default_track;
  populateCases();
}

function selectedTrack() {
  return state.catalog.tracks.find((track) => track.track_id === $("#track-select").value);
}

function populateCases() {
  const track = selectedTrack();
  const caseSelect = $("#case-select");
  caseSelect.innerHTML = track.cases.map((item) => {
    const summary = `${item.summary.slice(0, 60)}${item.summary.length > 60 ? "…" : ""}`;
    return `<option value="${h(item.case_id)}">${h(item.case_id)} · ${h(summary)}</option>`;
  }).join("");
  if (track.track_id === state.catalog.default_track) caseSelect.value = state.catalog.default_case;
}

async function loadCase() {
  const track = $("#track-select").value;
  const caseId = $("#case-select").value;
  $("#product-loading").classList.remove("hidden");
  $("#product-loading").textContent = "Loading retained artifacts…";
  $("#product-result").classList.add("hidden");
  try {
    state.currentCase = await getJSON(`/api/case?track=${encodeURIComponent(track)}&case_id=${encodeURIComponent(caseId)}`);
    renderCase(state.currentCase);
  } catch (error) {
    toast(error.message);
    $("#product-loading").textContent = `Unable to load case: ${error.message}`;
  }
}

function renderCase(data) {
  $("#product-loading").classList.add("hidden");
  $("#product-result").classList.remove("hidden");
  $("#case-id").textContent = `${data.case.case_id} · ${data.case.data_origin.replaceAll("_", " ")}`;
  $("#case-summary").textContent = data.case.context.summary;
  $("#case-facts").innerHTML = `
    <div><span>Candidates</span><strong>${data.case.candidate_count}</strong></div>
    <div><span>Shortlisted</span><strong>${data.shortlist.length}</strong></div>
    <div><span>Evidence snapshot</span><strong>${h(data.retrieval.snapshot_version)}</strong></div>
    <div><span>Mode</span><strong>Recorded replay</strong></div>`;

  $("#normalization-list").innerHTML = data.normalization.map((variant) => `
    <div class="normalization-row"><span>${h(variant.variant_id)}</span><code title="${h(variant.canonical_id)}">${h(variant.canonical_id)}</code></div>`
  ).join("");

  const evidenceCount = Object.values(data.retrieval.evidence_by_variant)
    .reduce((sum, records) => sum + records.length, 0);
  $("#evidence-summary").innerHTML = `<div class="snapshot-facts">
    <div><span>Records retrieved</span><strong>${evidenceCount}</strong></div>
    <div><span>Live dependency</span><strong>${data.retrieval.external_live_dependency ? "Yes" : "None"}</strong></div>
    <div><span>Snapshot date</span><strong>${h(data.retrieval.snapshot_date)}</strong></div>
    <div><span>SHA-256</span><strong title="${h(data.retrieval.snapshot_sha256)}">${h(data.retrieval.snapshot_sha256.slice(0, 12))}…</strong></div>
  </div>`;

  const uncertainty = $("#uncertainty-chip");
  uncertainty.className = `uncertainty-chip${data.uncertainty.escalated ? " warn" : ""}`;
  uncertainty.textContent = data.uncertainty.escalated ? "Uncertainty escalated" : "No escalation recorded";
  $("#shortlist").innerHTML = data.shortlist.length
    ? data.shortlist.map(renderVariantCard).join("")
    : `<div class="comparison-unavailable">No candidate was returned. This is an explicit abstention for expert review—not a negative diagnosis.</div>`;

  const usage = data.system.usage;
  const details = [
    ["System", data.system.system_version], ["Prompt", data.system.prompt_version],
    ["Model", data.system.model], ["Provider", data.system.provider || "recorded artifact"],
    ["Prompt SHA-256", data.system.prompt_sha256], ["Model calls", data.system.model_call_count],
    ["Call count source", data.system.model_call_count_source || "retained artifact"],
    ["Input tokens", usage.input_tokens], ["Output tokens", usage.output_tokens],
    ["Runtime", `${fmt(data.system.runtime_seconds, 3)}s`]
  ];
  $("#technical-content").innerHTML = details.map(([label, value]) =>
    `<div><span>${h(label)}</span><code title="${h(value)}">${h(value)}</code></div>`
  ).join("");
  $("#review-message").textContent = data.human_review_checkpoint;
  renderComparison(data.baseline_comparison, data.case.case_id);
}

function renderVariantCard(variant) {
  return `<article class="variant-card">
    <div class="variant-top">
      <span class="rank">${variant.rank}</span>
      <div><div class="variant-title"><strong>${h(variant.variant_id)}</strong>${variant.gene ? `<span class="gene-chip">${h(variant.gene)}</span>` : ""}</div><code class="canonical">${h(variant.normalized.canonical_id)}</code></div>
      <div class="confidence"><strong>${pct(variant.confidence * 100, 0)}</strong><span>confidence</span></div>
    </div>
    <div class="variant-body">
      <p class="variant-reason">${h(variant.reason)}</p>
      <div class="evidence-groups">
        ${renderEvidenceGroup("Supporting evidence", variant.supporting_evidence)}
        ${renderEvidenceGroup("Counterevidence", variant.counterevidence)}
        ${renderEvidenceGroup("Uncertainty", variant.uncertainty_evidence)}
      </div>
    </div>
  </article>`;
}

function renderEvidenceGroup(title, records) {
  if (!records.length) {
    return `<section class="evidence-group"><h5>${h(title)}</h5><span class="empty-evidence">None retrieved</span></section>`;
  }
  const items = records.map((record) => {
    const url = record.provenance.source_url;
    const link = typeof url === "string" && url.startsWith("https://")
      ? `<a class="provenance-link" href="${h(url)}" target="_blank" rel="noreferrer">Source provenance ↗</a>`
      : "";
    return `<div class="evidence-item">
      <div class="evidence-meta"><span class="evidence-id">${h(record.evidence_id)}</span><span class="evidence-pill">${h(record.strength)}</span><span class="evidence-pill">${h(record.category)}</span></div>
      <p>${h(record.statement)}</p>${link}
    </div>`;
  }).join("");
  return `<section class="evidence-group"><h5>${h(title)}</h5>${items}</section>`;
}

function renderComparison(comparison, caseId) {
  const element = $("#comparison-content");
  if (!comparison) {
    element.innerHTML = `<div class="comparison-unavailable"><strong>${h(caseId)}</strong><p>A retained V0 artifact is available only for frozen benchmark_v1 cases. V1 remains fully inspectable in Triage.</p></div>`;
    return;
  }
  const v1Ids = new Set(comparison.v1_ranked_variants.map((item) => item.variant_id));
  const renderList = (items, markRemoved = false) => items.length ? items.map((item) => `
    <div class="comparison-variant${markRemoved && !v1Ids.has(item.variant_id) ? " removed" : ""}"><strong>#${item.rank} ${h(item.variant_id)}</strong><span>${pct(item.confidence * 100, 0)} confidence</span></div>`
  ).join("") : `<div class="comparison-variant"><span>Explicit empty shortlist</span></div>`;
  element.innerHTML = `
    <article class="comparison-card v0"><p class="eyebrow">One general-purpose call</p><h3>V0 baseline</h3><p>${h(comparison.baseline_model)} · ${comparison.baseline_review_burden} review candidates</p><div class="comparison-list">${renderList(comparison.baseline_ranked_variants, true)}</div></article>
    <article class="comparison-card v1"><p class="eyebrow">Normalization + evidence grounding</p><h3>GenomeTriage V1</h3><p>Retained default · ${comparison.v1_review_burden} review candidates</p><div class="comparison-list">${renderList(comparison.v1_ranked_variants)}</div></article>
    <div class="comparison-summary"><div><strong>${comparison.baseline_review_burden} → ${comparison.v1_review_burden}</strong><span>case review burden</span></div><div><strong>${comparison.removed_by_v1.length}</strong><span>baseline candidates removed</span></div><div><strong>${h(comparison.removed_by_v1.join(", ") || "None")}</strong><span>removed candidate IDs</span></div></div>`;
}

function renderDashboard() {
  const dashboard = state.dashboard;
  const v0 = dashboard.systems.v0;
  const v1 = dashboard.systems.v1;
  $("#hero-fp").textContent = pct(dashboard.headline.false_positive_reduction_percent);
  $("#hero-burden").textContent = pct(dashboard.headline.review_burden_reduction_percent);
  $("#hero-recall").textContent = dashboard.headline.recall_at_3_preserved ? "100%" : "Not preserved";
  $("#hero-precision").textContent = `${pct(v0.shortlist_precision * 100)} → ${pct(v1.shortlist_precision * 100)}`;

  const rows = [
    ["Recall@3", v0.recall_at_3, v1.recall_at_3, 1],
    ["False positives", v0.false_positives, v1.false_positives, Math.max(v0.false_positives, v1.false_positives)],
    ["Review burden", v0.review_burden, v1.review_burden, Math.max(v0.review_burden, v1.review_burden)],
    ["Shortlist precision", v0.shortlist_precision, v1.shortlist_precision, 1]
  ];
  const metricRows = rows.map(([label, before, after, maximum]) => {
    const digits = label.includes("precision") || label.includes("Recall") ? 3 : 0;
    return `<div class="metric-row"><span>${h(label)}</span><progress value="${h(before)}" max="${h(maximum)}"></progress><b>${fmt(before, digits)}</b><progress class="v1-bar" value="${h(after)}" max="${h(maximum)}"></progress><b class="v1-value">${fmt(after, digits)}</b></div>`;
  }).join("");
  const conflict = dashboard.generalization.benchmark_conflict_v1;
  const publicTrack = dashboard.generalization.benchmark_public_v1;
  $("#dashboard-content").innerHTML = `
    <div class="headline-cards">
      <div class="headline-card"><strong>−${pct(dashboard.headline.false_positive_reduction_percent)}</strong><span>False positives · 9 → 2</span></div>
      <div class="headline-card"><strong>−${pct(dashboard.headline.review_burden_reduction_percent)}</strong><span>Review burden · 23 → 16</span></div>
      <div class="headline-card"><strong>${fmt(v1.recall_at_3, 3)}</strong><span>Recall@3 preserved</span></div>
      <div class="headline-card"><strong>+${pct(dashboard.headline.shortlist_precision_percentage_points)}</strong><span>Shortlist precision points</span></div>
    </div>
    <div class="metric-comparison"><h3>V0 baseline → retained V1</h3><div class="metric-row"><span></span><b>V0</b><span></span><b class="v1-value">V1</b></div>${metricRows}</div>
    <div class="control-card"><span class="control-icon">C</span><div><h4>V0-top3 control: prediction-identical</h4><p>False positives stayed at ${dashboard.systems.v0_top3_control.false_positives}; review burden stayed at ${dashboard.systems.v0_top3_control.review_burden}. Truncation explained ${dashboard.control.false_positive_reductions_explained_by_truncation}/${dashboard.control.total_v0_to_v1_false_positive_reduction} false-positive reductions.</p></div></div>
    <div class="generalization-grid">
      ${generalizationCard("Held-out conflict", conflict.v1, conflict.v3)}
      ${generalizationCard("Public ClinVar proxy", publicTrack.v1, publicTrack.v3)}
    </div>
    <div class="limitation"><strong>Interpretation boundary:</strong> The complete V1 pipeline produced the measured benchmark improvement. Retrieval alone was not isolated. Public labels are a deterministic ClinVar-metadata proxy, not clinical truth or clinical validation. ${h(dashboard.pricing_note)}</div>`;
}

function generalizationCard(title, v1, v3) {
  return `<article class="generalization-card"><span class="track-tag">Generalization track</span><h4>${h(title)}</h4><div class="mini-metrics"><div><strong>${fmt(v1.recall_at_3, 3)}</strong><span>V1 Recall@3</span></div><div><strong>${fmt(v1.shortlist_precision, 3)}</strong><span>V1 shortlist precision</span></div><div><strong>${v1.false_positives}</strong><span>V1 false positives</span></div></div><p class="microcopy">V3 experimental: ${v3.false_positives} false positives, Recall@3 ${fmt(v3.recall_at_3, 3)}. V3 is not the global default.</p></article>`;
}

function renderJourney() {
  $("#hot-take").textContent = `“${state.journey.hot_take}”`;
  $("#journey-content").innerHTML = state.journey.stages.map((stage) => {
    const decisionClass = stage.decision.includes("DEFAULT") ? "kept" : stage.decision.includes("EXPERIMENTAL") ? "experimental" : "";
    return `<article class="journey-item"><span class="journey-stage">${h(stage.stage)}</span><div><h3>${h(stage.title)}</h3><p>${h(stage.outcome)}</p></div><span class="decision-badge ${decisionClass}">${h(stage.decision)}</span></article>`;
  }).join("");
}

async function inspectInput() {
  const file = $("#input-file").files[0];
  const result = $("#inspection-result");
  if (!file) {
    result.innerHTML = `<div class="inspection-error">Choose a small VCF or structured JSON file first.</div>`;
    return;
  }
  if (file.size > 256 * 1024) {
    result.innerHTML = `<div class="inspection-error">File exceeds the 256 KiB demo limit.</div>`;
    return;
  }
  try {
    const content = await file.text();
    const payload = await getJSON("/api/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format: $("#input-format").value, content, genome_build: "GRCh38" })
    });
    const ids = payload.normalized_variants.map((item) => `<code>${h(item.canonical_id)}</code>`).join(" · ");
    result.innerHTML = `<div class="inspection-success"><strong>${payload.normalized_variants.length} variant(s) normalized.</strong> ${h(payload.message)}<br>${ids}</div>`;
  } catch (error) {
    result.innerHTML = `<div class="inspection-error"><strong>Input rejected safely.</strong> ${h(error.message)}</div>`;
  }
}

async function init() {
  try {
    [state.catalog, state.dashboard, state.journey] = await Promise.all([
      getJSON("/api/catalog"), getJSON("/api/dashboard"), getJSON("/api/journey")
    ]);
    populateCatalog();
    renderDashboard();
    renderJourney();
    await loadCase();
  } catch (error) {
    toast(`Application initialization failed: ${error.message}`);
  }
}

$$(".nav-button").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$("#hero-run").addEventListener("click", () => switchView("product"));
$("#track-select").addEventListener("change", () => { populateCases(); loadCase(); });
$("#case-select").addEventListener("change", loadCase);
$("#run-case").addEventListener("click", loadCase);
$("#inspect-input").addEventListener("click", inspectInput);
document.addEventListener("DOMContentLoaded", init);
