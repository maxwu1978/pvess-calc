const form = document.querySelector("#project-form");
const button = document.querySelector("#generate");
const preflightButton = document.querySelector("#preflight");
const statusEl = document.querySelector("#status");
const bomEmpty = document.querySelector("#bom-empty");
const bomTable = document.querySelector("#bom-table");
const bomBody = document.querySelector("#bom-table tbody");
const costTotals = document.querySelector("#cost-totals");
const quoteCards = document.querySelector("#quote-cards");
const categoryCosts = document.querySelector("#category-costs");
const filesEmpty = document.querySelector("#files-empty");
const fileList = document.querySelector("#file-list");
const fileFilter = document.querySelector("#file-filter");
const fileCount = document.querySelector("#file-count");
const deliveryEmpty = document.querySelector("#delivery-empty");
const deliveryPackage = document.querySelector("#delivery-package");
const sourceEmpty = document.querySelector("#source-empty");
const sourceMaterials = document.querySelector("#source-materials");
const readinessEmpty = document.querySelector("#readiness-empty");
const readinessPanel = document.querySelector("#readiness-panel");
const previewEmpty = document.querySelector("#preview-empty");
const previewPanel = document.querySelector("#preview-panel");
const errorEmpty = document.querySelector("#error-empty");
const errorPanel = document.querySelector("#error-panel");
const preflightEmpty = document.querySelector("#preflight-empty");
const preflightPanel = document.querySelector("#preflight-panel");
const summaryStrip = document.querySelector("#summary-strip");
const validationPanel = document.querySelector("#validation-panel");
const progressBar = document.querySelector("#progress-bar");
const progressMessage = document.querySelector("#progress-message");
const historyEmpty = document.querySelector("#history-empty");
const historyList = document.querySelector("#history-list");
const accessTokenInput = document.querySelector("#access-token");
const saveTokenButton = document.querySelector("#save-token");
const tokenStatus = document.querySelector("#token-status");
const lookupButton = document.querySelector("#lookup-address");
const lookupMode = document.querySelector("#lookup-mode");
const lookupPanel = document.querySelector("#lookup-panel");
const addressSample = document.querySelector("#address-sample");

const projectTemplate = document.querySelector("#project-template");
const moduleChoice = document.querySelector("#module-choice");
const moduleBrandDisplay = document.querySelector("#module-brand-display");
const moduleModelDisplay = document.querySelector("#module-model-display");
const moduleWattsDisplay = document.querySelector("#module-watts-display");
const inverterChoice = document.querySelector("#inverter-choice");
const inverterModelDisplay = document.querySelector("#inverter-model-display");
const inverterAmpsInput = document.querySelector('input[name="inverter_ac_output_a"]');
const batteryChoice = document.querySelector("#battery-choice");
const batteryKwhDisplay = document.querySelector("#battery-kwh-display");
const batteryModelDisplay = document.querySelector("#battery-model-display");
const batteryQtyInput = document.querySelector('input[name="battery_quantity"]');

let activePoll = null;
let currentFiles = [];
let currentPreviewItems = [];

const numberFields = new Set([
  "modules",
  "strings",
  "inverter_quantity",
  "inverter_ac_output_a",
  "inverter_ac_output_v",
  "battery_quantity",
  "distance_to_doorway_ft",
  "distance_to_window_ft",
  "distance_to_egress_ft",
  "main_panel_a",
  "busbar_a",
  "self_consumption_fraction",
  "pv_turnkey_usd_per_w",
  "inverter_cost_usd_total",
  "battery_cost_usd_total",
  "roof_pitch_deg",
  "roof_azimuth_deg",
  "roof_width_ft",
  "roof_height_ft",
  "roof_info_height_ft",
  "decking_thickness_in",
  "roof_layers",
  "msp_x_ft",
  "msp_y_ft",
  "inverter_x_ft",
  "inverter_y_ft",
  "ac_disconnect_x_ft",
  "ac_disconnect_y_ft",
  "ess_x_ft",
  "ess_y_ft",
  "attic_drop_x_ft",
  "attic_drop_y_ft",
  "attic_to_eq_height_ft",
]);

const templates = {
  pv_ess: {
    modules: 32,
    strings: 4,
    module_choice: "talesun_tp7g54m_415",
    inverter_choice: "growatt",
    battery_choice: "inhouse_16kwh_hv",
    battery_quantity: 1,
    interconnection_method: "supply_side_tap",
    self_consumption_fraction: 0.55,
  },
  pv_only: {
    modules: 24,
    strings: 3,
    module_choice: "talesun_tp7g54m_415",
    inverter_choice: "growatt",
    battery_choice: "none",
    battery_quantity: 0,
    interconnection_method: "supply_side_tap",
    self_consumption_fraction: 0.40,
  },
  retrofit_existing_pv: {
    modules: 20,
    strings: 2,
    module_choice: "rec_alpha_pure_410",
    inverter_choice: "megarova",
    battery_choice: "growatt_apx_20kwh",
    battery_quantity: 1,
    interconnection_method: "sum_rule",
    self_consumption_fraction: 0.65,
  },
};

const dfwResidentialMonthlyKwh = [
  880, 780, 720, 820, 1050, 1450, 1700, 1750, 1450, 1050, 820, 860,
];

const addressSamples = {
  glasshouse: {
    project_name: "Frisco PV + ESS Package",
    site_address: "7652 Glasshouse Walk, Frisco, TX",
    location: "Frisco, TX",
    ahj: "Frisco TX",
    utility: "Oncor Electric Delivery",
    monthly_kwh_text: dfwResidentialMonthlyKwh.join(", "),
  },
  crossvine: {
    project_name: "Mansfield Crossvine PV + ESS Package",
    site_address: "905 Crossvine Drive, Mansfield, TX",
    location: "Mansfield, TX",
    ahj: "City of Mansfield Building Safety",
    utility: "Oncor Electric Delivery",
    monthly_kwh_text: dfwResidentialMonthlyKwh.join(", "),
  },
  green_circle: {
    project_name: "Mansfield Green Circle PV + ESS Package",
    site_address: "2806 Green Circle Drive, Mansfield, TX",
    location: "Mansfield, TX",
    ahj: "City of Mansfield Building Safety",
    utility: "Oncor Electric Delivery",
    installer_address: "2806 Green Cir Dr, Mansfield, TX",
    monthly_kwh_text: dfwResidentialMonthlyKwh.join(", "),
  },
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const formData = new FormData(form);
  const payload = buildPayload(formData);
  const validation = validatePayload(payload);
  renderValidation(validation.errors, validation.warnings);
  if (validation.errors.length > 0) {
    statusEl.textContent = "Fix validation errors before generating.";
    statusEl.classList.add("error");
    return;
  }

  setBusy(true, "Submitting generation job.");
  setProgress(2, "Submitting generation job.");

  try {
    const request = new FormData();
    request.append("payload", JSON.stringify(payload));
    appendSiteFiles(request, formData);

    const response = await apiFetch("/api/projects/form", {
      method: "POST",
      body: request,
    });
    const state = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(state));
    }
    setBusy(true, `Job ${state.job_id} queued.`);
    pollJob(state.job_id);
  } catch (error) {
    setBusy(false, "");
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
});

preflightButton.addEventListener("click", runPreflight);
fileFilter.addEventListener("change", () => renderFiles(currentFiles));
saveTokenButton.addEventListener("click", saveAccessToken);
lookupButton.addEventListener("click", runAddressLookup);
previewPanel.addEventListener("click", handlePreviewClick);
projectTemplate.addEventListener("change", () => applyTemplate(projectTemplate.value));
addressSample.addEventListener("change", () => applyAddressSample(addressSample.value));
moduleChoice.addEventListener("change", syncModuleOption);
inverterChoice.addEventListener("change", syncInverterOption);
batteryChoice.addEventListener("change", syncBatteryOption);

loadAccessToken();
syncModuleOption();
syncInverterOption();
syncBatteryOption({ preserveQuantity: true });
loadHistory();

function loadAccessToken() {
  const token = localStorage.getItem("pvess_access_token") || "";
  accessTokenInput.value = token;
  tokenStatus.textContent = token ? "Token saved for API and file requests" : "Local server mode";
}

function saveAccessToken() {
  const token = accessTokenInput.value.trim();
  if (token) {
    localStorage.setItem("pvess_access_token", token);
    tokenStatus.textContent = "Token saved for API and file requests";
  } else {
    localStorage.removeItem("pvess_access_token");
    tokenStatus.textContent = "Local server mode";
  }
  loadHistory();
}

function currentAccessToken() {
  return (accessTokenInput.value || localStorage.getItem("pvess_access_token") || "").trim();
}

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = currentAccessToken();
  if (token) {
    headers.set("X-PVESS-Token", token);
  }
  return fetch(url, {
    ...options,
    headers,
  });
}

function withAuthUrl(url) {
  const token = currentAccessToken();
  if (!token || !url) {
    return url;
  }
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}

function applyTemplate(name) {
  const preset = templates[name];
  if (!preset) {
    return;
  }
  for (const [key, value] of Object.entries(preset)) {
    const field = form.elements[key] || document.querySelector(`[name="${key}"]`);
    if (field) {
      field.value = value;
    }
  }
  syncModuleOption();
  syncInverterOption();
  syncBatteryOption({ preserveQuantity: true });
  renderValidation([], [`Applied template: ${labelForTemplate(name)}.`]);
}

function applyAddressSample(name) {
  const sample = addressSamples[name];
  if (!sample) {
    return;
  }
  for (const [key, value] of Object.entries(sample)) {
    setFieldValue(key, value);
  }
  renderValidation([], [`Applied address sample: ${sample.site_address}. Monthly usage is simulated until replaced by a utility bill.`]);
}

function buildPayload(data) {
  const payload = {};
  for (const [key, rawValue] of data.entries()) {
    if (key.startsWith("out_")) {
      continue;
    }
    if (key === "monthly_kwh_text") {
      continue;
    }
    if (rawValue instanceof File) {
      continue;
    }
    const value = typeof rawValue === "string" ? rawValue.trim() : rawValue;
    if (numberFields.has(key)) {
      if (value === "") {
        continue;
      }
      payload[key] = Number(value);
    } else {
      payload[key] = value;
    }
  }

  const monthly = parseMonthlyKwh(data.get("monthly_kwh_text") || "");
  if (monthly.length > 0) {
    payload.monthly_kwh = monthly;
  }

  payload.outputs = {
    customer: data.has("out_customer"),
    permit: data.has("out_permit"),
    dxf: data.has("out_dxf"),
    labels: data.has("out_labels"),
    qet: data.has("out_qet"),
  };

  return payload;
}

function validatePayload(payload) {
  const errors = [];
  const warnings = [];
  const modules = Number(payload.modules || 0);
  const strings = Number(payload.strings || 0);
  const moduleWatts = Number(moduleChoice.selectedOptions[0]?.dataset.watts || 0);
  const inverterAmps = Number(inverterAmpsInput.value || 0);
  const inverterQty = Number(payload.inverter_quantity || 1);
  const acKw = inverterAmps * 240 * inverterQty / 1000;
  const dcKw = modules * moduleWatts / 1000;

  if (strings > 0 && modules % strings !== 0) {
    errors.push("Module count must divide evenly by string count.");
  }
  if (payload.battery_choice === "none" && Number(payload.battery_quantity || 0) > 0) {
    errors.push("Battery quantity must be 0 when No battery is selected.");
  }
  if (payload.battery_choice !== "none" && Number(payload.battery_quantity || 0) === 0) {
    warnings.push("A battery model is selected but quantity is 0; this will generate a PV-only package.");
  }
  if (payload.monthly_kwh && payload.monthly_kwh.length !== 12) {
    errors.push("Monthly kWh must contain exactly 12 numeric values.");
  }
  if (acKw > 0) {
    const ratio = dcKw / acKw;
    if (ratio > 1.7) {
      errors.push(`DC/AC ratio is ${ratio.toFixed(2)}; reduce modules or add inverter capacity.`);
    } else if (ratio > 1.45) {
      warnings.push(`DC/AC ratio is ${ratio.toFixed(2)}; engineering review recommended.`);
    }
  }
  return { errors, warnings };
}

function parseMonthlyKwh(raw) {
  const text = String(raw || "").trim();
  if (!text) {
    return [];
  }
  return text
    .split(/[\s,;]+/)
    .map((item) => Number(item))
    .filter((value) => Number.isFinite(value));
}

async function runPreflight() {
  clearError();
  const formData = new FormData(form);
  const payload = buildPayload(formData);
  const validation = validatePayload(payload);
  renderValidation(validation.errors, validation.warnings);
  if (validation.errors.length > 0) {
    statusEl.textContent = "Fix validation errors before preflight.";
    statusEl.classList.add("error");
    return;
  }

  preflightButton.disabled = true;
  preflightButton.textContent = "Checking...";
  statusEl.textContent = "Running preflight.";
  try {
    const response = await apiFetch("/api/preflight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    renderPreflight(data);
    statusEl.textContent = `Preflight ${data.status}`;
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  } finally {
    preflightButton.disabled = false;
    preflightButton.textContent = "Run preflight";
  }
}

async function runAddressLookup() {
  clearError();
  const address = (
    form.elements.site_address?.value ||
    form.elements.location?.value ||
    ""
  ).trim();
  if (!address) {
    renderLookupMessage("Enter a site address before lookup.", "warning");
    return;
  }

  lookupButton.disabled = true;
  lookupButton.textContent = "Looking up...";
  statusEl.textContent = "Looking up address data.";
  try {
    const mode = lookupMode.value || "online";
    const response = await apiFetch(
      `/api/lookup/address?address=${encodeURIComponent(address)}&mode=${encodeURIComponent(mode)}`
    );
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    applyLookupToForm(data.suggested_payload || {});
    renderLookup(data);
    statusEl.textContent = `Address lookup ${data.status}`;
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  } finally {
    lookupButton.disabled = false;
    lookupButton.textContent = "Lookup address";
  }
}

function applyLookupToForm(suggested) {
  for (const [key, value] of Object.entries(suggested)) {
    setFieldValue(key, value);
  }
}

function renderLookup(data) {
  const suggested = Object.keys(data.suggested_payload || {});
  const providers = data.providers || [];
  const hits = providers.filter((provider) => provider.hit);
  const roof = data.roof_summary || {};
  lookupPanel.classList.remove("hidden");
  lookupPanel.innerHTML = `
    <div class="lookup-summary">
      <div>
        <strong>${escapeHtml(data.status)} · ${escapeHtml(data.mode)} lookup</strong>
        <span>${hits.length}/${providers.length} providers returned data${roof.section_count ? ` · ${roof.section_count} roof faces` : ""}</span>
      </div>
      <span>${roof.imagery_quality ? `Solar imagery ${escapeHtml(roof.imagery_quality)}` : "Review fields before generation"}</span>
    </div>
    <div class="lookup-fields">
      ${suggested.map((field) => `<span>${escapeHtml(field)}</span>`).join("") || "<span>No form fields changed</span>"}
    </div>
    <div class="lookup-sources">
      ${hits.slice(0, 5).map((provider) => `${escapeHtml(provider.source)}:${escapeHtml(provider.confidence)}`).join(" · ") || "No provider hits"}
    </div>
  `;
}

function renderLookupMessage(message, type) {
  lookupPanel.classList.remove("hidden");
  lookupPanel.innerHTML = `<div class="validation-${type}">${escapeHtml(message)}</div>`;
}

async function pollJob(jobId) {
  if (activePoll) {
    clearTimeout(activePoll);
  }

  const tick = async () => {
    try {
      const response = await apiFetch(`/api/jobs/${jobId}`);
      const state = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(state));
      }
      renderJobState(state);
      if (state.status === "done") {
        setBusy(false, `Done. Job ${state.job_id}`);
        renderResult(state.result);
        await loadHistory();
        return;
      }
      if (state.status === "failed") {
        setBusy(false, "");
        statusEl.textContent = state.error || "Generation failed.";
        statusEl.classList.add("error");
        renderError(state.error || state.message || "Generation failed.");
        await loadHistory();
        return;
      }
      activePoll = setTimeout(tick, 900);
    } catch (error) {
      setBusy(false, "");
      statusEl.textContent = error.message;
      statusEl.classList.add("error");
      renderError(error.message);
    }
  };

  await tick();
}

function renderJobState(state) {
  setProgress(state.progress || 0, `${state.stage}: ${state.message}`);
  if (state.status !== "done") {
    statusEl.textContent = `${state.status}: ${state.message}`;
  }
}

function renderResult(data) {
  if (!data) {
    return;
  }
  const summary = data.summary;
  summaryStrip.innerHTML = `
    <div><strong>${summary.system_kw_dc}</strong><span>DC kW</span></div>
    <div><strong>${summary.modules}</strong><span>Modules</span></div>
    <div><strong>${money(summary.installed_cost_usd)}</strong><span>Installed cost</span></div>
    <div><strong>${money(summary.cost_after_itc_usd)}</strong><span>ITC cost</span></div>
  `;

  renderBom(data.bom);
  renderSourceMaterials(data.source_materials || {});
  renderReadiness(data.readiness || {});
  renderDeliveryPackage(data.files || []);
  renderPreviews(data.files || []);
  renderFiles(data.files);
  renderError("");
}

function renderPreflight(data) {
  const issues = data.issues || [];
  const intake = data.intake || {};
  const estimate = data.estimate || {};
  const statusClass = data.status === "PASS" ? "pass" : (data.status === "FAIL" ? "fail" : "warn");
  preflightEmpty.classList.add("hidden");
  preflightPanel.classList.remove("hidden");
  preflightPanel.innerHTML = `
    <div class="readiness-status ${statusClass}">
      <strong>${escapeHtml(data.status)}</strong>
      <span>${intake.ready || 0}/${intake.total || 0} intake items ready · ${money(estimate.cost_after_itc_usd)} after ITC</span>
    </div>
    <dl class="preflight-metrics">
      <dt>DC size</dt><dd>${data.summary?.system_kw_dc ?? "-"} kW</dd>
      <dt>Installed</dt><dd>${money(estimate.installed_cost_usd)}</dd>
      <dt>Annual savings</dt><dd>${money(estimate.annual_bill_savings_usd)}</dd>
      <dt>Payback</dt><dd>${estimate.payback_after_itc_years ?? "-"} yr</dd>
    </dl>
    <div class="intake-meter">
      <span style="width: ${Math.max(0, Math.min(100, Number(intake.percent) || 0))}%"></span>
    </div>
    <ul class="preflight-list">
      ${issues.slice(0, 8).map((issue) => `
        <li class="${issue.severity}">
          <span>${escapeHtml(issue.severity)}</span>
          <strong>${escapeHtml(issue.field)}</strong>
          <em>${escapeHtml(issue.message)}</em>
        </li>
      `).join("") || "<li class=\"pass\"><strong>No blocking issues detected</strong></li>"}
    </ul>
  `;
}

function appendSiteFiles(request, data) {
  for (const key of [
    "front_elevation",
    "roof",
    "meter",
    "main_panel",
    "sub_panel",
    "equipment_location",
    "utility_bill",
    "structural_letter",
    "spec_module",
    "spec_inverter",
    "spec_battery",
    "spec_racking",
    "spec_optimizer",
  ]) {
    const file = data.get(key);
    if (file instanceof File && file.size > 0) {
      request.append(key, file, file.name);
    }
  }
}

function syncModuleOption() {
  const selected = moduleChoice.selectedOptions[0];
  moduleBrandDisplay.value = selected.dataset.brand || "";
  moduleModelDisplay.value = selected.dataset.model || "";
  moduleWattsDisplay.value = selected.dataset.watts || "";
}

function syncInverterOption() {
  const selected = inverterChoice.selectedOptions[0];
  inverterModelDisplay.value = selected.dataset.model || "";
  inverterAmpsInput.value = selected.dataset.amps || "";
}

function syncBatteryOption(options = {}) {
  const selected = batteryChoice.selectedOptions[0];
  batteryModelDisplay.value = selected.dataset.model || "";
  batteryKwhDisplay.value = selected.dataset.kwh || "0";
  if (batteryChoice.value === "none") {
    batteryQtyInput.value = "0";
  } else if (!options.preserveQuantity && Number(batteryQtyInput.value || 0) === 0) {
    batteryQtyInput.value = "1";
  }
}

function renderBom(bom) {
  bomEmpty.classList.add("hidden");
  bomTable.classList.remove("hidden");
  quoteCards.classList.remove("hidden");
  categoryCosts.classList.remove("hidden");
  costTotals.classList.remove("hidden");
  bomBody.innerHTML = "";
  renderQuoteCards(bom.quote_tiers || []);
  renderCategoryCosts(bom.installed_breakdown || bom.categories || []);

  for (const line of bom.lines) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(line.label)}</td>
      <td>${line.quantity}</td>
      <td>${money(line.unit_price_usd)}</td>
      <td>${money(line.total_usd)}</td>
    `;
    bomBody.appendChild(row);
  }

  costTotals.innerHTML = `
    <dt>Parts subtotal</dt><dd>${money(bom.parts_subtotal_usd)}</dd>
    <dt>Estimated labor and soft costs</dt><dd>${money(bom.estimated_labor_soft_costs_usd)}</dd>
    <dt>Installed cost</dt><dd>${money(bom.installed_cost_usd)}</dd>
    <dt>Cost after 30% ITC</dt><dd>${money(bom.cost_after_itc_usd)}</dd>
    <dt>Annual savings</dt><dd>${money(bom.annual_bill_savings_usd)}</dd>
    <dt>Payback after ITC</dt><dd>${bom.payback_after_itc_years ?? "-"} years</dd>
  `;
}

function renderQuoteCards(tiers) {
  if (!tiers.length) {
    quoteCards.innerHTML = "";
    quoteCards.classList.add("hidden");
    return;
  }
  quoteCards.innerHTML = tiers.map((tier) => `
    <article class="quote-card ${tier.is_selected ? "selected" : ""}">
      <div class="quote-title">${escapeHtml(tier.name)}</div>
      <div class="quote-price">${money(tier.cost_after_itc_usd)}</div>
      <div class="quote-sub">${money(tier.installed_cost_usd)} before ITC</div>
      <dl>
        <dt>Battery</dt><dd>${tier.battery_kwh_total} kWh</dd>
        <dt>Savings</dt><dd>${money(tier.monthly_savings_usd)} / mo</dd>
        <dt>Payback</dt><dd>${tier.payback_after_itc_years ?? "-"} yr</dd>
      </dl>
      <p>${escapeHtml(tier.backup_summary)}</p>
    </article>
  `).join("");
}

function renderCategoryCosts(categories) {
  if (!categories.length) {
    categoryCosts.innerHTML = "";
    categoryCosts.classList.add("hidden");
    return;
  }
  categoryCosts.innerHTML = categories.map((category) => `
    <div>
      <span>${escapeHtml(category.name)}</span>
      <strong>${money(category.total_usd)}</strong>
    </div>
  `).join("");
}

function renderFiles(files) {
  currentFiles = files || [];
  const selected = fileFilter.value;
  const shown = selected === "all"
    ? currentFiles
    : currentFiles.filter((file) => file.category === selected);
  filesEmpty.classList.toggle("hidden", shown.length > 0);
  fileCount.textContent = currentFiles.length
    ? `${shown.length}/${currentFiles.length} shown`
    : "";
  fileList.innerHTML = "";
  for (const file of shown) {
    const item = document.createElement("li");
    item.innerHTML = `
      <a href="${withAuthUrl(file.url)}" target="_blank" rel="noopener">${escapeHtml(file.label)}</a>
      <span><em>${escapeHtml(file.category || "Other")}</em>${formatBytes(file.bytes)}</span>
    `;
    fileList.appendChild(item);
  }
}

function renderDeliveryPackage(files) {
  const archive = files.find((file) => file.label === "Complete Project ZIP");
  deliveryEmpty.classList.toggle("hidden", Boolean(archive));
  deliveryPackage.classList.toggle("hidden", !archive);
  if (!archive) {
    deliveryPackage.innerHTML = "";
    return;
  }
  deliveryPackage.innerHTML = `
    <a class="package-link" href="${withAuthUrl(archive.url)}" target="_blank" rel="noopener">
      Download complete ZIP
    </a>
    <span>${formatBytes(archive.bytes)}</span>
  `;
}

function renderPreviews(files) {
  const previewImages = files.filter((file) => file.kind === "preview");
  const previewDocs = files.filter((file) => ["pdf", "markdown"].includes(file.kind));
  currentPreviewItems = [...previewDocs, ...previewImages];
  const hasPreview = currentPreviewItems.length > 0;
  previewEmpty.classList.toggle("hidden", hasPreview);
  previewPanel.classList.toggle("hidden", !hasPreview);
  if (!hasPreview) {
    previewPanel.innerHTML = "";
    return;
  }

  const active = previewDocs.find((file) => file.kind === "pdf") || previewImages[0] || previewDocs[0];
  previewPanel.innerHTML = `
    ${renderPreviewViewer(active)}
    <div class="preview-actions">
      ${currentPreviewItems.map((file, index) => `
        <button type="button" data-preview-index="${index}">${escapeHtml(file.label)}</button>
        <a href="${withAuthUrl(file.url)}" target="_blank" rel="noopener">Open</a>
      `).join("")}
    </div>
    <div class="preview-grid">
      ${previewImages.map((file) => `
        <a class="preview-card" href="${withAuthUrl(file.url)}" target="_blank" rel="noopener">
          <img src="${withAuthUrl(file.url)}" alt="${escapeHtml(file.label)}" loading="lazy" />
          <span>${escapeHtml(file.label)}</span>
        </a>
      `).join("")}
    </div>
  `;
}

function handlePreviewClick(event) {
  const button = event.target.closest("[data-preview-index]");
  if (!button) {
    return;
  }
  const item = currentPreviewItems[Number(button.dataset.previewIndex)];
  if (!item) {
    return;
  }
  const viewer = previewPanel.querySelector(".preview-viewer");
  if (viewer) {
    viewer.outerHTML = renderPreviewViewer(item);
  }
}

function renderPreviewViewer(file) {
  if (!file) {
    return "";
  }
  const url = withAuthUrl(file.url);
  const body = file.kind === "preview"
    ? `<img src="${url}" alt="${escapeHtml(file.label)}" />`
    : `<iframe src="${url}" title="${escapeHtml(file.label)}"></iframe>`;
  return `
    <div class="preview-viewer">
      <div class="preview-viewer-header">
        <strong>${escapeHtml(file.label)}</strong>
        <span>${formatBytes(file.bytes)}</span>
      </div>
      ${body}
    </div>
  `;
}

function renderSourceMaterials(source) {
  const photos = source.site_photos || [];
  const hasDocs = (
    source.utility_bill_uploaded ||
    source.structural_letter_uploaded ||
    source.spec_sheet_count ||
    source.monthly_kwh_count
  );
  sourceEmpty.classList.toggle("hidden", photos.length > 0 || hasDocs);
  sourceMaterials.classList.toggle("hidden", photos.length === 0 && !hasDocs);
  if (photos.length === 0 && !hasDocs) {
    sourceMaterials.innerHTML = "";
    return;
  }

  const missing = source.missing_photo_kinds || [];
  sourceMaterials.innerHTML = `
    <dt>Source material status</dt><dd>${source.site_data_source === "real" ? "Field-uploaded source materials" : "Simulated source materials"}</dd>
    <dt>PV-7 photos</dt><dd>${source.site_photo_count || 0}/${source.required_site_photo_count || 6}</dd>
    <dt>Utility bill</dt><dd>${source.utility_bill_uploaded ? "uploaded" : "not uploaded"}</dd>
    <dt>Structural letter</dt><dd>${source.structural_letter_uploaded ? "uploaded" : "not uploaded"}</dd>
    <dt>Spec sheets</dt><dd>${source.spec_sheet_count || 0}</dd>
    <dt>Monthly usage</dt><dd>${source.monthly_kwh_count || 0}/12</dd>
    <dt>Equipment coordinates</dt><dd>${source.equipment_locations_ready ? "ready" : "missing"}</dd>
    <dt>Missing photos</dt><dd>${missing.length ? missing.join(", ") : "none"}</dd>
  `;
}

function renderReadiness(readiness) {
  const counts = readiness.counts || {};
  const reviewItems = readiness.review_items || [];
  readinessEmpty.classList.toggle("hidden", Boolean(readiness.status));
  readinessPanel.classList.toggle("hidden", !readiness.status);
  if (!readiness.status) {
    readinessPanel.innerHTML = "";
    return;
  }

  const statusClass = readiness.status === "PASS" ? "pass" : "warn";
  readinessPanel.innerHTML = `
    <div class="readiness-status ${statusClass}">
      <strong>${escapeHtml(readiness.status)}</strong>
      <span>${readiness.needs_review ? "Review before AHJ submission" : "Ready for strict gate"}</span>
    </div>
    <dl class="readiness-counts">
      <dt>Ready</dt><dd>${counts.ready || 0}</dd>
      <dt>Simulated</dt><dd>${counts.simulated || 0}</dd>
      <dt>Missing</dt><dd>${counts.missing || 0}</dd>
      <dt>N/A</dt><dd>${counts.not_applicable || 0}</dd>
    </dl>
    <ul class="readiness-list">
      ${reviewItems.slice(0, 6).map((item) => `
        <li>
          <span>${escapeHtml(item.status)}</span>
          <strong>${escapeHtml(item.key)}</strong>
        </li>
      `).join("") || "<li><strong>No open data gaps</strong></li>"}
    </ul>
  `;
}

function renderError(message) {
  const text = String(message || "").trim();
  errorEmpty.classList.toggle("hidden", Boolean(text));
  errorPanel.classList.toggle("hidden", !text);
  errorPanel.textContent = text;
}

async function loadHistory() {
  try {
    const response = await apiFetch("/api/jobs");
    const data = await response.json();
    const jobs = data.jobs || [];
    historyList.innerHTML = "";
    historyEmpty.classList.toggle("hidden", jobs.length > 0);
    for (const job of jobs) {
      const item = document.createElement("li");
      const title = job.result?.summary?.project_name || job.job_id;
      item.innerHTML = `
        <button type="button" class="history-button" data-job-id="${job.job_id}">
          ${escapeHtml(title)}
        </button>
        <span class="history-actions">
          <button type="button" data-job-action="load" data-job-id="${job.job_id}">Load</button>
          <button type="button" data-job-action="rerun" data-job-id="${job.job_id}">Rerun</button>
          <button type="button" data-job-action="delete" data-job-id="${job.job_id}">Delete</button>
        </span>
      `;
      historyList.appendChild(item);
    }
  } catch {
    historyEmpty.classList.remove("hidden");
  }
}

historyList.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-job-id]");
  if (!target) {
    return;
  }
  const jobId = target.dataset.jobId;
  const action = target.dataset.jobAction || "view";
  try {
    if (action === "load") {
      const response = await apiFetch(`/api/jobs/${jobId}/payload`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(payload));
      }
      applyPayloadToForm(payload);
      statusEl.textContent = `Loaded form from job ${jobId}`;
      return;
    }
    if (action === "rerun") {
      const response = await apiFetch(`/api/jobs/${jobId}/rerun`, { method: "POST" });
      const state = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(state));
      }
      setBusy(true, `Rerunning job ${jobId}.`);
      pollJob(state.job_id);
      return;
    }
    if (action === "delete") {
      const response = await apiFetch(`/api/jobs/${jobId}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(data));
      }
      statusEl.textContent = `Deleted job ${jobId}`;
      await loadHistory();
      return;
    }

    const response = await apiFetch(`/api/jobs/${jobId}`);
    const state = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(state));
    }
    renderJobState(state);
    if (state.result) {
      renderResult(state.result);
      statusEl.textContent = `Viewed job ${state.job_id}`;
    }
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
});

function applyPayloadToForm(payload) {
  for (const [key, value] of Object.entries(payload || {})) {
    if (key === "outputs") {
      continue;
    }
    if (key === "monthly_kwh") {
      const monthly = Array.isArray(value) ? value.join(", ") : "";
      setFieldValue("monthly_kwh_text", monthly);
      continue;
    }
    if (Array.isArray(value) || (value && typeof value === "object")) {
      continue;
    }
    setFieldValue(key, value);
  }
  const outputs = payload.outputs || {};
  setCheckbox("out_customer", outputs.customer);
  setCheckbox("out_permit", outputs.permit);
  setCheckbox("out_dxf", outputs.dxf);
  setCheckbox("out_labels", outputs.labels);
  setCheckbox("out_qet", outputs.qet);
  syncModuleOption();
  syncInverterOption();
  syncBatteryOption({ preserveQuantity: true });
  renderValidation([], ["Loaded prior job payload. File inputs must be reattached before a rerun with new uploads."]);
}

function setFieldValue(name, value) {
  const field = form.elements[name] || document.querySelector(`[name="${name}"]`);
  if (!field || field.type === "file") {
    return;
  }
  if (field.type === "checkbox") {
    field.checked = Boolean(value);
    return;
  }
  field.value = value ?? "";
}

function setCheckbox(name, value) {
  const field = form.elements[name];
  if (field) {
    field.checked = Boolean(value);
  }
}

function renderValidation(errors, warnings) {
  if (errors.length === 0 && warnings.length === 0) {
    validationPanel.classList.add("hidden");
    validationPanel.innerHTML = "";
    return;
  }
  validationPanel.classList.remove("hidden");
  validationPanel.innerHTML = [
    ...errors.map((msg) => `<div class="validation-error">${escapeHtml(msg)}</div>`),
    ...warnings.map((msg) => `<div class="validation-warning">${escapeHtml(msg)}</div>`),
  ].join("");
}

function setProgress(percent, message) {
  progressBar.style.width = `${Math.max(0, Math.min(100, Number(percent) || 0))}%`;
  progressMessage.textContent = message || "No active job.";
}

function setBusy(isBusy, message) {
  button.disabled = isBusy;
  button.textContent = isBusy ? "Generating..." : "Generate package";
  statusEl.textContent = message;
}

function clearError() {
  statusEl.classList.remove("error");
  renderError("");
}

function formatApiError(data) {
  if (!data || data.detail === undefined) {
    return "Generation failed.";
  }
  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  }
  return String(data.detail);
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function labelForTemplate(name) {
  return {
    pv_ess: "PV + ESS",
    pv_only: "PV-only",
    retrofit_existing_pv: "Retrofit with existing PV",
  }[name] || name;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
