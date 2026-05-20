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
const leadEmpty = document.querySelector("#lead-empty");
const leadList = document.querySelector("#lead-list");
const leadStatus = document.querySelector("#lead-status");
const leadQuery = document.querySelector("#lead-query");
const leadRefresh = document.querySelector("#lead-refresh");
const leadExport = document.querySelector("#lead-export");
const readinessEmpty = document.querySelector("#readiness-empty");
const readinessPanel = document.querySelector("#readiness-panel");
const packageQaEmpty = document.querySelector("#package-qa-empty");
const packageQaPanel = document.querySelector("#package-qa-panel");
const runPackageQaButton = document.querySelector("#run-package-qa");
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
const historyStatus = document.querySelector("#history-status");
const historyQuery = document.querySelector("#history-query");
const historyFrom = document.querySelector("#history-from");
const historyTo = document.querySelector("#history-to");
const historyAll = document.querySelector("#history-all");
const historyRefresh = document.querySelector("#history-refresh");
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
let currentJobId = "";
let currentReadiness = {};
let artifactReviews = {};
let lastLookupRoofCandidates = [];
let runtimeConfig = { auth_required: false };

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
    statusEl.textContent = "Fix the highlighted inputs before generating the package.";
    statusEl.classList.add("error");
    return;
  }

  setBusy(true, "Submitting estimate package job.");
  setProgress(2, "Submitting estimate package job.");

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
    setBusy(true, `Package job ${state.job_id} queued.`);
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
lookupPanel.addEventListener("click", handleLookupCandidateClick);
previewPanel.addEventListener("click", handlePreviewClick);
fileList.addEventListener("change", handleArtifactReviewChange);
runPackageQaButton.addEventListener("click", runPackageQa);
leadRefresh.addEventListener("click", loadLeads);
leadExport.addEventListener("click", exportLeadsCsv);
projectTemplate.addEventListener("change", () => applyTemplate(projectTemplate.value));
addressSample.addEventListener("change", () => applyAddressSample(addressSample.value));
moduleChoice.addEventListener("change", syncModuleOption);
inverterChoice.addEventListener("change", syncInverterOption);
batteryChoice.addEventListener("change", syncBatteryOption);

loadAccessToken();
syncModuleOption();
syncInverterOption();
syncBatteryOption({ preserveQuantity: true });
loadRuntimeConfig().then(() => {
  loadHistory();
  loadLeads();
});

async function loadRuntimeConfig() {
  try {
    const response = await fetch("/api/runtime-config");
    if (response.ok) {
      runtimeConfig = await response.json();
    }
  } catch {
    runtimeConfig = { auth_required: false };
  }
  if (runtimeConfig.auth_required && !currentAccessToken()) {
    tokenStatus.textContent = "Enter an operator token to use API and files";
  }
}

function loadAccessToken() {
  const token = localStorage.getItem("pvess_access_token") || "";
  accessTokenInput.value = token;
  tokenStatus.textContent = token ? "Operator token saved for API and files" : "No token required on local server";
}

function saveAccessToken() {
  const token = accessTokenInput.value.trim();
  if (token) {
    localStorage.setItem("pvess_access_token", token);
    tokenStatus.textContent = "Operator token saved for API and files";
  } else {
    localStorage.removeItem("pvess_access_token");
    tokenStatus.textContent = "No token required on local server";
  }
  loadHistory();
  loadLeads();
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
  renderValidation([], [`Project type set to ${labelForTemplate(name)}.`]);
}

function applyAddressSample(name) {
  const sample = addressSamples[name];
  if (!sample) {
    return;
  }
  for (const [key, value] of Object.entries(sample)) {
    setFieldValue(key, value);
  }
  renderValidation([], [`Loaded sample address: ${sample.site_address}. Monthly usage is simulated until a bill or Smart Meter export is uploaded.`]);
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
    statusEl.textContent = "Fix the highlighted inputs before checking readiness.";
    statusEl.classList.add("error");
    return;
  }

  preflightButton.disabled = true;
  preflightButton.textContent = "Checking...";
  statusEl.textContent = "Checking project readiness.";
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
    statusEl.textContent = `Readiness check ${data.status}`;
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  } finally {
    preflightButton.disabled = false;
    preflightButton.textContent = "Check readiness";
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
    renderLookupMessage("Enter a site address before using auto-fill.", "warning");
    return;
  }

  lookupButton.disabled = true;
  lookupButton.textContent = "Auto-filling...";
  statusEl.textContent = "Looking up address details.";
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
    statusEl.textContent = `Address auto-fill ${data.status}`;
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  } finally {
    lookupButton.disabled = false;
    lookupButton.textContent = "Auto-fill from address";
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
  lastLookupRoofCandidates = roof.candidates || [];
  lookupPanel.classList.remove("hidden");
  lookupPanel.innerHTML = `
    <div class="lookup-summary">
      <div>
        <strong>${escapeHtml(data.status)} · ${escapeHtml(data.mode)} address data</strong>
        <span>${hits.length}/${providers.length} data sources returned project data${roof.section_count ? ` · ${roof.section_count} roof faces` : ""}</span>
      </div>
      <span>${roof.imagery_quality ? `Solar imagery ${escapeHtml(roof.imagery_quality)}` : "Review roof and service fields before generation"}</span>
    </div>
    <div class="lookup-fields">
      ${suggested.map((field) => `<span>${escapeHtml(field)}</span>`).join("") || "<span>No form fields changed</span>"}
    </div>
    <div class="lookup-sources">
      ${hits.slice(0, 5).map((provider) => `${escapeHtml(provider.source)}:${escapeHtml(provider.confidence)}`).join(" · ") || "No lookup data returned"}
    </div>
    ${lastLookupRoofCandidates.length ? `
      <div class="roof-candidates">
        ${lastLookupRoofCandidates.slice(0, 6).map((section, index) => `
          <button type="button" data-roof-candidate="${index}">
            ${escapeHtml(section.name || `Roof ${index + 1}`)}
            <span>${escapeHtml(String(section.azimuth_deg ?? "-"))}° · ${escapeHtml(String(section.pitch_deg ?? "-"))}° · ${escapeHtml(String(section.area_sqft ?? "-"))} sq ft</span>
          </button>
        `).join("")}
      </div>
    ` : ""}
  `;
}

function handleLookupCandidateClick(event) {
  const button = event.target.closest("[data-roof-candidate]");
  if (!button) {
    return;
  }
  const section = lastLookupRoofCandidates[Number(button.dataset.roofCandidate)];
  if (!section) {
    return;
  }
  const updates = {
    roof_pitch_deg: section.pitch_deg,
    roof_azimuth_deg: section.azimuth_deg,
    roof_width_ft: section.width_ft,
    roof_height_ft: section.height_ft,
    roof_info_type: section.roof_type || "Comp Shingle",
  };
  for (const [key, value] of Object.entries(updates)) {
    if (value !== undefined && value !== null && value !== "") {
      setFieldValue(key, value);
    }
  }
  renderValidation([], [`Roof candidate applied: ${section.name || "Roof Section"}. Review dimensions before generation.`]);
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
        setBusy(false, `Package ready. Project ${state.job_id}`);
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
  currentJobId = data.job_id || "";
  currentReadiness = data.readiness || {};
  artifactReviews = {};
  const summary = data.summary;
  summaryStrip.innerHTML = `
    <div><strong>${summary.system_kw_dc}</strong><span>DC kW</span></div>
    <div><strong>${summary.modules}</strong><span>Modules</span></div>
    <div><strong>${money(summary.installed_cost_usd)}</strong><span>Installed cost</span></div>
    <div><strong>${money(summary.cost_after_itc_usd)}</strong><span>ITC cost</span></div>
  `;

  renderBom(data.bom);
  renderSourceMaterials(data.source_materials || {});
  renderReadiness(currentReadiness);
  renderPackageQa(data.package_qa || {});
  runPackageQaButton.disabled = !currentJobId;
  renderDeliveryPackage(data.files || []);
  renderPreviews(data.files || []);
  renderFiles(data.files);
  renderError("");
  loadArtifactReviews();
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
      <span>${intake.ready || 0}/${intake.total || 0} handoff items ready · ${money(estimate.cost_after_itc_usd)} after ITC</span>
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
          <em>${escapeHtml(issue.message)}${issue.blocks_level ? ` · blocks ${escapeHtml(issue.blocks_level)}` : ""}</em>
        </li>
      `).join("") || "<li class=\"pass\"><strong>No blocking issues detected. Ready to generate an estimate package.</strong></li>"}
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
    "attic",
    "equipment_location",
    "site_photos_auto",
    "utility_bill",
    "structural_letter",
    "spec_module",
    "spec_inverter",
    "spec_battery",
    "spec_racking",
    "spec_optimizer",
    "spec_sheets_auto",
  ]) {
    for (const file of data.getAll(key)) {
      if (file instanceof File && file.size > 0) {
        request.append(key, file, file.name);
      }
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
      <div class="quote-sub">${money(tier.installed_cost_usd)} before 30% ITC</div>
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
    const review = artifactReviews[file.path] || { status: "not_reviewed" };
    item.innerHTML = `
      <a href="${withAuthUrl(file.url)}" target="_blank" rel="noopener">${escapeHtml(file.label)}</a>
      <span>
        <em>${escapeHtml(file.category || "Other")}</em>${formatBytes(file.bytes)}
        <select data-review-path="${escapeHtml(file.path)}" aria-label="Review status for ${escapeHtml(file.label)}">
          ${reviewStatusOptions(review.status)}
        </select>
      </span>
    `;
    fileList.appendChild(item);
  }
}

async function loadArtifactReviews() {
  if (!currentJobId) {
    return;
  }
  try {
    const response = await apiFetch(`/api/jobs/${currentJobId}/reviews`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    artifactReviews = data.reviews || {};
    if (data.gate && currentReadiness) {
      currentReadiness.gate = data.gate;
      renderReadiness(currentReadiness);
    }
    renderFiles(currentFiles);
    renderPreviews(currentFiles);
  } catch {
    artifactReviews = {};
  }
}

async function handleArtifactReviewChange(event) {
  const select = event.target.closest("[data-review-path]");
  if (!select || !currentJobId) {
    return;
  }
  try {
    const response = await apiFetch(`/api/jobs/${currentJobId}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: select.dataset.reviewPath,
        status: select.value,
        note: "",
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    artifactReviews = data.reviews || {};
    if (data.gate && currentReadiness) {
      currentReadiness.gate = data.gate;
      renderReadiness(currentReadiness);
    }
    renderPreviews(currentFiles);
    statusEl.textContent = "Review status saved.";
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
}

function reviewStatusOptions(selected) {
  const options = [
    ["not_reviewed", "not reviewed"],
    ["needs_revision", "needs revision"],
    ["approved_internal", "approved for internal review"],
  ];
  return options.map(([value, label]) => `
    <option value="${value}" ${selected === value ? "selected" : ""}>${label}</option>
  `).join("");
}

function reviewStatusLabel(status) {
  if (status === "approved_internal") {
    return "approved";
  }
  if (status === "needs_revision") {
    return "needs revision";
  }
  return "not reviewed";
}

function reviewLabel(path) {
  const status = artifactReviews[path]?.status || "not_reviewed";
  if (status === "approved_internal") {
    return "approved for internal review";
  }
  return status.replace("_", " ");
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
      ${currentPreviewItems.map((file, index) => renderPreviewCard(file, index)).join("")}
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

function renderPreviewCard(file, index) {
  const review = reviewLabel(file.path);
  if (file.kind === "preview") {
    return `
      <button type="button" class="preview-card" data-preview-index="${index}">
        <img src="${withAuthUrl(file.url)}" alt="${escapeHtml(file.label)}" loading="lazy" />
        <span>${escapeHtml(file.label)}</span>
        <em>${escapeHtml(review)}</em>
      </button>
    `;
  }
  return `
    <button type="button" class="preview-card doc-thumb" data-preview-index="${index}">
      <strong>${escapeHtml(file.kind.toUpperCase())}</strong>
      <span>${escapeHtml(file.label)}</span>
      <em>${escapeHtml(review)}</em>
    </button>
  `;
}

function renderSourceMaterials(source) {
  const photos = source.site_photos || [];
  const specCoverage = source.spec_coverage || {};
  const classifications = source.photo_classifications || [];
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
    <dt>Utility parse</dt><dd>${source.utility_bill_parse?.status || "not parsed"}</dd>
    <dt>Structural letter</dt><dd>${source.structural_letter_uploaded ? "uploaded" : "not uploaded"}</dd>
    <dt>Spec sheets</dt><dd>${source.spec_sheet_count || 0} (${(specCoverage.missing || []).length ? `missing ${(specCoverage.missing || []).join(", ")}` : "covered"})</dd>
    <dt>Monthly usage</dt><dd>${source.monthly_kwh_count || 0}/12 · ${source.monthly_kwh_source || "none"}</dd>
    <dt>Equipment coordinates</dt><dd>${source.equipment_locations_ready ? "ready" : "missing"}</dd>
    <dt>Missing photos</dt><dd>${missing.length ? missing.join(", ") : "none"}</dd>
    <dt>Photo classification</dt><dd>${classifications.length ? classifications.map((item) => `${item.filename}: ${item.classified_kind}`).join("; ") : "none"}</dd>
  `;
}

async function loadLeads() {
  if (runtimeConfig.auth_required && !currentAccessToken()) {
    leadList.innerHTML = "";
    leadEmpty.textContent = "Enter an operator token to view public estimate requests.";
    leadEmpty.classList.remove("hidden");
    return;
  }
  leadEmpty.textContent = "Public estimate requests appear here.";
  try {
    const response = await apiFetch(`/api/leads${leadQueryString()}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    renderLeads(data.leads || []);
  } catch {
    leadList.innerHTML = "";
    leadEmpty.textContent = "Lead list is unavailable.";
    leadEmpty.classList.remove("hidden");
  }
}

function leadQueryString() {
  const params = new URLSearchParams();
  if (leadStatus.value) {
    params.set("status", leadStatus.value);
  }
  if (leadQuery.value.trim()) {
    params.set("q", leadQuery.value.trim());
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

function exportLeadsCsv() {
  if (runtimeConfig.auth_required && !currentAccessToken()) {
    leadEmpty.textContent = "Enter an operator token before exporting leads.";
    leadEmpty.classList.remove("hidden");
    return;
  }
  window.location.href = withAuthUrl(`/api/leads/export.csv${leadQueryString()}`);
}

function renderLeads(leads) {
  leadList.innerHTML = "";
  leadEmpty.classList.toggle("hidden", leads.length > 0);
  for (const lead of leads) {
    const item = document.createElement("li");
    const usage = Array.isArray(lead.monthly_kwh) && lead.monthly_kwh.length === 12
      ? "usage ready"
      : "usage missing";
    const converted = lead.status === "converted" && lead.converted_job_id;
    item.innerHTML = `
      <span class="lead-details">
        <strong>${escapeHtml(lead.contact_name || "New lead")}</strong>
        <em>${escapeHtml(lead.site_address || "")}</em>
        <em>
          ${lead.email ? `<a href="mailto:${escapeHtml(lead.email)}">${escapeHtml(lead.email)}</a>` : ""}
          ${lead.phone ? ` · <a href="tel:${escapeHtml(lead.phone)}">${escapeHtml(lead.phone)}</a>` : ""}
        </em>
        <em>${escapeHtml(labelForLeadType(lead.project_type))} · ${usage} · last contact ${escapeHtml(formatLeadDate(lead.last_contacted_at) || "not recorded")}</em>
        <label class="lead-note-label">
          Follow-up notes
          <textarea class="lead-note" data-lead-note="${escapeHtml(lead.lead_id)}">${escapeHtml(lead.notes || "")}</textarea>
        </label>
      </span>
      <span class="history-actions">
        <select data-lead-status="${escapeHtml(lead.lead_id)}">
          ${leadStatusOption(lead.status, "new", "New")}
          ${leadStatusOption(lead.status, "contacted", "Contacted")}
          ${leadStatusOption(lead.status, "qualified", "Qualified")}
          ${leadStatusOption(lead.status, "converted", "Converted")}
          ${leadStatusOption(lead.status, "archived", "Archived")}
        </select>
        <button type="button" data-lead-action="save" data-lead-id="${escapeHtml(lead.lead_id)}">Save</button>
        ${converted ? `<button type="button" data-lead-job-id="${escapeHtml(lead.converted_job_id)}">View package</button>` : ""}
        <button type="button" data-lead-action="convert" data-lead-id="${escapeHtml(lead.lead_id)}" ${converted || lead.status === "archived" ? "disabled" : ""}>Generate estimate</button>
        <button type="button" data-lead-action="archive" data-lead-id="${escapeHtml(lead.lead_id)}" ${lead.status === "archived" ? "disabled" : ""}>Archive</button>
      </span>
    `;
    leadList.appendChild(item);
  }
}

function leadStatusOption(current, value, label) {
  return `<option value="${value}" ${current === value ? "selected" : ""}>${label}</option>`;
}

function labelForLeadType(value) {
  if (value === "pv_only") {
    return "Solar only";
  }
  if (value === "not_sure") {
    return "Not sure yet";
  }
  return "Solar + battery";
}

function formatLeadDate(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

leadStatus.addEventListener("change", loadLeads);

leadQuery.addEventListener("input", () => {
  window.clearTimeout(leadQuery._timer);
  leadQuery._timer = window.setTimeout(loadLeads, 250);
});

leadList.addEventListener("click", async (event) => {
  const jobButton = event.target.closest("[data-lead-job-id]");
  if (jobButton) {
    try {
      const response = await apiFetch(`/api/jobs/${encodeURIComponent(jobButton.dataset.leadJobId)}`);
      const state = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(state));
      }
      renderJobState(state);
      if (state.result) {
        renderResult(state.result);
        statusEl.textContent = `Viewed project ${state.job_id}`;
      }
    } catch (error) {
      statusEl.textContent = error.message;
      statusEl.classList.add("error");
      renderError(error.message);
    }
    return;
  }
  const actionButton = event.target.closest("[data-lead-action]");
  if (!actionButton) {
    return;
  }
  const action = actionButton.dataset.leadAction;
  const leadId = actionButton.dataset.leadId;
  clearError();
  try {
    if (action === "save") {
      actionButton.disabled = true;
      actionButton.textContent = "Saving...";
      const response = await apiFetch(`/api/leads/${encodeURIComponent(leadId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          status: document.querySelector(`[data-lead-status="${CSS.escape(leadId)}"]`)?.value || "new",
          notes: document.querySelector(`[data-lead-note="${CSS.escape(leadId)}"]`)?.value || "",
          mark_contacted: false,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(data));
      }
      statusEl.textContent = `Saved lead ${leadId}`;
      await loadLeads();
      return;
    }
    if (action === "archive") {
      actionButton.disabled = true;
      actionButton.textContent = "Archiving...";
      const response = await apiFetch(`/api/leads/${encodeURIComponent(leadId)}/archive`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(data));
      }
      statusEl.textContent = `Archived lead ${leadId}`;
      await loadLeads();
      return;
    }
    if (action === "convert") {
      actionButton.disabled = true;
      actionButton.textContent = "Generating...";
      const response = await apiFetch(`/api/leads/${encodeURIComponent(leadId)}/convert`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(data));
      }
      await loadLeads();
      setBusy(true, `Generating estimate package from lead ${leadId}.`);
      pollJob(data.job.job_id);
    }
  } catch (error) {
    actionButton.disabled = false;
    actionButton.textContent = {
      save: "Save",
      archive: "Archive",
      convert: "Generate estimate",
    }[action] || "Retry";
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
});

function renderReadiness(readiness) {
  const counts = readiness.counts || {};
  const reviewItems = readiness.review_items || [];
  const gate = readiness.gate || {};
  const blockers = gate.blockers || [];
  const requiredReviews = gate.required_artifact_reviews || [];
  const requiredReviewCount = Number(gate.required_artifact_review_count || requiredReviews.length || 0);
  const pendingReviewCount = Number(gate.pending_required_artifact_review_count || 0);
  const approvedReviewCount = Math.max(0, requiredReviewCount - pendingReviewCount);
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
      <span>${escapeHtml(gate.level || (readiness.needs_review ? "Internal review" : "AHJ-ready candidate"))}</span>
    </div>
    <div class="gate-card ${gate.can_submit_to_ahj ? "pass" : "warn"}">
      <strong>${escapeHtml(gate.level || "Internal review")}</strong>
      <span>${gate.can_submit_to_ahj ? "Candidate package may proceed to formal AHJ review." : `Next: ${escapeHtml(gate.next_level || "AHJ-ready candidate")}`}</span>
    </div>
    <div class="gate-card ${pendingReviewCount ? "warn" : "pass"}">
      <strong>Artifact reviews</strong>
      <span>${requiredReviewCount ? `${approvedReviewCount}/${requiredReviewCount} required artifacts approved` : "No required artifact reviews for selected outputs"}</span>
    </div>
    <dl class="readiness-counts">
      <dt>Ready</dt><dd>${counts.ready || 0}</dd>
      <dt>Simulated</dt><dd>${counts.simulated || 0}</dd>
      <dt>Missing</dt><dd>${counts.missing || 0}</dd>
      <dt>N/A</dt><dd>${counts.not_applicable || 0}</dd>
    </dl>
    ${requiredReviews.length ? `
      <ul class="gate-list handoff-review-list">
        ${requiredReviews.slice(0, 8).map((item) => `
          <li>
            <span class="${item.status === "approved_internal" ? "review-approved" : "review-pending"}">${escapeHtml(reviewStatusLabel(item.status))}</span>
            <em>${escapeHtml(item.label || item.path || "")}</em>
          </li>
        `).join("")}
      </ul>
    ` : ""}
    <ul class="gate-list">
      ${blockers.slice(0, 6).map((item) => `
        <li>
          <span>${escapeHtml(item.field || item.key)}</span>
          <em>${escapeHtml(item.detail || "")}</em>
        </li>
      `).join("") || "<li><span>Gate</span><em>No AHJ-ready blockers detected</em></li>"}
    </ul>
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

async function runPackageQa() {
  if (!currentJobId) {
    return;
  }
  runPackageQaButton.disabled = true;
  runPackageQaButton.textContent = "Running...";
  statusEl.textContent = "Running package QA.";
  try {
    const response = await apiFetch(`/api/jobs/${currentJobId}/qa`, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    renderPackageQa(data.package_qa || {});
    renderDeliveryPackage(data.files || []);
    renderPreviews(data.files || []);
    renderFiles(data.files || []);
    statusEl.textContent = "Package QA complete. Review handoff readiness before submission.";
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  } finally {
    runPackageQaButton.disabled = !currentJobId;
    runPackageQaButton.textContent = "Run package QA";
  }
}

function renderPackageQa(qa) {
  const hasQa = Boolean(qa && qa.status);
  packageQaEmpty.classList.toggle("hidden", hasQa);
  packageQaPanel.classList.toggle("hidden", !hasQa);
  if (!hasQa) {
    packageQaPanel.innerHTML = "";
    return;
  }
  const summary = qa.summary || {};
  const doctor = qa.doctor || {};
  const archive = qa.archive || {};
  const pdfs = qa.pdfs || {};
  const statusClass = qa.status === "PASS" ? "pass" : (qa.status === "FAIL" ? "fail" : "warn");
  const warnings = (doctor.warnings || []).slice(0, 5);
  const failures = (doctor.failures || []).slice(0, 5);
  packageQaPanel.innerHTML = `
    <div class="readiness-status ${statusClass}">
      <strong>${escapeHtml(qa.status)}</strong>
      <span>${escapeHtml(archive.status || "Archive pending")} · ${pdfs.total || 0} PDF artifact(s)</span>
    </div>
    <dl class="readiness-counts">
      <dt>Doctor fail</dt><dd>${summary.doctor_failed || 0}</dd>
      <dt>Doctor warn</dt><dd>${summary.doctor_warned || 0}</dd>
      <dt>PDF fail</dt><dd>${summary.pdf_failed || 0}</dd>
      <dt>PDF warn</dt><dd>${summary.pdf_warned || 0}</dd>
    </dl>
    <ul class="gate-list">
      ${failures.map((item) => `
        <li>
          <span>${escapeHtml(item.name)}</span>
          <em>${escapeHtml(item.detail || "")}</em>
        </li>
      `).join("") || warnings.map((item) => `
        <li>
          <span>${escapeHtml(item.name)}</span>
          <em>${escapeHtml(item.detail || "")}</em>
        </li>
      `).join("") || "<li><span>QA</span><em>No package QA failures detected</em></li>"}
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
  if (runtimeConfig.auth_required && !currentAccessToken()) {
    historyList.innerHTML = "";
    historyEmpty.textContent = "Enter an operator token to view recent projects.";
    historyEmpty.classList.remove("hidden");
    return;
  }
  historyEmpty.textContent = "No generated projects yet.";
  try {
    const response = await apiFetch(`/api/jobs${historyQueryString()}`);
    const data = await response.json();
    const jobs = data.jobs || [];
    historyList.innerHTML = "";
    historyEmpty.classList.toggle("hidden", jobs.length > 0);
    for (const job of jobs) {
      const item = document.createElement("li");
      const title = job.result?.summary?.project_name || job.job_id;
      const gateLevel = job.result?.readiness?.gate?.level || "not gated";
      const qaStatus = job.result?.package_qa?.status || "QA not run";
      item.innerHTML = `
        <button type="button" class="history-button" data-job-id="${job.job_id}">
          ${escapeHtml(title)}
        </button>
        <span class="history-meta">
          ${escapeHtml(gateLevel)} · ${escapeHtml(qaStatus)}
        </span>
        <span class="history-actions">
          <button type="button" data-job-action="load" data-job-id="${job.job_id}">Load form</button>
          <button type="button" data-job-action="rerun" data-job-id="${job.job_id}">Rerun package</button>
          <button type="button" data-job-action="delete" data-job-id="${job.job_id}">Delete</button>
        </span>
      `;
      historyList.appendChild(item);
    }
  } catch {
    historyEmpty.classList.remove("hidden");
  }
}

function historyQueryString() {
  const params = new URLSearchParams();
  if (historyStatus.value) {
    params.set("status", historyStatus.value);
  }
  if (historyQuery.value.trim()) {
    params.set("q", historyQuery.value.trim());
  }
  if (historyFrom.value) {
    params.set("created_from", historyFrom.value);
  }
  if (historyTo.value) {
    params.set("created_to", historyTo.value);
  }
  if (historyAll.checked) {
    params.set("all_jobs", "true");
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

for (const element of [historyStatus, historyFrom, historyTo, historyAll]) {
  element.addEventListener("change", loadHistory);
}

historyQuery.addEventListener("input", () => {
  window.clearTimeout(historyQuery._timer);
  historyQuery._timer = window.setTimeout(loadHistory, 250);
});

historyRefresh.addEventListener("click", loadHistory);

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
      statusEl.textContent = `Loaded form from project ${jobId}`;
      return;
    }
    if (action === "rerun") {
      const response = await apiFetch(`/api/jobs/${jobId}/rerun`, { method: "POST" });
      const state = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(state));
      }
      setBusy(true, `Rerunning package from project ${jobId}.`);
      pollJob(state.job_id);
      return;
    }
    if (action === "delete") {
      const response = await apiFetch(`/api/jobs/${jobId}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(data));
      }
      statusEl.textContent = `Deleted project ${jobId}`;
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
      statusEl.textContent = `Viewed project ${state.job_id}`;
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
  renderValidation([], ["Loaded a prior project form. Reattach file uploads before rerunning with new source materials."]);
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
  button.textContent = isBusy ? "Generating package..." : "Generate estimate package";
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
