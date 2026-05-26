const form = document.querySelector("#project-form");
const button = document.querySelector("#generate");
const preflightButton = document.querySelector("#preflight");
const statusEl = document.querySelector("#status");
const draftStatus = document.querySelector("#draft-status");
const wizardBackButton = document.querySelector("#wizard-back");
const wizardContinueButton = document.querySelector("#wizard-continue");
const saveDraftButton = document.querySelector("#save-draft");
const stepFeedback = document.querySelector("#step-feedback");
const stepFeedbackPanel = document.querySelector(".step-feedback-panel");
const stepFeedbackTitle = document.querySelector("#step-feedback-title");
const checklistStatus = document.querySelector("#checklist-status");
const checklistStatusTitle = document.querySelector("#checklist-status-title");
const resultsAside = document.querySelector(".results");
const sideConsoleTitle = document.querySelector("#side-console-title");
const sideConsoleLink = document.querySelector("#side-console-link");
const operatorTools = document.querySelector("#operator-tools");
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
const leadDigest = document.querySelector("#lead-digest");
const leadMetricsPanel = document.querySelector("#lead-metrics-panel");
const leadDraftPanel = document.querySelector("#lead-draft-panel");
const leadDraftSubject = document.querySelector("#lead-draft-subject");
const leadDraftBody = document.querySelector("#lead-draft-body");
const leadDraftMailto = document.querySelector("#lead-draft-mailto");
const leadNotificationPanel = document.querySelector("#lead-notification-panel");
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
const lookupButton = document.querySelector("#lookup-address");
const lookupMode = document.querySelector("#lookup-mode");
const lookupPanel = document.querySelector("#lookup-panel");
const roofPreviewButton = document.querySelector("#roof-preview-generate");
const roofPreviewPanel = document.querySelector("#roof-preview-panel");
const addressSample = document.querySelector("#address-sample");
const wizardLinks = [...document.querySelectorAll("[data-wizard-step]")];
const wizardSections = [...document.querySelectorAll(".flow-section")];

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
const monthlyUsageMode = document.querySelector("#monthly-usage-mode");
const monthlyAverageField = document.querySelector("#monthly-average-field");
const monthlyDetailField = document.querySelector("#monthly-detail-field");
const usageBillHint = document.querySelector("#usage-bill-hint");
const batteryLocationBlock = document.querySelector("#battery-location-block");
const batteryInstallLocation = document.querySelector('select[name="battery_install_location"]');
const batteryClearanceNote = document.querySelector("#battery-clearance-note");
const selfConsumptionProfile = document.querySelector("#self-consumption-profile");
const selfConsumptionFraction = document.querySelector("#self-consumption-fraction");
const selfConsumptionNote = document.querySelector("#self-consumption-note");
const roofAssumptionSummary = document.querySelector("#roof-assumption-summary");
const reviewSummary = document.querySelector("#review-summary");
const packageLevelFields = [...document.querySelectorAll('input[name="package_level"]')];
const artifactReviewWorkbench = document.querySelector("#artifact-review-workbench");
const artifactReviewTabs = document.querySelector("#artifact-review-tabs");
const artifactReviewPage = document.querySelector("#artifact-review-page");
const artifactReviewCounter = document.querySelector("#artifact-review-counter");
const artifactReviewPosition = document.querySelector("#artifact-review-position");
const artifactReviewPrev = document.querySelector("#artifact-review-prev");
const artifactReviewNext = document.querySelector("#artifact-review-next");
const reviewFocusBar = document.querySelector("#review-focus-bar");
const reviewStatusDrawer = document.querySelector("#review-status-drawer");
const reviewStatusDrawerBody = document.querySelector("#review-status-drawer-body");

let activePoll = null;
let roofPreviewPoll = null;
let currentFiles = [];
let currentPreviewItems = [];
let currentJobId = "";
let currentReadiness = {};
let currentResultData = null;
let artifactReviewPages = [];
let artifactReviewPageIndex = 0;
let artifactReviews = {};
let lastLookupRoofCandidates = [];
let lastLookupRoofSections = [];
let lastEe4Trace = null;
let runtimeConfig = { auth_required: false };
let currentStepIndex = 0;
let wizardStepStates = {};
let draftSaveTimer = null;
let localDraftRestored = false;

const wizardDraftKey = "tge_pvess_wizard_draft_v1";
const wizardStepOrder = [
  "project-basics",
  "site-field-data",
  "system-equipment",
  "service-costs",
  "source-materials",
  "package-outputs",
];
const wizardSteps = {
  "project-basics": {
    title: "Project & Address",
    summary: "Select the project scope, enter the U.S. address, then confirm local utility, AHJ, and code basis when available.",
    readyLabel: "Address verified.",
  },
  "site-field-data": {
    title: "Roof & Usage",
    summary: "Confirm target roof imagery, usage, ESS location, and field basics before equipment and package generation.",
    readyLabel: "Roof and usage data ready.",
  },
  "system-equipment": {
    title: "System Equipment",
    summary: "Select one inverter family, module count, string count, battery mode, and equipment quantities.",
    readyLabel: "Equipment selected.",
  },
  "service-costs": {
    title: "Electrical & Roof Costs",
    summary: "Confirm service amperage, interconnection preference, utility tariff, usage behavior, and cost assumptions.",
    readyLabel: "Electrical assumptions ready.",
  },
  "source-materials": {
    title: "Roof & Evidence",
    summary: "Upload or explicitly mark simulated photos, utility bills, structural letters, and equipment spec sheets.",
    readyLabel: "Evidence status ready.",
  },
  "package-outputs": {
    title: "Review & Generate",
    summary: "Run readiness, select deliverables, review blocking issues, and generate the estimate package.",
    readyLabel: "Ready for readiness check and generation review.",
  },
};

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

const inverterBatteryPairings = {
  megarevo: "pytes_v16",
  megarova: "pytes_v16",
  hoymiles: "hoymiles_hbx_10lv_usg1",
  hoymile: "hoymiles_hbx_10lv_usg1",
  growatt: "growatt_apx_20kwh",
};

const legacySelectValues = {
  inverter_choice: {
    megarova: "megarevo",
    hoymile: "hoymiles",
  },
  battery_choice: {
    inhouse_16kwh_hv: "pytes_v16",
    paizhi_16kwh_lfp: "pytes_v16",
  },
};

const satelliteCropModes = [
  {
    value: "target",
    label: "Target roof only",
    description: "Tightest crop for dense neighborhoods and townhome rows.",
  },
  {
    value: "tight",
    label: "Tight",
    description: "Focuses on the selected roof with limited nearby context.",
  },
  {
    value: "standard",
    label: "Standard",
    description: "Keeps adjacent roof context for orientation checks.",
  },
  {
    value: "wide",
    label: "Wide",
    description: "Shows the full Google Solar context frame.",
  },
];

const packageOutputPresets = {
  estimate: {
    out_customer: true,
    out_permit: false,
    out_dxf: false,
    out_labels: false,
    out_qet: false,
  },
  engineering_review: {
    out_customer: true,
    out_permit: true,
    out_dxf: true,
    out_labels: true,
    out_qet: false,
  },
  ahj_ready: {
    out_customer: true,
    out_permit: true,
    out_dxf: true,
    out_labels: true,
    out_qet: false,
  },
};

const templates = {
  pv_ess: {
    modules: 32,
    strings: 4,
    module_choice: "talesun_tp7g54m_415",
    inverter_choice: "growatt",
    battery_choice: "growatt_apx_20kwh",
    battery_quantity: 1,
    interconnection_method: "supply_side_tap",
    self_consumption_profile: "pv_ess_typical",
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
    self_consumption_profile: "pv_only_typical",
    self_consumption_fraction: 0.40,
  },
  retrofit_existing_pv: {
    modules: 20,
    strings: 2,
    module_choice: "rec_alpha_pure_410",
    inverter_choice: "megarevo",
    battery_choice: "pytes_v16",
    battery_quantity: 1,
    interconnection_method: "sum_rule",
    self_consumption_profile: "high_daytime",
    self_consumption_fraction: 0.65,
  },
};

const dfwResidentialMonthlyKwh = [
  880, 780, 720, 820, 1050, 1450, 1700, 1750, 1450, 1050, 820, 860,
];

const addressSamples = {
  glasshouse: {
    project_name: "Frisco PV + ESS Package",
    address_line1: "7652 Glasshouse Walk",
    address_line2: "",
    address_city: "Frisco",
    address_state: "TX",
    address_postal_code: "75035",
    site_address: "7652 Glasshouse Walk, Frisco, TX 75035",
    location: "Frisco, TX",
    ahj: "Frisco TX",
    utility: "Oncor Electric Delivery",
    monthly_usage_mode: "monthly_detail",
    monthly_kwh_text: dfwResidentialMonthlyKwh.join(", "),
  },
  crossvine: {
    project_name: "Mansfield Crossvine PV + ESS Package",
    address_line1: "905 Crossvine Drive",
    address_line2: "",
    address_city: "Mansfield",
    address_state: "TX",
    address_postal_code: "76063",
    site_address: "905 Crossvine Drive, Mansfield, TX 76063",
    location: "Mansfield, TX",
    ahj: "City of Mansfield Building Safety",
    utility: "Oncor Electric Delivery",
    monthly_usage_mode: "monthly_detail",
    monthly_kwh_text: dfwResidentialMonthlyKwh.join(", "),
  },
  green_circle: {
    project_name: "Mansfield Green Circle PV + ESS Package",
    address_line1: "2806 Green Circle Drive",
    address_line2: "",
    address_city: "Mansfield",
    address_state: "TX",
    address_postal_code: "76063",
    site_address: "2806 Green Circle Drive, Mansfield, TX 76063",
    location: "Mansfield, TX",
    ahj: "City of Mansfield Building Safety",
    utility: "Oncor Electric Delivery",
    installer_address: "2806 Green Cir Dr, Mansfield, TX",
    monthly_usage_mode: "monthly_detail",
    monthly_kwh_text: dfwResidentialMonthlyKwh.join(", "),
  },
};

async function submitProjectForm(event) {
  event?.preventDefault?.();
  if (button.disabled) {
    return;
  }
  clearError();

  const formData = new FormData(form);
  const payload = buildPayload(formData);
  const validation = validatePayload(payload);
  renderValidation(validation.errors, validation.warnings);
  if (validation.errors.length > 0) {
    const stepValidation = validateStep("package-outputs", payload);
    renderStepValidation(stepValidation);
    if (stepValidation.errors[0]) {
      focusIssueField(stepValidation.errors[0]);
    }
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
}

preflightButton.addEventListener("click", runPreflight);
button.addEventListener("click", submitProjectForm);
form.addEventListener("submit", submitProjectForm);
fileFilter.addEventListener("change", () => renderFiles(currentFiles));
lookupButton.addEventListener("click", runAddressLookup);
lookupPanel.addEventListener("click", handleLookupCandidateClick);
roofPreviewButton.addEventListener("click", runRoofPreview);
roofPreviewPanel.addEventListener("click", handleRoofPreviewClick);
previewPanel.addEventListener("click", handlePreviewClick);
fileList.addEventListener("change", handleArtifactReviewChange);
runPackageQaButton.addEventListener("click", runPackageQa);
artifactReviewWorkbench.addEventListener("click", handleArtifactReviewPagerClick);
artifactReviewWorkbench.addEventListener("change", handleArtifactReviewChange);
reviewFocusBar.addEventListener("click", handleReviewFocusBarClick);
reviewStatusDrawer.addEventListener("click", handleReviewStatusDrawerClick);
leadRefresh.addEventListener("click", loadLeads);
leadExport.addEventListener("click", exportLeadsCsv);
wizardBackButton.addEventListener("click", goToPreviousStep);
wizardContinueButton.addEventListener("click", continueWizard);
saveDraftButton.addEventListener("click", () => saveDraft({ manual: true }));
for (const link of wizardLinks) {
  link.addEventListener("click", handleWizardNavClick);
}
form.addEventListener("input", handleWizardFormInput);
form.addEventListener("change", handleWizardFormInput);
projectTemplate.addEventListener("change", () => applyTemplate(projectTemplate.value));
addressSample.addEventListener("change", () => applyAddressSample(addressSample.value));
moduleChoice.addEventListener("change", syncModuleOption);
inverterChoice.addEventListener("change", syncInverterOption);
batteryChoice.addEventListener("change", syncBatteryOption);
batteryQtyInput.addEventListener("input", syncBatterySiteFields);
monthlyUsageMode.addEventListener("change", syncUsageMode);
batteryInstallLocation.addEventListener("change", syncBatterySiteFields);
selfConsumptionProfile.addEventListener("change", syncSelfConsumptionProfile);
for (const field of packageLevelFields) {
  field.addEventListener("change", syncPackagePreset);
}

setupFileUploadControls();
syncModuleOption();
syncInverterOption();
syncUsageMode();
syncBatteryOption({ preserveQuantity: true });
syncSelfConsumptionProfile();
syncRoofAssumptionSummary();
syncPackagePreset({ preserveOutputs: true });
restoreDraftFromLocal();
initWizard();
loadRuntimeConfig().then(() => {
  loadHistory();
  loadLeads();
});

async function loadRuntimeConfig() {
  try {
    const response = await fetch(requestUrl("/api/runtime-config"));
    if (response.ok) {
      runtimeConfig = await response.json();
    }
  } catch {
    runtimeConfig = { auth_required: false };
  }
}

function currentAccessToken() {
  return "";
}

function requestUrl(url) {
  const target = new URL(url, window.location.href);
  target.username = "";
  target.password = "";
  return target.toString();
}

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  return fetch(requestUrl(url), {
    ...options,
    headers,
  });
}

function storageGet(key) {
  try {
    return window.localStorage?.getItem(key) || "";
  } catch {
    return "";
  }
}

function storageSet(key, value) {
  try {
    window.localStorage?.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function storageRemove(key) {
  try {
    window.localStorage?.removeItem(key);
  } catch {
    // localStorage can be unavailable in restricted browser contexts.
  }
}

function withAuthUrl(url) {
  return requestUrl(url);
}

function initWizard() {
  const requestedStep = new URLSearchParams(window.location.search).get("step") || window.location.hash.replace("#", "");
  const targetIndex = wizardStepOrder.includes(requestedStep)
    ? wizardStepOrder.indexOf(requestedStep)
    : currentStepIndex;
  setWizardStep(targetIndex, { validate: false, replaceUrl: false });
}

function currentStepId() {
  return wizardStepOrder[currentStepIndex] || wizardStepOrder[0];
}

function handleWizardNavClick(event) {
  event.preventDefault();
  const stepId = event.currentTarget.dataset.wizardStep;
  const targetIndex = wizardStepOrder.indexOf(stepId);
  if (targetIndex < 0 || targetIndex === currentStepIndex) {
    return;
  }
  if (targetIndex > currentStepIndex && !recordCurrentStepValidation({ focus: true })) {
    return;
  }
  clearStepActionStatus();
  setWizardStep(targetIndex);
}

function goToPreviousStep() {
  if (currentStepIndex > 0) {
    setWizardStep(currentStepIndex - 1);
  }
}

function continueWizard() {
  if (!recordCurrentStepValidation({ focus: true })) {
    statusEl.textContent = "Fix the blocking items before continuing.";
    statusEl.classList.add("error");
    return;
  }
  clearStepActionStatus();
  if (currentStepIndex < wizardStepOrder.length - 1) {
    setWizardStep(currentStepIndex + 1);
  } else {
    runPreflight();
  }
}

function setWizardStep(index, options = {}) {
  currentStepIndex = Math.max(0, Math.min(index, wizardStepOrder.length - 1));
  const stepId = currentStepId();
  for (const section of wizardSections) {
    section.classList.toggle("active-step", section.id === stepId);
  }
  for (const link of wizardLinks) {
    const state = wizardStepStates[link.dataset.wizardStep] || "todo";
    link.classList.toggle("active", link.dataset.wizardStep === stepId);
    link.classList.toggle("valid", state === "valid");
    link.classList.toggle("warning", state === "warning");
    link.classList.toggle("error", state === "error");
  }
  wizardBackButton.disabled = currentStepIndex === 0;
  const isLast = currentStepIndex === wizardStepOrder.length - 1;
  wizardContinueButton.textContent = isLast ? "Run readiness" : "Continue";
  preflightButton.classList.add("hidden");
  button.classList.toggle("hidden", !isLast);
  updateSideConsoleMode(isLast);
  updateReviewFocusMode();
  renderCurrentStepValidation({ quiet: options.validate === false });
  if (options.replaceUrl !== false) {
    const url = new URL(window.location.href);
    url.searchParams.set("step", stepId);
    const nextUrl = `${url.pathname}?${url.searchParams.toString()}${url.hash}`;
    history.replaceState({}, "", nextUrl);
  }
  localAutosave();
}

function handleWizardFormInput(event) {
  if (event.target?.type === "file") {
    return;
  }
  if (event.target?.id === "self-consumption-profile") {
    syncSelfConsumptionProfile();
  }
  if ([
    "roof_pitch_deg",
    "roof_azimuth_deg",
    "roof_width_ft",
    "roof_height_ft",
  ].includes(event.target?.name)) {
    syncRoofAssumptionSummary();
  }
  if ([
    "address_line1",
    "address_line2",
    "address_city",
    "address_state",
    "address_postal_code",
    "site_address",
    "location",
  ].includes(event.target?.name)) {
    clearLookupRoofSections();
    markRoofPreviewStale("Address changed. Rebuild the roof preview before relying on the satellite outline.");
  }
  if (event.target?.name === "satellite_crop_mode") {
    markRoofPreviewStale("Satellite crop range changed. Rebuild the roof preview to use the selected range.");
  }
  window.clearTimeout(draftSaveTimer);
  draftSaveTimer = window.setTimeout(() => {
    localAutosave();
    renderCurrentStepValidation({ quiet: false });
  }, 180);
}

function recordCurrentStepValidation(options = {}) {
  const payload = buildPayload(new FormData(form));
  const validation = validateStep(currentStepId(), payload);
  const state = validation.errors.length ? "error" : (validation.warnings.length ? "warning" : "valid");
  wizardStepStates[currentStepId()] = state;
  renderStepValidation(validation);
  updateWizardNavStates();
  if (validation.errors.length && options.focus) {
    focusIssueField(validation.errors[0]);
  }
  return validation.errors.length === 0;
}

function renderCurrentStepValidation(options = {}) {
  const payload = buildPayload(new FormData(form));
  const validation = validateStep(currentStepId(), payload);
  const isReviewStep = currentStepId() === "package-outputs";
  if (isReviewStep) {
    renderReviewSummary(payload);
  }
  if (!options.quiet || isReviewStep) {
    renderStepValidation(validation);
  } else {
    renderStepValidation({
      ...validation,
      errors: [],
      warnings: [],
      passes: validation.passes.slice(0, 3),
    });
  }
}

function updateWizardNavStates() {
  for (const link of wizardLinks) {
    const state = wizardStepStates[link.dataset.wizardStep] || "todo";
    link.classList.toggle("valid", state === "valid");
    link.classList.toggle("warning", state === "warning");
    link.classList.toggle("error", state === "error");
    link.classList.toggle("active", link.dataset.wizardStep === currentStepId());
  }
}

function updateSideConsoleMode(isReviewStep) {
  resultsAside.classList.toggle("review-mode", isReviewStep);
  resultsAside.classList.toggle("checklist-mode", !isReviewStep);
  if (operatorTools) {
    operatorTools.hidden = !isReviewStep;
    if (!isReviewStep) {
      operatorTools.open = false;
    }
  }
  sideConsoleTitle.textContent = isReviewStep
    ? sideConsoleTitle.dataset.reviewTitle
    : sideConsoleTitle.dataset.checklistTitle;
  sideConsoleLink.textContent = isReviewStep ? "Go to outputs" : "Go to review";
  sideConsoleLink.href = isReviewStep ? "#package-outputs" : "#package-outputs";
}

function updateReviewFocusMode() {
  const enabled = currentStepId() === "package-outputs" && Boolean(currentResultData);
  document.body.classList.toggle("review-focus-mode", enabled);
  if (reviewFocusBar) {
    reviewFocusBar.classList.toggle("hidden", !enabled);
  }
  if (!enabled) {
    closeReviewStatusDrawer();
  }
}

function renderStepValidation(validation) {
  markIssueFields(validation);
  renderChecklistStatus(validation);
  const step = wizardSteps[currentStepId()];
  const isReviewStep = currentStepId() === "package-outputs";
  const issues = [
    ...validation.errors.map((item) => ({ ...item, level: "error", label: "Error" })),
    ...validation.warnings.map((item) => ({ ...item, level: "warning", label: "Warning" })),
  ];
  if (!isReviewStep && issues.length === 0) {
    stepFeedbackPanel.classList.add("hidden");
    stepFeedback.innerHTML = "";
    return;
  }

  stepFeedbackPanel.classList.remove("hidden");
  stepFeedbackTitle.textContent = isReviewStep ? "Review checklist" : "Needs attention";
  const visiblePasses = isReviewStep ? validation.passes : [];
  if (isReviewStep) {
    renderReviewChecklist(step, issues, visiblePasses);
    return;
  }
  stepFeedback.innerHTML = `
    <div class="step-feedback-head">
      <strong>${escapeHtml(step.title)}</strong>
      <span>${escapeHtml(step.summary)}</span>
    </div>
    <ul class="step-feedback-list">
      ${issues.map((item) => `
        <li class="${item.level}">
          <strong>${item.label}</strong>
          ${escapeHtml(item.message)}
        </li>
      `).join("")}
      ${visiblePasses.map((item) => `
        <li class="pass">
          <strong>Passed</strong>
          ${escapeHtml(item.message || item)}
        </li>
      `).join("")}
    </ul>
  `;
}

function renderReviewChecklist(step, issues, passes) {
  const groups = reviewIssueGroups(issues, passes);
  stepFeedback.innerHTML = `
    <div class="step-feedback-head">
      <strong>${escapeHtml(step.title)}</strong>
      <span>${escapeHtml(step.summary)}</span>
    </div>
    ${groups.map((group) => `
      <div class="step-feedback-group ${group.kind}">
        <h3>${escapeHtml(group.title)}</h3>
        <ul class="step-feedback-list">
          ${group.items.map((item) => `
            <li class="${escapeHtml(item.level)}">
              <strong>${escapeHtml(item.label)}</strong>
              ${escapeHtml(item.message || item)}
            </li>
          `).join("")}
        </ul>
      </div>
    `).join("")}
  `;
}

function reviewIssueGroups(issues, passes) {
  const blocking = issues.filter((item) => item.level === "error");
  const warnings = issues.filter((item) => item.level === "warning");
  const ahjFields = new Set([
    "site_data_source",
    "site_photos_auto",
    "meter_number",
    "meter_location",
    "meter_esid",
    "battery_install_location",
    "engineer_firm",
    "roof_info_type",
    "msp_x_ft",
  ]);
  const ahj = warnings.filter((item) => ahjFields.has(item.field));
  const estimate = warnings.filter((item) => !ahjFields.has(item.field));
  const groups = [];
  groups.push({
    title: blocking.length ? "Must fix before generation" : "Must fix before generation",
    kind: blocking.length ? "error" : "pass",
    items: blocking.length
      ? blocking
      : [{ level: "pass", label: "Ready", message: "No blocking errors for estimate generation." }],
  });
  if (estimate.length) {
    groups.push({
      title: "Can generate, but estimate quality is affected",
      kind: "warning",
      items: estimate,
    });
  }
  if (ahj.length) {
    groups.push({
      title: "Required before AHJ-ready handoff",
      kind: "warning",
      items: ahj,
    });
  }
  groups.push({
    title: "Package QA",
    kind: "pass",
    items: [
      { level: "pass", label: "Next", message: "Run Package QA after generation, then approve required artifacts before AHJ handoff." },
      ...passes.slice(0, 3).map((item) => ({ ...item, level: "pass", label: "Passed" })),
    ],
  });
  return groups;
}

function renderChecklistStatus(validation) {
  const errorCount = validation.errors?.length || 0;
  const warningCount = validation.warnings?.length || 0;
  const passCount = validation.passes?.length || 0;
  const isReviewStep = currentStepId() === "package-outputs";
  const step = wizardSteps[currentStepId()];
  const stepNumber = wizardStepOrder.indexOf(currentStepId()) + 1;
  checklistStatusTitle.textContent = isReviewStep ? "Review status" : "Current step";
  if (isReviewStep && currentResultData) {
    const counts = artifactReviewCounts();
    const gate = currentReadiness?.gate || {};
    checklistStatus.innerHTML = `
      <span class="step-status-eyebrow">Step ${stepNumber} of ${wizardStepOrder.length}</span>
      <strong>${escapeHtml(gate.level || "Package generated")}</strong>
      <p>${counts.required ? `${counts.approved}/${counts.required} required artifact approvals complete.` : "Generated artifacts are ready for optional review."}</p>
      <div class="checklist-counts">
        <span class="${gate.can_submit_to_ahj ? "pass" : "warning"}">${gate.can_submit_to_ahj ? "AHJ-ready" : "review needed"}</span>
        <span>${artifactReviewPages.length || 0} pages</span>
        <span class="${counts.required && counts.approved < counts.required ? "warning" : "pass"}">${counts.required ? `${counts.required - counts.approved} remaining` : "no required approvals"}</span>
      </div>
    `;
    return;
  }
  const action = errorCount
    ? `Fix ${errorCount} blocking item${errorCount === 1 ? "" : "s"} before continuing.`
    : step.readyLabel;
  const detail = errorCount
    ? "The first blocking field is focused when you click Continue."
    : (warningCount
      ? "Warnings do not block this estimate, but they remain visible for review."
      : (isReviewStep ? "Run readiness, review evidence, then generate the package." : `${passCount} checks passed.`));
  checklistStatus.innerHTML = `
    <span class="step-status-eyebrow">Step ${stepNumber} of ${wizardStepOrder.length}</span>
    <strong>${escapeHtml(action)}</strong>
    <p>${escapeHtml(detail)}</p>
    <div class="checklist-counts">
      <span class="${errorCount ? "error" : ""}">${errorCount} error${errorCount === 1 ? "" : "s"}</span>
      <span class="${warningCount ? "warning" : ""}">${warningCount} warning${warningCount === 1 ? "" : "s"}</span>
      <span class="${passCount ? "pass" : ""}">${passCount} check${passCount === 1 ? "" : "s"} passed</span>
    </div>
  `;
}

function markIssueFields(validation) {
  for (const label of form.querySelectorAll(".field-invalid, .field-warning")) {
    label.classList.remove("field-invalid", "field-warning");
  }
  for (const message of form.querySelectorAll(".field-message")) {
    message.remove();
  }
  const errorFields = new Set((validation.errors || []).map((item) => item.field).filter(Boolean));
  for (const item of validation.errors || []) {
    markField(item.field, "field-invalid", item.message);
  }
  for (const item of validation.warnings || []) {
    if (errorFields.has(item.field)) {
      continue;
    }
    markField(item.field, "field-warning", item.message);
  }
}

function markField(name, className, message) {
  if (!name) {
    return;
  }
  const field = form.elements[name] || document.querySelector(`[name="${CSS.escape(name)}"]`);
  const wrapper = field?.closest?.("label");
  if (wrapper) {
    wrapper.classList.add(className);
    if (message) {
      const hint = document.createElement("span");
      hint.className = `field-message ${className === "field-invalid" ? "error" : "warning"}`;
      hint.textContent = message;
      wrapper.appendChild(hint);
    }
  }
}

function focusIssueField(issue) {
  const field = issue?.field ? (form.elements[issue.field] || document.querySelector(`[name="${CSS.escape(issue.field)}"]`)) : null;
  const step = field?.closest?.(".flow-section")?.id;
  if (step && step !== currentStepId()) {
    setWizardStep(wizardStepOrder.indexOf(step));
  }
  if (field && typeof field.focus === "function") {
    field.focus({ preventScroll: false });
  }
}

function issue(field, message) {
  return { field, message };
}

function validateStep(stepId, payload) {
  const errors = [];
  const warnings = [];
  const passes = [];
  const modules = Number(payload.modules || 0);
  const strings = Number(payload.strings || 0);
  const moduleWatts = Number(moduleChoice.selectedOptions[0]?.dataset.watts || payload.module_power_w || 0);
  const inverterAmps = Number(payload.inverter_ac_output_a || 0);
  const inverterQty = Number(payload.inverter_quantity || 1);
  const dcKw = modules * moduleWatts / 1000;
  const acKw = inverterAmps * 240 * inverterQty / 1000;

  if (stepId === "project-basics") {
    if (!payload.site_address) errors.push(issue("address_line1", "Street address is required before lookup or generation."));
    if (!payload.location) errors.push(issue("address_city", "City and state are required for climate, rate, and AHJ assumptions."));
    if (!form.elements.address_postal_code?.value.trim()) {
      errors.push(issue("address_postal_code", "ZIP code is required for a standard U.S. project address."));
    }
    if (!payload.ahj) warnings.push(issue("ahj", "AHJ is not filled yet; check the address or confirm it later."));
    if (!payload.utility) warnings.push(issue("utility", "Utility is not filled yet; check the address or confirm it later."));
    if (payload.site_address) passes.push(issue("address_line1", "U.S. address captured for project lookup and output title block."));
    if (payload.project_name) passes.push(issue("project_name", `Project name: ${payload.project_name}.`));
    if (payload.nec_edition) passes.push(issue("nec_edition", `Code basis set to NEC ${payload.nec_edition}.`));
  }

  if (stepId === "site-field-data") {
    const usageMode = payload.monthly_usage_mode || "local_default";
    if (usageMode === "average" && (!payload.monthly_kwh || payload.monthly_kwh.length !== 12)) {
      errors.push(issue("monthly_kwh_average", "Enter a positive average monthly kWh value."));
    }
    if (usageMode === "monthly_detail" && (!payload.monthly_kwh || payload.monthly_kwh.length !== 12)) {
      errors.push(issue("monthly_kwh_text", "Enter exactly 12 monthly kWh values."));
    }
    if (usageMode === "upload_bill") {
      passes.push(issue("monthly_usage_mode", "Utility bill upload will be handled in Evidence."));
    }
    if (payload.battery_install_location === "garage" || payload.battery_install_location === "indoor") {
      if (Number(payload.distance_to_doorway_ft || 0) > 0 && Number(payload.distance_to_doorway_ft || 0) < 3) {
        errors.push(issue("distance_to_doorway_ft", "Indoor/garage ESS doorway setback should be at least 3 ft."));
      }
      if (Number(payload.distance_to_window_ft || 0) > 0 && Number(payload.distance_to_window_ft || 0) < 3) {
        errors.push(issue("distance_to_window_ft", "Indoor/garage ESS window setback should be at least 3 ft."));
      }
      if (Number(payload.distance_to_egress_ft || 0) > 0 && Number(payload.distance_to_egress_ft || 0) < 3) {
        errors.push(issue("distance_to_egress_ft", "Indoor/garage ESS egress setback should be at least 3 ft."));
      }
    }
    if (payload.monthly_kwh?.length === 12) passes.push(issue("monthly_usage_mode", "Usage estimate is ready."));
    if (payload.ee4_trace?.roof_outline) {
      passes.push(issue("roof-preview-generate", "Roof topology is saved for downstream permit sheets."));
    } else {
      warnings.push(issue("roof-preview-generate", "Build and accept the roof topology in this step before relying on permit drawings."));
    }
    if (payload.battery_choice === "none" || Number(payload.battery_quantity || 0) === 0) {
      passes.push(issue("battery_install_location", "Battery location is not needed for PV-only scope."));
    } else if (payload.battery_install_location && payload.battery_install_location !== "unknown") {
      passes.push(issue("battery_install_location", "Battery install area is captured."));
    } else {
      passes.push(issue("battery_install_location", "Battery install area can be confirmed later."));
    }
    if (payload.roof_info_type) passes.push(issue("roof_info_type", "Roof material is captured."));
  }

  if (stepId === "system-equipment") {
    if (modules < 1) errors.push(issue("modules", "At least one module is required."));
    if (strings < 1) errors.push(issue("strings", "At least one string is required."));
    if (strings > 0 && modules > 0 && modules % strings !== 0) {
      errors.push(issue("strings", "Module count must divide evenly by string count."));
    }
    if (payload.battery_choice === "none" && Number(payload.battery_quantity || 0) > 0) {
      errors.push(issue("battery_quantity", "Battery quantity must be 0 when No battery is selected."));
    }
    if (payload.battery_choice !== "none" && Number(payload.battery_quantity || 0) === 0) {
      warnings.push(issue("battery_quantity", "A battery model is selected but quantity is 0; this will generate PV-only economics."));
    }
    const pairedBattery = inverterBatteryPairings[payload.inverter_choice];
    if (
      pairedBattery
      && payload.battery_choice !== "none"
      && Number(payload.battery_quantity || 0) > 0
      && payload.battery_choice !== pairedBattery
    ) {
      errors.push(issue("battery_choice", "Battery package must match the selected inverter brand."));
    }
    if (acKw > 0) {
      const ratio = dcKw / acKw;
      if (ratio > 1.7) {
        errors.push(issue("modules", `DC/AC ratio is ${ratio.toFixed(2)}; reduce modules or add inverter capacity.`));
      } else if (ratio > 1.45) {
        warnings.push(issue("modules", `DC/AC ratio is ${ratio.toFixed(2)}; engineering review recommended.`));
      }
    }
    if (modules && strings && modules % strings === 0) passes.push(issue("strings", `${modules} modules across ${strings} string(s).`));
    if (payload.inverter_choice) passes.push(issue("inverter_choice", "One inverter brand/model family is selected."));
  }

  if (stepId === "service-costs") {
    if (Number(payload.main_panel_a || 0) <= 0) errors.push(issue("main_panel_a", "Main breaker amperage is required."));
    if (Number(payload.busbar_a || 0) <= 0) errors.push(issue("busbar_a", "Busbar amperage is required."));
    if (payload.existing_solar_status === "present") {
      warnings.push(issue("existing_solar_status", "Existing solar is present; engineering must verify existing backfeed before final interconnection."));
    } else if (payload.existing_solar_status === "not_sure") {
      warnings.push(issue("existing_solar_status", "Existing solar status is not confirmed; panel photos should verify it."));
    }
    if (Number(payload.self_consumption_fraction || 0) < 0 || Number(payload.self_consumption_fraction || 0) > 1) {
      errors.push(issue("self_consumption_fraction", "Self-consumption must be between 0 and 1."));
    }
    if (Number(payload.pv_turnkey_usd_per_w || 0) <= 0) {
      errors.push(issue("pv_turnkey_usd_per_w", "PV turnkey $/W must be greater than 0."));
    }
    if (Number(payload.roof_width_ft || 0) <= 0 || Number(payload.roof_height_ft || 0) <= 0) {
      errors.push(issue("roof_width_ft", "Roof width and height must be greater than 0."));
    }
    if (payload.interconnection_method === "supply_side_tap") {
      passes.push(issue("interconnection_method", "Engineering review will select the interconnection path."));
    } else {
      warnings.push(issue("interconnection_method", "Non-supply-side interconnection selected; verify 705 busbar rules."));
    }
    if (payload.main_panel_a && payload.busbar_a) passes.push(issue("main_panel_a", "Service amperage assumptions are ready."));
    if (payload.export_tariff_model) passes.push(issue("export_tariff_model", "Utility export tariff selected."));
    if (Number(payload.pv_turnkey_usd_per_w || 0) > 0) passes.push(issue("pv_turnkey_usd_per_w", "Turnkey PV cost assumption is ready."));
  }

  if (stepId === "source-materials") {
    const requiredPhotoFields = ["front_elevation", "roof", "meter", "main_panel"];
    const hasIndividualCorePhotos = requiredPhotoFields.some((name) => fileInputHasValue(name));
    const hasBulkSitePhotos = fileInputHasValue("site_photos_auto");
    const hasSitePhotos = hasIndividualCorePhotos || hasBulkSitePhotos;
    if (payload.site_data_source === "simulated") {
      if (payload.package_level === "ahj_ready") {
        warnings.push(issue("site_data_source", "AHJ-ready handoff requires uploaded field evidence."));
      } else {
        passes.push(issue("site_data_source", "Quick estimate evidence selected. Field evidence can be added later for AHJ-ready handoff."));
      }
    }
    if (payload.site_data_source === "real" && !hasSitePhotos) {
      warnings.push(issue("site_photos_auto", "Field evidence mode is selected but no site photos are attached."));
    }
    if (!fileInputHasValue("utility_bill") && !payload.monthly_kwh?.length) {
      warnings.push(issue("utility_bill", "No utility bill or monthly usage is attached."));
    }
    if (payload.site_data_source === "real" && hasSitePhotos) {
      passes.push(issue("site_photos_auto", "Site photos are attached for classification and PV-7 review."));
    } else {
      passes.push(issue("site_data_source", "Evidence state is explicit for downstream handoff checks."));
    }
    passes.push(issue("", "Engineering documents are checked in Review before AHJ-ready handoff."));
  }

  if (stepId === "package-outputs") {
    const selectedOutputs = Object.values(payload.outputs || {}).filter(Boolean).length;
    if (!selectedOutputs) {
      errors.push(issue("", "Select at least one package output before generation."));
    }
    const full = validateAllSteps(payload, { includeReview: false });
    errors.push(...full.errors);
    warnings.push(...full.warnings.slice(0, 8));
    warnings.push(...reviewOnlyIntakeIssues(payload).slice(0, 10));
    if (selectedOutputs) passes.push(issue("", `${selectedOutputs} output type(s) selected.`));
    passes.push(issue("", "Readiness can be checked before generation."));
    passes.push(issue("", "Missing evidence and estimate-stage warnings are summarized here before handoff."));
    passes.push(issue("", "Package QA is available in Operator tools after generation."));
  }

  return { errors, warnings, passes };
}

function reviewOnlyIntakeIssues(payload) {
  const warnings = [];
  if (!payload.monthly_kwh || payload.monthly_kwh.length !== 12) {
    warnings.push(issue("monthly_usage_mode", "Usage source is not complete; savings and payback may use fallback assumptions."));
  }
  if (!payload.meter_number) {
    warnings.push(issue("meter_number", "Meter number will be needed for AHJ-ready package."));
  }
  if (!payload.meter_location) {
    warnings.push(issue("meter_location", "Meter location will need site review for plan callouts."));
  }
  if (String(payload.site_address || payload.location).toUpperCase().includes("TX") && !payload.meter_esid) {
    warnings.push(issue("meter_esid", "Texas ESID will be needed from the utility bill."));
  }
  if (payload.battery_choice !== "none" && Number(payload.battery_quantity || 0) > 0 && payload.battery_install_location === "unknown") {
    warnings.push(issue("battery_install_location", "Battery install location is not confirmed yet."));
  }
  if (
    payload.battery_choice !== "none"
    && Number(payload.battery_quantity || 0) > 0
    && ["garage", "indoor"].includes(payload.battery_install_location)
    && Number(payload.distance_to_doorway_ft || 0) <= 0
    && Number(payload.distance_to_window_ft || 0) <= 0
    && Number(payload.distance_to_egress_ft || 0) <= 0
  ) {
    warnings.push(issue("battery_install_location", "Battery door/window/egress clearance evidence is missing; verify from photos or site survey."));
  }
  if (!payload.engineer_firm || !payload.engineer_firm_number || !payload.engineer_email || !payload.engineer_phone) {
    warnings.push(issue("engineer_firm", "Engineer-of-record details are missing for AHJ-ready package."));
  }
  if (
    Number(payload.roof_info_height_ft || 0) <= 0
    || !payload.roof_construction
    || !payload.roof_framing
    || payload.roof_condition === "unknown"
    || payload.roof_attic_access === "unknown"
    || Number(payload.decking_thickness_in || 0) <= 0
    || Number(payload.roof_layers || 0) <= 0
  ) {
    warnings.push(issue("roof_info_type", "Roof survey details are incomplete for structural review."));
  }
  if (payload.msp_x_ft == null || payload.msp_y_ft == null || payload.inverter_x_ft == null || payload.inverter_y_ft == null) {
    warnings.push(issue("msp_x_ft", "Equipment coordinates are missing; EE-4 routing will use defaults until site survey is complete."));
  }
  return warnings;
}

function validateAllSteps(payload, options = {}) {
  const stepIds = options.includeReview === false
    ? wizardStepOrder.filter((id) => id !== "package-outputs")
    : wizardStepOrder;
  const errors = [];
  const warnings = [];
  for (const stepId of stepIds) {
    const validation = validateStep(stepId, payload);
    errors.push(...validation.errors);
    warnings.push(...validation.warnings);
  }
  return { errors, warnings };
}

function fileInputHasValue(name) {
  const field = form.elements[name];
  if (!field) {
    return false;
  }
  const files = field.files || [];
  return files.length > 0 && [...files].some((file) => file.size > 0);
}

function setupFileUploadControls() {
  for (const field of form.querySelectorAll('input[type="file"]')) {
    if (field.dataset.fileControlReady === "true") {
      continue;
    }
    field.dataset.fileControlReady = "true";
    field.classList.add("native-file-input");
    const control = document.createElement("div");
    control.className = "file-upload-control";
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "file-upload-button";
    trigger.textContent = field.multiple ? "Choose files" : "Choose file";
    const status = document.createElement("span");
    status.className = "file-upload-status";
    status.textContent = fileUploadStatus(field);
    control.append(trigger, status);
    field.insertAdjacentElement("afterend", control);
    trigger.addEventListener("click", () => field.click());
    field.addEventListener("change", () => {
      status.textContent = fileUploadStatus(field);
      renderCurrentStepValidation({ quiet: true });
    });
  }
}

function fileUploadStatus(field) {
  const files = [...(field.files || [])].filter((file) => file.size > 0);
  if (!files.length) {
    return field.multiple ? "No files selected" : "No file selected";
  }
  if (files.length === 1) {
    return files[0].name;
  }
  return `${files.length} files selected`;
}

function syncPackagePreset(options = {}) {
  const level = selectedPackageLevel();
  const preset = packageOutputPresets[level];
  if (!preset || options.preserveOutputs) {
    return;
  }
  for (const [name, checked] of Object.entries(preset)) {
    const field = form.elements[name];
    if (field && field.type === "checkbox") {
      field.checked = checked;
    }
  }
  renderCurrentStepValidation({ quiet: false });
  localAutosave();
}

function selectedPackageLevel() {
  return packageLevelFields.find((field) => field.checked)?.value || "estimate";
}

function packageLevelLabel(value) {
  return {
    estimate: "Customer estimate",
    engineering_review: "Engineering review",
    ahj_ready: "AHJ-ready candidate",
  }[value] || "Customer estimate";
}

function roofTraceStatusLabel(status) {
  if (!status || !status.mode) {
    return "Not checked";
  }
  const suffix = status.can_ahj_ready ? "AHJ-ready geometry" : "needs roof trace review";
  return `${status.label || status.mode} · ${suffix}`;
}

function traceModuleLayoutStatusLabel(status) {
  if (!status || !status.mode) {
    return "Not checked";
  }
  const placed = Number(status.placed_modules ?? 0);
  const target = Number(status.target_modules ?? 0);
  const count = target ? ` · ${placed}/${target} modules` : "";
  const suffix = status.can_ahj_ready ? "layout verified" : "needs layout review";
  return `${status.label || status.mode}${count} · ${suffix}`;
}

function renderReviewSummary(payload) {
  if (!reviewSummary) {
    return;
  }
  const moduleWatts = Number(moduleChoice.selectedOptions[0]?.dataset.watts || payload.module_power_w || 0);
  const dcKw = Number(payload.modules || 0) * moduleWatts / 1000;
  const batteryKwh = Number(payload.battery_quantity || 0) * Number(batteryChoice.selectedOptions[0]?.dataset.kwh || 0);
  const inverterModel = inverterChoice.selectedOptions[0]?.dataset.model || payload.inverter_model || payload.inverter_choice || "-";
  const batteryLabel = payload.battery_choice === "none" || Number(payload.battery_quantity || 0) === 0
    ? "No battery"
    : `${payload.battery_quantity || 0} x ${batteryChoice.selectedOptions[0]?.dataset.model || payload.battery_model || payload.battery_choice}`;
  const selectedOutputs = outputLabels(payload.outputs || {});
  const roofSections = Array.isArray(payload.roof_sections) ? payload.roof_sections.length : 0;
  const roofGeometry = roofSections
    ? `${roofSections} lookup roof face${roofSections === 1 ? "" : "s"} · trace required for AHJ-ready`
    : "Fallback roof dimensions · trace required for AHJ-ready";
  reviewSummary.innerHTML = `
    <dt>Address</dt><dd>${escapeHtml(payload.site_address || "-")}</dd>
    <dt>System</dt><dd>${dcKw ? dcKw.toFixed(2) : "-"} kW DC · ${escapeHtml(String(payload.modules || "-"))} modules</dd>
    <dt>Inverter / battery</dt><dd>${escapeHtml(inverterModel)} · ${escapeHtml(batteryLabel)}${batteryKwh ? ` · ${batteryKwh.toFixed(1)} kWh` : ""}</dd>
    <dt>Roof geometry</dt><dd>${escapeHtml(roofGeometry)}</dd>
    <dt>Evidence</dt><dd>${payload.site_data_source === "real" ? "Uploaded field evidence" : "Quick estimate evidence"}</dd>
    <dt>Package level</dt><dd>${escapeHtml(packageLevelLabel(payload.package_level))}</dd>
    <dt>Deliverables</dt><dd>${escapeHtml(selectedOutputs.join(", ") || "None selected")}</dd>
  `;
}

function outputLabels(outputs) {
  const labels = [];
  if (outputs.customer) labels.push("Customer PDF");
  if (outputs.permit) labels.push("Permit package");
  if (outputs.dxf) labels.push("DXF previews");
  if (outputs.labels) labels.push("NEC labels");
  if (outputs.qet) labels.push("QET");
  return labels;
}

function normalizeMessages(items) {
  return items.map((item) => typeof item === "string" ? item : item.message);
}

function currentDraftId() {
  const existing = storageGet("tge_pvess_draft_id") || "";
  if (existing) {
    return existing;
  }
  const generated = `draft-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  storageSet("tge_pvess_draft_id", generated);
  return generated;
}

function localAutosave() {
  try {
    const payload = buildPayload(new FormData(form));
    const record = {
      draft_id: currentDraftId(),
      step: currentStepId(),
      payload,
      updated_at: new Date().toISOString(),
    };
    if (!storageSet(wizardDraftKey, JSON.stringify(record))) {
      throw new Error("storage unavailable");
    }
    draftStatus.textContent = `Draft autosaved ${formatTime(record.updated_at)}`;
    draftStatus.classList.add("saved");
    draftStatus.classList.remove("warning");
  } catch {
    draftStatus.textContent = "Draft autosave unavailable";
    draftStatus.classList.add("warning");
  }
}

function restoreDraftFromLocal() {
  const raw = storageGet(wizardDraftKey);
  if (!raw) {
    return;
  }
  try {
    const record = JSON.parse(raw);
    if (!record || !record.payload) {
      return;
    }
    applyPayloadToForm(record.payload, {
      message: `Restored local draft from ${formatTime(record.updated_at)}.`,
      preserveStep: true,
    });
    if (wizardStepOrder.includes(record.step)) {
      currentStepIndex = wizardStepOrder.indexOf(record.step);
    }
    localDraftRestored = true;
    draftStatus.textContent = `Draft restored ${formatTime(record.updated_at)}`;
    draftStatus.classList.add("saved");
  } catch {
    draftStatus.textContent = "Saved draft could not be restored";
    draftStatus.classList.add("warning");
  }
}

async function saveDraft(options = {}) {
  const record = {
    draft_id: currentDraftId(),
    step: currentStepId(),
    payload: buildPayload(new FormData(form)),
  };
  const localSaved = storageSet(wizardDraftKey, JSON.stringify({
    ...record,
    updated_at: new Date().toISOString(),
  }));
  draftStatus.textContent = localSaved ? "Draft saved locally" : "Draft storage unavailable";
  draftStatus.classList.add("saved");
  draftStatus.classList.remove("warning");
  if (options.manual) {
    saveDraftButton.disabled = true;
    saveDraftButton.textContent = "Saving...";
  }
  try {
    const response = await apiFetch("/api/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(record),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    storageSet("tge_pvess_draft_id", data.draft_id);
    storageSet(wizardDraftKey, JSON.stringify(data));
    draftStatus.textContent = `Draft saved ${formatTime(data.updated_at)}`;
    if (options.manual) {
      statusEl.textContent = `Draft ${data.draft_id} saved.`;
    }
  } catch (error) {
    draftStatus.textContent = "Draft saved locally; server sign-in required";
    draftStatus.classList.add("warning");
    if (options.manual) {
      statusEl.textContent = error.message.includes("required")
        ? "Draft saved locally. Sign in to save it to the server."
        : `Draft saved locally. ${error.message}`;
    }
  } finally {
    if (options.manual) {
      saveDraftButton.disabled = false;
      saveDraftButton.textContent = "Save draft";
    }
  }
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "recently";
  }
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function applyTemplate(name) {
  const preset = templates[name];
  if (!preset) {
    return;
  }
  clearLookupRoofSections();
  for (const [key, value] of Object.entries(preset)) {
    const field = form.elements[key] || document.querySelector(`[name="${key}"]`);
    if (field) {
      field.value = value;
    }
  }
  syncModuleOption();
  syncInverterOption();
  syncBatteryOption({ preserveQuantity: true });
  syncUsageMode();
  syncSelfConsumptionProfile();
  syncRoofAssumptionSummary();
  renderValidation([], [`Project type set to ${labelForTemplate(name)}.`]);
  renderCurrentStepValidation({ quiet: false });
  localAutosave();
}

function applyAddressSample(name) {
  const sample = addressSamples[name];
  if (!sample) {
    return;
  }
  clearLookupRoofSections();
  for (const [key, value] of Object.entries(sample)) {
    setFieldValue(key, value);
  }
  markRoofPreviewStale("Sample address loaded. Build a fresh roof preview for this project.");
  syncUsageMode();
  syncSelfConsumptionProfile();
  syncRoofAssumptionSummary();
  renderValidation([], [`Loaded sample project: ${sample.site_address}. Monthly usage is simulated until a bill or Smart Meter export is uploaded.`]);
  renderCurrentStepValidation({ quiet: false });
  localAutosave();
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
    if (key === "monthly_kwh_average") {
      continue;
    }
    if (key === "monthly_usage_mode") {
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

  const monthlyMode = String(data.get("monthly_usage_mode") || "local_default");
  payload.monthly_usage_mode = monthlyMode;
  if (monthlyMode === "local_default") {
    payload.monthly_kwh = [...dfwResidentialMonthlyKwh];
  } else if (monthlyMode === "average") {
    const average = Number(data.get("monthly_kwh_average") || 0);
    if (Number.isFinite(average) && average > 0) {
      payload.monthly_kwh = Array.from({ length: 12 }, () => average);
    }
  } else if (monthlyMode === "monthly_detail") {
    const monthly = parseMonthlyKwh(data.get("monthly_kwh_text") || "");
    if (monthly.length > 0) {
      payload.monthly_kwh = monthly;
    }
  }

  syncUsAddressPayload(payload);
  if (lastLookupRoofSections.length) {
    payload.roof_sections = lastLookupRoofSections.map((section) => ({ ...section }));
  }
  if (lastEe4Trace) {
    payload.ee4_trace = JSON.parse(JSON.stringify(lastEe4Trace));
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

function syncUsAddressPayload(payload) {
  const line1 = String(payload.address_line1 || "").trim();
  const line2 = String(payload.address_line2 || "").trim();
  const city = String(payload.address_city || "").trim();
  const state = String(payload.address_state || "").trim().toUpperCase();
  const postal = String(payload.address_postal_code || "").trim();
  const street = [line1, line2].filter(Boolean).join(", ");
  const cityStateZip = [
    city,
    [state, postal].filter(Boolean).join(" "),
  ].filter(Boolean).join(", ");
  payload.site_address = [street, cityStateZip].filter(Boolean).join(", ");
  payload.location = [city, state].filter(Boolean).join(", ");
  if (!payload.project_name) {
    payload.project_name = deriveProjectName(payload.site_address);
  }
  setRawFieldValue("site_address", payload.site_address);
  setRawFieldValue("location", payload.location);
  setRawFieldValue("project_name", payload.project_name);
  delete payload.address_line1;
  delete payload.address_line2;
  delete payload.address_city;
  delete payload.address_state;
  delete payload.address_postal_code;
}

function deriveProjectName(siteAddress) {
  const street = String(siteAddress || "").split(",")[0]?.trim() || "Residential";
  const typeLabel = {
    pv_ess: "Solar + Battery",
    pv_only: "Solar",
    retrofit_existing_pv: "Battery Retrofit",
  }[projectTemplate.value] || "Solar";
  return `${street} ${typeLabel} Project`;
}

function validatePayload(payload) {
  const validation = validateAllSteps(payload, { includeReview: false });
  if (!Object.values(payload.outputs || {}).some(Boolean)) {
    validation.errors.push(issue("", "Select at least one package output before generation."));
  }
  return {
    errors: normalizeMessages(validation.errors),
    warnings: normalizeMessages(validation.warnings),
  };
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
    const stepValidation = validateStep("package-outputs", payload);
    renderStepValidation(stepValidation);
    if (stepValidation.errors[0]) {
      focusIssueField(stepValidation.errors[0]);
    }
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
  const payload = buildPayload(new FormData(form));
  const address = (payload.site_address || payload.location || "").trim();
  if (!address) {
    renderLookupMessage("Enter street, city, state, and ZIP before using auto-fill.", "warning");
    return;
  }

  lookupButton.disabled = true;
  lookupButton.textContent = "Checking...";
  statusEl.textContent = "Checking address details.";
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
    renderCurrentStepValidation({ quiet: false });
    localAutosave();
    statusEl.textContent = `Address check ${data.status}`;
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  } finally {
    lookupButton.disabled = false;
    lookupButton.textContent = "Check address";
  }
}

function applyLookupToForm(suggested) {
  for (const [key, value] of Object.entries(suggested)) {
    setFieldValue(key, value);
  }
}

function normalizeRoofSections(sections) {
  if (!Array.isArray(sections)) {
    return [];
  }
  return sections.map((section, index) => {
    const width = Number(section.width_ft);
    const height = Number(section.height_ft);
    const pitch = Number(section.pitch_deg);
    const azimuth = Number(section.azimuth_deg);
    if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(height) || height <= 0) {
      return null;
    }
    if (!Number.isFinite(pitch) || !Number.isFinite(azimuth)) {
      return null;
    }
    return {
      name: String(section.name || `Roof Section ${index + 1}`),
      roof_type: String(section.roof_type || "Comp Shingle"),
      pitch_deg: pitch,
      azimuth_deg: azimuth,
      width_ft: width,
      height_ft: height,
      module_count: Number.isFinite(Number(section.module_count)) ? Number(section.module_count) : 0,
      shape: ["rect", "tri", "polygon"].includes(section.shape) ? section.shape : "rect",
    };
  }).filter(Boolean).slice(0, 80);
}

function clearLookupRoofSections() {
  lastLookupRoofSections = [];
  lastLookupRoofCandidates = [];
  lastEe4Trace = null;
}

function renderLookup(data) {
  const suggested = Object.keys(data.suggested_payload || {});
  const providers = data.providers || [];
  const hits = providers.filter((provider) => provider.hit);
  const roof = data.roof_summary || {};
  lastLookupRoofSections = normalizeRoofSections(data.fields?.roof_sections || []);
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
  renderCurrentStepValidation({ quiet: false });
  localAutosave();
}

function renderLookupMessage(message, type) {
  lookupPanel.classList.remove("hidden");
  lookupPanel.innerHTML = `<div class="validation-${type}">${escapeHtml(message)}</div>`;
}

function markRoofPreviewStale(message) {
  if (!roofPreviewPanel) {
    return;
  }
  const status = roofPreviewPanel.dataset.status || "";
  if (!status || status === "empty") {
    return;
  }
  roofPreviewPanel.dataset.status = "stale";
  roofPreviewPanel.innerHTML = `
    <div class="roof-preview-empty warning">
      <strong>Roof preview needs refresh.</strong>
      <span>${escapeHtml(message)}</span>
      <button type="button" class="secondary-button" data-roof-preview-action="rebuild">Rebuild roof preview</button>
    </div>
  `;
}

function renderRoofPreviewProgress(message, progress = 12) {
  if (!roofPreviewPanel) {
    return;
  }
  roofPreviewPanel.dataset.status = "progress";
  roofPreviewPanel.innerHTML = `
    <div class="roof-preview-empty">
      <strong>Building roof preview...</strong>
      <span>${escapeHtml(message)}</span>
    </div>
  `;
  setProgress(progress, message);
}

async function runRoofPreview() {
  clearError();
  const formData = new FormData(form);
  const payload = buildPayload(formData);
  const projectValidation = validateStep("project-basics", payload);
  if (projectValidation.errors.length > 0) {
    renderStepValidation(projectValidation);
    focusIssueField(projectValidation.errors[0]);
    statusEl.textContent = "Enter a complete U.S. address before building the roof preview.";
    statusEl.classList.add("error");
    return;
  }

  const previewPayload = {
    ...payload,
    outputs: {
      customer: false,
      permit: false,
      dxf: false,
      labels: false,
      qet: false,
    },
  };

  roofPreviewButton.disabled = true;
  roofPreviewButton.textContent = "Building...";
  statusEl.classList.remove("error");
  statusEl.textContent = "Building satellite roof preview.";
  renderRoofPreviewProgress("Submitting a lightweight roof-preview job.");

  try {
    const request = new FormData();
    request.append("payload", JSON.stringify(previewPayload));
    appendSiteFiles(request, formData);

    const response = await apiFetch("/api/projects/form", {
      method: "POST",
      body: request,
    });
    const state = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(state));
    }
    await pollRoofPreviewJob(state.job_id);
  } catch (error) {
    roofPreviewButton.disabled = false;
    roofPreviewButton.textContent = "Build roof preview";
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
    if (roofPreviewPanel) {
      roofPreviewPanel.dataset.status = "error";
      roofPreviewPanel.innerHTML = `
        <div class="roof-preview-empty error">
          <strong>Roof preview failed.</strong>
          <span>${escapeHtml(error.message)}</span>
          <button type="button" class="secondary-button" data-roof-preview-action="rebuild">Try again</button>
        </div>
      `;
    }
  }
}

async function pollRoofPreviewJob(jobId) {
  if (roofPreviewPoll) {
    clearTimeout(roofPreviewPoll);
  }

  const tick = async () => {
    try {
      const response = await apiFetch(`/api/jobs/${jobId}`);
      const state = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(state));
      }
      renderRoofPreviewProgress(`${state.stage}: ${state.message}`, state.progress || 15);
      if (state.status === "done") {
        const result = {
          ...(state.result || {}),
          job_id: state.result?.job_id || state.job_id,
        };
        roofPreviewButton.disabled = false;
        roofPreviewButton.textContent = "Rebuild roof preview";
        statusEl.textContent = `Roof preview ready. Project ${state.job_id}`;
        renderRoofPreviewResult(result);
        await loadHistory();
        return;
      }
      if (state.status === "failed") {
        throw new Error(state.error || state.message || "Roof preview failed.");
      }
      roofPreviewPoll = setTimeout(tick, 900);
    } catch (error) {
      roofPreviewButton.disabled = false;
      roofPreviewButton.textContent = "Build roof preview";
      statusEl.textContent = error.message;
      statusEl.classList.add("error");
      renderError(error.message);
      if (roofPreviewPanel) {
        roofPreviewPanel.dataset.status = "error";
        roofPreviewPanel.innerHTML = `
          <div class="roof-preview-empty error">
            <strong>Roof preview failed.</strong>
            <span>${escapeHtml(error.message)}</span>
            <button type="button" class="secondary-button" data-roof-preview-action="rebuild">Try again</button>
          </div>
        `;
      }
    }
  };

  await tick();
}

function renderRoofPreviewResult(data) {
  if (!roofPreviewPanel || !data) {
    return;
  }
  currentJobId = data.job_id || currentJobId;
  currentFiles = data.files || [];
  currentReadiness = data.readiness || {};
  currentResultData = data;

  const source = data.source_materials || {};
  const readiness = data.readiness || {};
  const roofTrace = readiness.roof_trace || source.roof_trace || {};
  const traceLayout = readiness.trace_module_layout || source.trace_module_layout || {};
  const r8Validation = readiness.r8_validation || source.r8_validation || {};
  const roofTopology = readiness.roof_topology || source.roof_topology || {};
  const satelliteOutline = (
    readiness.satellite_roof_outline
    || source.satellite_roof_outline
    || r8Validation.satellite_roof_outline
    || {}
  );
  const satelliteCropMode = currentSatelliteCropMode(r8Validation);
  const satellitePng = findFileByLabel(currentFiles, "R8 Step 2 Satellite Review PNG");
  const staticSatellitePng = findFileByLabel(currentFiles, "R8 Step 2 Google Static Satellite Fallback PNG");
  const uploadedSatelliteImage = findFileByLabel(currentFiles, "Uploaded Roof Satellite Image");
  const satelliteAudit = findFileByLabel(currentFiles, "Satellite Data Chain Audit Report");
  const satelliteOutlinePng = findFileByLabel(currentFiles, "Satellite Roof Outline Candidate PNG");
  const satelliteOutlineYaml = findFileByLabel(currentFiles, "Satellite EE-4 Trace Candidate YAML");
  const satelliteOutlineJson = findFileByLabel(currentFiles, "Satellite Roof Outline Candidate JSON");
  const topologyDraftYaml = findFileByLabel(currentFiles, "EE-4 Trace Draft YAML");
  const topologyPreviewPng = findFileByLabel(currentFiles, "R8 Step 3 Roof Trace Layout PNG");
  const topologyPreviewPdf = findFileByLabel(currentFiles, "R8 Step 3 Roof Trace Layout PDF");
  const attachmentPreviewPng = findFileByLabel(currentFiles, "R8 Step 4 Panel Attachment Layout PNG");
  const topologyComplete = Boolean(roofTrace.can_ahj_ready && traceLayout.can_ahj_ready);
  const topologyAcceptSource = "satellite_candidate";
  const topologyAcceptLabel = "Accept satellite topology and regenerate preview";
  const outlineStatus = satelliteOutline.status || "REVIEW";
  const outlineStatusClass = outlineStatus === "PASS" ? "pass" : "warning";
  const address = data.summary?.site_address || form.elements.site_address?.value || "Project address";
  const googleStatic = r8Validation.google_static_satellite || {};
  const preferredSatellite = uploadedSatelliteImage || staticSatellitePng || satellitePng;
  const preferredSatelliteLabel = uploadedSatelliteImage
    ? "Uploaded roof reference"
    : (staticSatellitePng ? "Google Static satellite fallback" : "Google Solar satellite review");
  const maskBlocked = outlineStatus !== "PASS" && /zero roof pixels|mask/i.test(String(satelliteOutline.detail || satelliteOutline.audit_detail || ""));

  roofPreviewPanel.dataset.status = "ready";
  roofPreviewPanel.innerHTML = `
    <div class="roof-preview-head">
      <div>
        <strong>${topologyComplete ? "Roof topology completed" : "Roof preview ready"}</strong>
        <span>${escapeHtml(address)} · ${escapeHtml(satelliteCropModeLabel(satelliteCropMode))} crop</span>
      </div>
      <span class="review-status-pill ${topologyComplete ? "pass" : "warning"}">
        ${topologyComplete ? "Topology saved" : "Topology needs acceptance"}
      </span>
      <button type="button" class="secondary-button" data-roof-preview-action="rebuild">Rebuild with selected range</button>
    </div>
    ${renderRoofTopologyChecklist(roofTopology)}
    <div class="roof-preview-grid">
      <article class="roof-preview-card">
        <div>
          <h4>Satellite image</h4>
          <p>Confirm this image is centered on the customer's roof, not the neighbor's roof or a shared townhome block.</p>
        </div>
        ${preferredSatellite ? `
          <a class="roof-preview-image" href="${withAuthUrl(preferredSatellite.url)}" target="_blank" rel="noopener">
            <img src="${withAuthUrl(preferredSatellite.url)}" alt="Satellite roof preview" />
          </a>
        ` : `
          <div class="roof-preview-missing">No satellite image returned. Online map keys or manual roof evidence may be needed.</div>
        `}
        <dl class="review-metric-grid compact">
          <dt>Image source</dt><dd>${escapeHtml(preferredSatellite ? preferredSatelliteLabel : "Not available")}</dd>
          <dt>Solar mask</dt><dd><span class="review-status-pill ${outlineStatus === "PASS" ? "pass" : "warning"}">${escapeHtml(outlineStatus)}</span></dd>
          <dt>Static fallback</dt><dd>${escapeHtml(googleStatic.status || (staticSatellitePng ? "PASS" : "not used"))}</dd>
        </dl>
        ${maskBlocked ? `
          <div class="gate-card warn">
            <strong>Google Solar mask did not produce an outline.</strong>
            <span>${escapeHtml(satelliteOutline.detail || satelliteOutline.audit_detail || "Use the uploaded image or Static satellite fallback, then trace the roof manually in Step 2.")}</span>
          </div>
        ` : ""}
        <div class="satellite-outline-actions">
          ${satellitePng ? `<a href="${withAuthUrl(satellitePng.url)}" target="_blank" rel="noopener">Open satellite image</a>` : ""}
          ${staticSatellitePng ? `<a href="${withAuthUrl(staticSatellitePng.url)}" target="_blank" rel="noopener">Open Static fallback</a>` : ""}
          ${uploadedSatelliteImage ? `<a href="${withAuthUrl(uploadedSatelliteImage.url)}" target="_blank" rel="noopener">Open uploaded image</a>` : ""}
          ${satelliteAudit ? `<a href="${withAuthUrl(satelliteAudit.url)}" target="_blank" rel="noopener">Open data audit</a>` : ""}
        </div>
      </article>
      <article class="roof-preview-card">
        <div>
          <h4>Roof outline candidate</h4>
          <p>Use this as an early topology check. It still needs ridge, hip, obstruction, and fire pathway review before AHJ handoff.</p>
        </div>
        ${satelliteOutlinePng ? `
          <a class="roof-preview-image" href="${withAuthUrl(satelliteOutlinePng.url)}" target="_blank" rel="noopener">
            <img src="${withAuthUrl(satelliteOutlinePng.url)}" alt="Satellite roof outline candidate" />
          </a>
        ` : `
          <div class="roof-preview-missing">No automatic outline candidate was produced. Upload a recent roof image or use the Static fallback image, then edit/save the roof outline below.</div>
        `}
        <dl class="review-metric-grid compact">
          <dt>Status</dt><dd><span class="review-status-pill ${outlineStatusClass}">${escapeHtml(outlineStatus)}</span></dd>
          <dt>Vertices</dt><dd>${escapeHtml(String(satelliteOutline.vertex_count || "-"))}</dd>
          <dt>Area</dt><dd>${satelliteOutline.area_sqft ? `${escapeHtml(String(satelliteOutline.area_sqft))} sqft` : "-"}</dd>
          <dt>Roof trace</dt><dd>${escapeHtml(roofTraceStatusLabel(roofTrace))}</dd>
        </dl>
        <div class="satellite-outline-actions">
          ${satelliteOutlinePng ? `<a href="${withAuthUrl(satelliteOutlinePng.url)}" target="_blank" rel="noopener">Open outline preview</a>` : ""}
          ${satelliteOutlineJson ? `<a href="${withAuthUrl(satelliteOutlineJson.url)}" target="_blank" rel="noopener">Open candidate JSON</a>` : ""}
          ${satelliteOutlineYaml ? `<a href="${withAuthUrl(satelliteOutlineYaml.url)}" target="_blank" rel="noopener">Open candidate YAML</a>` : ""}
          ${satelliteOutlineYaml && currentJobId && !topologyComplete ? `
            <button type="button" class="secondary-button" data-roof-preview-action="accept-satellite">
              Accept outline and regenerate preview
            </button>
          ` : ""}
        </div>
      </article>
      <article class="roof-preview-card roof-preview-topology-card">
        <div>
          <h4>Roof topology draft</h4>
          <p>Complete the Step 2 topology layer here. This saves an EE-4 trace with roof outline, facets or roof lines, fire pathways, and module-layout checks for the downstream package.</p>
        </div>
        ${topologyPreviewPng ? `
          <a class="roof-preview-image" href="${withAuthUrl(topologyPreviewPng.url)}" target="_blank" rel="noopener">
            <img src="${withAuthUrl(topologyPreviewPng.url)}" alt="Roof topology draft preview" />
          </a>
        ` : `
          <div class="roof-preview-missing">No topology preview returned. Rebuild the roof preview after confirming the address.</div>
        `}
        <dl class="review-metric-grid compact">
          <dt>Topology</dt><dd><span class="review-status-pill ${roofTrace.can_ahj_ready ? "pass" : "warning"}">${escapeHtml(roofTrace.status || "WARN")}</span></dd>
          <dt>Geometry</dt><dd>${escapeHtml(roofTraceStatusLabel(roofTrace))}</dd>
          <dt>Module layout</dt><dd>${escapeHtml(traceModuleLayoutStatusLabel(traceLayout))}</dd>
          <dt>Modules</dt><dd>${escapeHtml(moduleLayoutCountLabel(roofTopology, traceLayout))}</dd>
          <dt>Trace source</dt><dd>${escapeHtml(roofTrace.source || "Generated roof draft")}</dd>
        </dl>
        <div class="satellite-outline-actions">
          ${topologyPreviewPng ? `<a href="${withAuthUrl(topologyPreviewPng.url)}" target="_blank" rel="noopener">Open topology preview</a>` : ""}
          ${topologyPreviewPdf ? `<a href="${withAuthUrl(topologyPreviewPdf.url)}" target="_blank" rel="noopener">Open topology PDF</a>` : ""}
          ${attachmentPreviewPng ? `<a href="${withAuthUrl(attachmentPreviewPng.url)}" target="_blank" rel="noopener">Open panel layout</a>` : ""}
          ${topologyDraftYaml ? `<a href="${withAuthUrl(topologyDraftYaml.url)}" target="_blank" rel="noopener">Open topology YAML</a>` : ""}
          ${satelliteOutlineYaml && currentJobId && !topologyComplete ? `
            <button type="button" class="secondary-button" data-roof-preview-action="accept-topology" data-roof-preview-source="${topologyAcceptSource}">
              ${topologyAcceptLabel}
            </button>
          ` : ""}
          ${currentJobId ? `
            <button type="button" class="secondary-button" data-roof-proposal-action>
              Generate skill topology proposal
            </button>
          ` : ""}
        </div>
        <p class="review-note">This completes the project topology data model for estimate and internal review. AHJ-ready handoff still requires field evidence and artifact approval.</p>
      </article>
    </div>
    ${renderRoofOutlineEditor(roofTopology)}
  `;
}

function renderRoofTopologyChecklist(roofTopology = {}) {
  const steps = Array.isArray(roofTopology.steps) ? roofTopology.steps : [];
  if (!steps.length) {
    return "";
  }
  return `
    <section class="roof-topology-checklist" aria-label="Roof topology workflow status">
      <div>
        <strong>Step 2 roof workflow</strong>
        <span>${escapeHtml(roofTopology.required_action || (roofTopology.status === "PASS" ? "Roof topology and panel layout are ready for downstream review." : "Complete roof evidence, outline, topology, and panel preview before relying on permit sheets."))}</span>
      </div>
      <ol>
        ${steps.map((step) => `
          <li class="${String(step.status || "").toLowerCase() === "pass" ? "pass" : "warn"}">
            <strong>${escapeHtml(step.code || "")}</strong>
            <span>${escapeHtml(step.label || "")}</span>
          </li>
        `).join("")}
      </ol>
    </section>
  `;
}

function moduleLayoutCountLabel(roofTopology = {}, traceLayout = {}) {
  const placed = Number(roofTopology.placed_modules || traceLayout.placed_modules || 0);
  const target = Number(roofTopology.target_modules || traceLayout.target_modules || 0);
  if (!target) {
    return placed ? `${placed} placed` : "-";
  }
  return `${placed}/${target}`;
}

function renderRoofOutlineEditor(roofTopology = {}) {
  const editor = roofTopology.editor || {};
  const trace = editor.trace || {};
  const vertices = normalizeRoofVertices(
    editor.outline_vertices || trace.roof_outline?.vertices || [],
  );
  if (!vertices.length) {
    return "";
  }
  return `
    <section class="roof-outline-editor" data-roof-outline-editor>
      <div class="roof-outline-editor-head">
        <div>
          <h4>Editable roof outline</h4>
          <p>Use this when the satellite mask includes too much roof or misses an edge. Tighten the outline, edit vertices, then save it as the reviewed Step 2 topology.</p>
        </div>
        <span class="review-status-pill">${escapeHtml(editor.source || "trace draft")}</span>
      </div>
      <script type="application/json" data-roof-editor-trace>${escapeHtml(JSON.stringify(trace || {}))}</script>
      <div class="roof-outline-editor-grid">
        <div class="roof-outline-svg-wrap" data-roof-outline-svg-wrap>
          ${renderRoofOutlineSvg(vertices)}
        </div>
        <div>
          <div class="roof-outline-editor-actions">
            <button type="button" class="secondary-button" data-roof-outline-action="shrink">Tighten 5%</button>
            <button type="button" class="secondary-button" data-roof-outline-action="expand">Expand 5%</button>
            <button type="button" class="secondary-button" data-roof-outline-action="add">Add vertex</button>
            <button type="button" class="primary-button" data-roof-outline-action="save">Save edited outline</button>
          </div>
          <div class="roof-outline-vertices" data-roof-outline-rows>
            ${renderRoofOutlineRows(vertices)}
          </div>
          <p class="review-note">Saved edits preserve the structured EE-4 trace contract. The backend regenerates roof lines, fire pathways, and module layout checks from this outline.</p>
        </div>
      </div>
    </section>
  `;
}

function renderRoofOutlineRows(vertices) {
  return vertices.map((point, index) => `
    <div class="roof-outline-row" data-roof-outline-row>
      <span>${index + 1}</span>
      <label>X ft
        <input type="number" step="0.1" value="${Number(point[0]).toFixed(2)}" data-roof-vertex-x />
      </label>
      <label>Y ft
        <input type="number" step="0.1" value="${Number(point[1]).toFixed(2)}" data-roof-vertex-y />
      </label>
      <button type="button" data-roof-outline-action="remove" data-index="${index}" ${vertices.length <= 3 ? "disabled" : ""}>Remove</button>
    </div>
  `).join("");
}

function renderRoofOutlineSvg(vertices) {
  const points = normalizeRoofVertices(vertices);
  if (!points.length) {
    return "";
  }
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = Math.max((maxX - minX), (maxY - minY), 1) * 0.08;
  const viewBox = [
    (minX - pad).toFixed(2),
    (minY - pad).toFixed(2),
    (maxX - minX + pad * 2).toFixed(2),
    (maxY - minY + pad * 2).toFixed(2),
  ].join(" ");
  const path = points.map((point) => point.join(",")).join(" ");
  return `
    <svg viewBox="${viewBox}" role="img" aria-label="Editable roof outline preview">
      <polygon points="${escapeHtml(path)}"></polygon>
      ${points.map((point, index) => `
        <circle cx="${point[0]}" cy="${point[1]}" r="${Math.max(pad * 0.12, 0.6).toFixed(2)}"></circle>
        <text x="${point[0]}" y="${point[1]}">${index + 1}</text>
      `).join("")}
    </svg>
  `;
}

function normalizeRoofVertices(vertices) {
  if (!Array.isArray(vertices)) {
    return [];
  }
  return vertices
    .map((point) => {
      if (!Array.isArray(point) || point.length < 2) {
        return null;
      }
      const x = Number(point[0]);
      const y = Number(point[1]);
      return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null;
    })
    .filter(Boolean);
}

function roofOutlineEditorVertices(editor) {
  const rows = [...editor.querySelectorAll("[data-roof-outline-row]")];
  return rows.map((row) => {
    const x = Number(row.querySelector("[data-roof-vertex-x]")?.value);
    const y = Number(row.querySelector("[data-roof-vertex-y]")?.value);
    return [x, y];
  }).filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
}

function setRoofOutlineEditorVertices(editor, vertices) {
  const normalized = normalizeRoofVertices(vertices);
  const rows = editor.querySelector("[data-roof-outline-rows]");
  const svgWrap = editor.querySelector("[data-roof-outline-svg-wrap]");
  if (rows) {
    rows.innerHTML = renderRoofOutlineRows(normalized);
  }
  if (svgWrap) {
    svgWrap.innerHTML = renderRoofOutlineSvg(normalized);
  }
}

function scaleRoofOutlineVertices(vertices, factor) {
  const points = normalizeRoofVertices(vertices);
  if (points.length < 3) {
    return points;
  }
  const cx = points.reduce((sum, point) => sum + point[0], 0) / points.length;
  const cy = points.reduce((sum, point) => sum + point[1], 0) / points.length;
  return points.map(([x, y]) => [
    Number((cx + (x - cx) * factor).toFixed(2)),
    Number((cy + (y - cy) * factor).toFixed(2)),
  ]);
}

function addRoofOutlineVertex(vertices) {
  const points = normalizeRoofVertices(vertices);
  if (points.length < 2) {
    return points;
  }
  const last = points[points.length - 1];
  const first = points[0];
  const midpoint = [
    Number(((last[0] + first[0]) / 2).toFixed(2)),
    Number(((last[1] + first[1]) / 2).toFixed(2)),
  ];
  return [...points, midpoint];
}

function signedRoofArea(vertices) {
  const points = normalizeRoofVertices(vertices);
  return points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0) / 2;
}

function handleRoofPreviewClick(event) {
  const proposalButton = event.target.closest("[data-roof-proposal-action]");
  if (proposalButton) {
    generateRoofTopologyProposal(proposalButton);
    return;
  }
  const outlineButton = event.target.closest("[data-roof-outline-action]");
  if (outlineButton) {
    handleRoofOutlineEditorAction(outlineButton);
    return;
  }
  const actionButton = event.target.closest("[data-roof-preview-action]");
  if (!actionButton) {
    return;
  }
  const action = actionButton.dataset.roofPreviewAction;
  if (action === "rebuild") {
    runRoofPreview();
  } else if (action === "accept-satellite") {
    acceptSatelliteRoofTrace(actionButton);
  } else if (action === "accept-topology") {
    acceptRoofTraceDraft(actionButton);
  }
}

function handleRoofOutlineEditorAction(button) {
  const editor = button.closest("[data-roof-outline-editor]");
  if (!editor) {
    return;
  }
  const action = button.dataset.roofOutlineAction;
  const vertices = roofOutlineEditorVertices(editor);
  if (action === "shrink") {
    setRoofOutlineEditorVertices(editor, scaleRoofOutlineVertices(vertices, 0.95));
  } else if (action === "expand") {
    setRoofOutlineEditorVertices(editor, scaleRoofOutlineVertices(vertices, 1.05));
  } else if (action === "add") {
    setRoofOutlineEditorVertices(editor, addRoofOutlineVertex(vertices));
  } else if (action === "remove") {
    const index = Number(button.dataset.index);
    if (vertices.length > 3 && Number.isInteger(index)) {
      setRoofOutlineEditorVertices(editor, vertices.filter((_point, idx) => idx !== index));
    }
  } else if (action === "save") {
    saveEditedRoofOutline(button);
  }
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
  resultsAside.classList.add("has-results");
  resultsAside.classList.remove("job-active");
  currentJobId = data.job_id || "";
  currentReadiness = data.readiness || {};
  currentResultData = data;
  artifactReviewPageIndex = 0;
  artifactReviews = {};
  updateReviewFocusMode();
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
  renderArtifactReviewWorkbench();
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
    "roof_satellite_image",
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
  if (!selected) return;
  moduleBrandDisplay.value = selected.dataset.brand || "";
  moduleModelDisplay.value = selected.dataset.model || "";
  moduleWattsDisplay.value = selected.dataset.watts || "";
}

function syncInverterOption() {
  const selected = inverterChoice.selectedOptions[0];
  if (!selected) return;
  inverterModelDisplay.value = selected.dataset.model || "";
  inverterAmpsInput.value = selected.dataset.amps || "";
  syncBatteryForInverter(selected);
}

function syncBatteryOption(options = {}) {
  const selected = batteryChoice.selectedOptions[0];
  if (!selected) return;
  batteryModelDisplay.value = selected.dataset.model || "";
  batteryKwhDisplay.value = selected.dataset.kwh || "0";
  if (batteryChoice.value === "none") {
    batteryQtyInput.value = "0";
  } else if (!options.preserveQuantity && Number(batteryQtyInput.value || 0) === 0) {
    batteryQtyInput.value = "1";
  }
  syncBatterySiteFields();
}

function syncBatteryForInverter(selected) {
  const pairedBattery = selected?.dataset?.pairedBattery || inverterBatteryPairings[inverterChoice.value];
  if (!pairedBattery || batteryChoice.value === "none") {
    return;
  }
  if (batteryChoice.value !== pairedBattery) {
    batteryChoice.value = pairedBattery;
  }
  syncBatteryOption({ preserveQuantity: true });
}

function syncUsageMode() {
  const mode = monthlyUsageMode.value;
  monthlyAverageField.classList.toggle("hidden", mode !== "average");
  monthlyDetailField.classList.toggle("hidden", mode !== "monthly_detail");
  usageBillHint.classList.toggle("hidden", mode !== "upload_bill");
}

function syncSelfConsumptionProfile() {
  const selected = selfConsumptionProfile.selectedOptions[0];
  if (!selected) return;
  const fraction = selected.dataset.fraction || "0.55";
  selfConsumptionFraction.value = fraction;
  const percent = Math.round(Number(fraction) * 100);
  selfConsumptionNote.textContent = `Self-consumption assumption: ${percent}% of PV production used onsite or shifted by battery.`;
}

function syncRoofAssumptionSummary() {
  if (!roofAssumptionSummary) return;
  const pitch = form.elements.roof_pitch_deg?.value || "-";
  const azimuth = form.elements.roof_azimuth_deg?.value || "-";
  const width = form.elements.roof_width_ft?.value || "-";
  const height = form.elements.roof_height_ft?.value || "-";
  roofAssumptionSummary.textContent = `Using fallback roof geometry: ${pitch} deg pitch, ${azimuth} deg azimuth, ${width} ft x ${height} ft. Address lookup or roof photos can replace this later.`;
}

function syncBatterySiteFields() {
  const hasBattery = batteryChoice.value !== "none" && Number(batteryQtyInput.value || 0) > 0;
  batteryLocationBlock.classList.toggle("hidden", !hasBattery);
  const needsClearanceReview = hasBattery && ["garage", "indoor"].includes(batteryInstallLocation.value);
  batteryClearanceNote.classList.toggle("hidden", !needsClearanceReview);
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

function renderArtifactReviewWorkbench() {
  if (!currentResultData || !currentJobId) {
    artifactReviewWorkbench.classList.add("hidden");
    reviewFocusBar.classList.add("hidden");
    artifactReviewTabs.innerHTML = "";
    artifactReviewPage.innerHTML = "";
    artifactReviewCounter.textContent = "No package generated";
    artifactReviewPosition.textContent = "Page 0 of 0";
    return;
  }

  artifactReviewWorkbench.classList.remove("hidden");
  artifactReviewPages = buildArtifactReviewPages(currentResultData);
  artifactReviewPageIndex = Math.max(
    0,
    Math.min(artifactReviewPageIndex, artifactReviewPages.length - 1)
  );
  const activePage = artifactReviewPages[artifactReviewPageIndex];
  const reviewCounts = artifactReviewCounts();

  artifactReviewCounter.textContent = reviewCounts.required
    ? `${reviewCounts.approved}/${reviewCounts.required} required approvals complete`
    : `${reviewCounts.approved} artifact review${reviewCounts.approved === 1 ? "" : "s"} complete`;
  artifactReviewPosition.textContent = `Page ${artifactReviewPageIndex + 1} of ${artifactReviewPages.length}`;
  artifactReviewPrev.disabled = artifactReviewPageIndex === 0;
  artifactReviewNext.disabled = artifactReviewPageIndex >= artifactReviewPages.length - 1;
  artifactReviewTabs.innerHTML = artifactReviewPages.map((page, index) => `
    <button type="button" class="${index === artifactReviewPageIndex ? "active" : ""}" data-review-page="${index}">
      <strong>${escapeHtml(reviewPageNavCode(page, index))}</strong>
      <span>${escapeHtml(page.title)}</span>
      <small>${escapeHtml(page.navSubtitle || page.subtitle || page.group || "")}</small>
      <em class="${escapeHtml(reviewPageStatusClass(page))}">${escapeHtml(reviewPageStatus(page))}</em>
    </button>
  `).join("");
  artifactReviewPage.innerHTML = renderArtifactReviewPage(activePage, currentResultData);
  hydrateMarkdownPreviews(artifactReviewPage);
  renderReviewFocusStatus();
  if (currentStepId() === "package-outputs") {
    renderChecklistStatus(validateStep("package-outputs", buildPayload(new FormData(form))));
  }
}

function findFileByLabel(files, label) {
  return files.find((file) => String(file.label || "") === label);
}

function permitPdfPageCount(file) {
  const match = String(file?.label || "").match(/\((\d+)\s+pages?\)/i);
  return match ? Number(match[1]) : 0;
}

function permitSheetMeta(pageNumber, pageCount) {
  const withStructuralDraft = pageCount >= 16;
  const sheetNumber = withStructuralDraft ? pageNumber - 2 : pageNumber;
  if (withStructuralDraft && pageNumber === 1) {
    return {
      title: "Structural review draft",
      navCode: "D1",
      priority: "draft",
      status: "draft",
      note: "replace with signed structural letter",
    };
  }
  if (withStructuralDraft && pageNumber === 2) {
    return {
      title: "Structural anchorage draft",
      navCode: "D2",
      priority: "draft",
      status: "draft",
      note: "replace with signed structural letter",
    };
  }
  const titles = {
    1: "PV-1 Cover",
    2: "PV-2 Site Plan",
    3: "PV-3 Property Plan",
    4: "PV-4 Attachment Plan",
    5: "PV-5 Mounting Details",
    6: "EE-1 String Plan",
    7: "EE-2 Three-line Diagram",
    8: "EE-2.1 One-line Diagram",
    9: "EE-3 Electrical Notes",
    10: "NEC Labels, sheet 1",
    11: "NEC Labels, sheet 2",
    12: "EE-5 Placard",
    13: "PV-6 Design Notes",
    14: "PV-7 Site Photos",
    15: "Specification Sheets",
  };
  const conditionalNotes = {
    7: "engineering cross-check",
    13: "check for notes repeated elsewhere",
    14: "replace simulated photos",
    15: "attach manufacturer PDFs",
  };
  const title = titles[sheetNumber] || `Permit page ${pageNumber}`;
  const navCode = String(title).match(/^([A-Z]+-\d+(?:\.\d+)?)/)?.[1]
    || `P${String(pageNumber).padStart(2, "0")}`;
  const priority = conditionalNotes[sheetNumber] ? "conditional" : "core";
  return {
    title,
    navCode,
    priority,
    status: priority === "core" ? "core" : "verify",
    note: conditionalNotes[sheetNumber] || "core sheet",
  };
}

function buildPermitPdfReviewPages(file) {
  const pageCount = permitPdfPageCount(file);
  if (!pageCount) {
    return [];
  }
  return Array.from({ length: pageCount }, (_, index) => {
    const pageNumber = index + 1;
    const meta = permitSheetMeta(pageNumber, pageCount);
    return {
      id: `permit:${file.path}:${pageNumber}`,
      kind: "file",
      group: "Permit drawing set",
      title: meta.title,
      subtitle: `Permit PDF page ${pageNumber} of ${pageCount}.`,
      navSubtitle: `Permit PDF p. ${pageNumber}`,
      file,
      pageNumber,
      wide: true,
      navCode: meta.navCode,
      reviewPriority: meta.priority,
      reviewStatus: meta.status,
      reviewNote: meta.note,
    };
  });
}

function reviewDownloadGroups(files) {
  const groupDefs = [
    {
      key: "verification",
      title: "R8 validation",
      description: "Step-by-step address, satellite, roof trace, and panel layout checks.",
      match: (file) => file.category === "Verification",
    },
    {
      key: "client",
      title: "Client package",
      description: "Files suitable for homeowner or sales review.",
      match: (file) => file.label === "Customer Summary PDF",
    },
    {
      key: "permit",
      title: "Permit drawing set",
      description: "AHJ-facing drawing PDFs and field-printable labels.",
      match: (file) => String(file.label || "").startsWith("Permit Package PDF")
        || String(file.label || "").startsWith("NEC Labels PDF"),
    },
    {
      key: "engineering",
      title: "Engineering and QA",
      description: "Calculation report, readiness reports, and package QA.",
      match: (file) => ["Engineering", "Readiness", "QA"].includes(file.category),
    },
    {
      key: "cad",
      title: "CAD and visual previews",
      description: "DXF source files and PNG previews for internal drafting checks.",
      match: (file) => file.category === "CAD",
    },
    {
      key: "cost",
      title: "Cost exports",
      description: "BOM and quote data for estimating and accounting workflows.",
      match: (file) => file.category === "Cost",
    },
    {
      key: "archive",
      title: "Archive and machine files",
      description: "Inputs, manifests, raw calculation JSON, and the complete ZIP.",
      match: (file) => ["Input", "Manifest", "Archive"].includes(file.category),
    },
  ];
  const assigned = new Set();
  const groups = groupDefs.map((group) => {
    const groupFiles = files.filter((file) => {
      if (assigned.has(file.path) || !group.match(file)) {
        return false;
      }
      assigned.add(file.path);
      return true;
    });
    return { ...group, files: groupFiles };
  });
  const otherFiles = files.filter((file) => !assigned.has(file.path));
  if (otherFiles.length) {
    groups.push({
      key: "other",
      title: "Other files",
      description: "Generated files that do not fit the standard package groups.",
      files: otherFiles,
    });
  }
  return groups;
}

function buildArtifactReviewPages(data) {
  const files = data.files || currentFiles || [];
  const customerSummary = findFileByLabel(files, "Customer Summary PDF");
  const permitPackage = files.find((file) => String(file.label || "").startsWith("Permit Package PDF"));
  const engineeringReport = findFileByLabel(files, "Engineering Report");
  const labelsPdf = files.find((file) => String(file.label || "").startsWith("NEC Labels PDF"));
  const cadPreviews = files.filter((file) => file.category === "CAD" && file.kind === "preview");
  const r8Address = findFileByLabel(files, "R8 Step 1 Address Confirmation");
  const r8Satellite = findFileByLabel(files, "R8 Step 2 Satellite Review PNG");
  const r8StaticSatellite = findFileByLabel(files, "R8 Step 2 Google Static Satellite Fallback PNG");
  const uploadedRoofSatellite = findFileByLabel(files, "Uploaded Roof Satellite Image");
  const satelliteOutlinePng = findFileByLabel(files, "Satellite Roof Outline Candidate PNG");
  const r8Roof = findFileByLabel(files, "R8 Step 3 Roof Trace Layout PNG")
    || findFileByLabel(files, "R8 Step 3 Roof Trace Layout PDF");
  const r8Panel = findFileByLabel(files, "R8 Step 4 Panel Attachment Layout PNG")
    || findFileByLabel(files, "R8 Step 4 Panel Attachment Layout PDF");
  const pages = [
    {
      id: "overview",
      kind: "overview",
      group: "Start",
      title: "Package map",
      subtitle: "Client, permit, engineering, evidence, QA, and download groups.",
    },
  ];
  if (r8Address) {
    pages.push({
      id: `r8-address:${r8Address.path}`,
      kind: "file",
      group: "R8 validation",
      title: "1. Confirm address",
      subtitle: "Verify the U.S. address and coordinates before reading roof geometry.",
      file: r8Address,
      wide: true,
      reviewPriority: "core",
      reviewStatus: "verify",
      reviewNote: "confirm address",
    });
  }
  if (r8Satellite) {
    pages.push({
      id: `r8-satellite:${r8Satellite.path}`,
      kind: "file",
      group: "R8 validation",
      title: "2. Satellite image",
      subtitle: "Confirm the imagery is the intended property before judging roof or panel layout.",
      file: r8Satellite,
      wide: true,
      reviewPriority: "core",
      reviewStatus: "verify",
      reviewNote: "check property match",
    });
  }
  if (r8StaticSatellite) {
    pages.push({
      id: `r8-static-satellite:${r8StaticSatellite.path}`,
      kind: "file",
      group: "R8 validation",
      title: "2B. Static satellite fallback",
      subtitle: "Use this visual fallback for manual tracing when Google Solar mask data is stale or empty.",
      file: r8StaticSatellite,
      wide: true,
      reviewPriority: "core",
      reviewStatus: "verify",
      reviewNote: "manual trace reference",
    });
  }
  if (uploadedRoofSatellite) {
    pages.push({
      id: `uploaded-roof-satellite:${uploadedRoofSatellite.path}`,
      kind: "file",
      group: "R8 validation",
      title: "2C. Uploaded roof reference",
      subtitle: "Use this uploaded roof/satellite reference for manual tracing and Step 2 topology review.",
      file: uploadedRoofSatellite,
      wide: true,
      reviewPriority: "core",
      reviewStatus: "verify",
      reviewNote: "manual trace reference",
    });
  }
  if (satelliteOutlinePng) {
    pages.push({
      id: `satellite-outline:${satelliteOutlinePng.path}`,
      kind: "file",
      group: "R8 validation",
      title: "2A. Roof outline candidate",
      subtitle: "Review the target-building mask contour before accepting it as a trace draft.",
      file: satelliteOutlinePng,
      wide: true,
      reviewPriority: "core",
      reviewStatus: "verify",
      reviewNote: "check outline fit",
    });
  }
  if (r8Roof) {
    pages.push({
      id: `r8-roof:${r8Roof.path}`,
      kind: "file",
      group: "R8 validation",
      title: "3. Roof trace",
      subtitle: "Compare traced roof outline and fire pathways against the satellite image.",
      file: r8Roof,
      wide: true,
      reviewPriority: "core",
      reviewStatus: "verify",
      reviewNote: "check roof geometry",
    });
  }
  if (r8Panel) {
    pages.push({
      id: `r8-panel:${r8Panel.path}`,
      kind: "file",
      group: "R8 validation",
      title: "4. Panel layout",
      subtitle: "Check module placement, setbacks, fire pathway clearance, and attachment layout.",
      file: r8Panel,
      wide: true,
      reviewPriority: "core",
      reviewStatus: "verify",
      reviewNote: "check panel fit",
    });
  }
  if (customerSummary) {
    pages.push({
      id: `client:${customerSummary.path}`,
      kind: "file",
      group: "Client package",
      title: "Customer summary",
      subtitle: "Homeowner-facing estimate summary.",
      file: customerSummary,
      wide: true,
    });
  }
  if (permitPackage) {
    pages.push({
      id: "permit-set",
      kind: "permit_set",
      group: "Permit drawing set",
      title: "Permit set guide",
      subtitle: "Sheet sequence, review priority, and known estimate-only pages.",
      file: permitPackage,
    });
    for (const permitPage of buildPermitPdfReviewPages(permitPackage)) {
      pages.push(permitPage);
    }
  }
  for (const file of cadPreviews) {
    pages.push({
      id: `cad:${file.path}`,
      kind: "file",
      group: "CAD previews",
      title: shortArtifactTitle(file.label),
      subtitle: "Wide-screen DXF visual check.",
      file,
      wide: true,
    });
  }
  if (engineeringReport) {
    pages.push({
      id: `engineering:${engineeringReport.path}`,
      kind: "file",
      group: "Engineering report",
      title: "NEC calculation report",
      subtitle: "Engineering math and code-reference report.",
      file: engineeringReport,
      wide: true,
    });
  }
  if (labelsPdf) {
    pages.push({
      id: `labels:${labelsPdf.path}`,
      kind: "file",
      group: "Labels",
      title: "Label print sheet",
      subtitle: "Standalone label PDF for field printing.",
      file: labelsPdf,
      wide: true,
    });
  }
  pages.push(
    {
      id: "bom",
      kind: "bom",
      group: "Commercial",
      title: "BOM + cost",
      subtitle: "Quote tiers, cost categories, and payback metrics.",
    },
    {
      id: "evidence",
      kind: "evidence",
      group: "Evidence",
      title: "Evidence readiness",
      subtitle: "Source data, missing real-world evidence, and AHJ readiness.",
    },
    {
      id: "deliverables",
      kind: "deliverables",
      group: "Downloads",
      title: "Advanced downloads",
      subtitle: "Raw CAD, JSON, CSV, manifests, and archive files.",
    },
    {
      id: "handoff",
      kind: "handoff",
      group: "Handoff",
      title: "Final handoff",
      subtitle: "Readiness gate, Package QA, required approvals, and ZIP.",
    }
  );
  return pages;
}

function renderArtifactReviewPage(page, data) {
  if (!page) {
    return "";
  }
  if (page.kind === "overview") {
    return renderReviewOverviewPage(data);
  }
  if (page.kind === "file") {
    return renderReviewFilePage(page.file, page);
  }
  if (page.kind === "permit_set") {
    return renderReviewPermitSetPage(page.file);
  }
  if (page.kind === "bom") {
    return renderReviewBomPage(data.bom || {});
  }
  if (page.kind === "evidence") {
    return renderReviewEvidencePage(data);
  }
  if (page.kind === "deliverables") {
    return renderReviewDeliverablesPage(data.files || []);
  }
  if (page.kind === "handoff") {
    return renderReviewHandoffPage(data);
  }
  return "";
}

function renderReviewOverviewPage(data) {
  const summary = data.summary || {};
  const files = data.files || [];
  const readiness = data.readiness || {};
  const gate = readiness.gate || {};
  const roofTrace = readiness.roof_trace || data.source_materials?.roof_trace || {};
  const traceLayout = readiness.trace_module_layout || data.source_materials?.trace_module_layout || {};
  const r8Validation = readiness.r8_validation || data.source_materials?.r8_validation || {};
  const archive = files.find((file) => file.label === "Complete Project ZIP");
  const counts = artifactReviewCounts();
  const groups = reviewDownloadGroups(files);
  return `
    <article class="review-page-card">
      <div class="review-page-heading">
        <div>
          <h4>Package map</h4>
          <p>Review customer-facing output first, then the permit drawing set, engineering report, cost, evidence, and final handoff.</p>
        </div>
        <span class="review-status-pill ${escapeHtml(readinessStatusClass(readiness.status))}">${escapeHtml(readiness.status || "Generated")}</span>
      </div>
      <dl class="review-metric-grid">
        <dt>Project</dt><dd>${escapeHtml(summary.project_name || "-")}</dd>
        <dt>DC size</dt><dd>${escapeHtml(String(summary.system_kw_dc ?? "-"))} kW</dd>
        <dt>Modules</dt><dd>${escapeHtml(String(summary.modules ?? "-"))}</dd>
        <dt>Files</dt><dd>${files.length}</dd>
        <dt>Required approvals</dt><dd>${counts.required ? `${counts.approved}/${counts.required}` : "none"}</dd>
        <dt>Roof geometry</dt><dd>${escapeHtml(roofTraceStatusLabel(roofTrace))}</dd>
        <dt>Module layout</dt><dd>${escapeHtml(traceModuleLayoutStatusLabel(traceLayout))}</dd>
        <dt>R8 validation</dt><dd>${escapeHtml(r8Validation.overall_status || "Not checked")}</dd>
        <dt>Handoff gate</dt><dd>${escapeHtml(gate.level || "Internal review")}</dd>
      </dl>
      <div class="review-two-column">
        ${groups.map((group) => `
          <section class="review-group-card">
            <h5>${escapeHtml(group.title)}</h5>
            <p>${escapeHtml(group.description)}</p>
            <strong>${group.files.length} file${group.files.length === 1 ? "" : "s"}</strong>
          </section>
        `).join("")}
      </div>
      ${archive ? `
        <a class="package-link review-download" href="${withAuthUrl(archive.url)}" target="_blank" rel="noopener">
          Download complete ZIP
        </a>
      ` : "<p class=\"empty inline-empty\">ZIP will appear after Package QA or archive creation.</p>"}
    </article>
  `;
}

function renderReviewFilePage(file, options = {}) {
  if (!file) {
    return "<p class=\"empty\">No preview file is available for this page.</p>";
  }
  const review = artifactReviews[file.path] || { status: "not_reviewed" };
  const required = requiredReviewPaths().has(file.path);
  const pageLabel = options.pageNumber ? `Page ${options.pageNumber}` : "";
  const pageStatus = options.reviewStatus || (options.reviewPriority === "core" ? "core" : "");
  const statusText = pageStatus
    ? `${pageStatus.toUpperCase()} · ${escapeHtml(options.reviewNote || "page review")}`
    : `${required ? "Required review" : "Optional review"} · ${escapeHtml(reviewStatusLabel(review.status))}`;
  return `
    <article class="review-file-page ${options.wide ? "wide-review" : ""}">
      <div class="review-file-viewer">
        ${renderPreviewViewer(file, options)}
      </div>
      <aside class="review-decision-card">
        <h4>${escapeHtml(options.title || file.label)}</h4>
        <span class="review-status-pill ${escapeHtml(pageStatus ? reviewPageStatusClass(options) : reviewStatusClass(review.status))}">
          ${statusText}
        </span>
        ${pageLabel ? `<p>${escapeHtml(pageLabel)} of ${escapeHtml(file.label)}. Approval is saved against the full artifact.</p>` : ""}
        <dl>
          ${options.group ? `<dt>Group</dt><dd>${escapeHtml(options.group)}</dd>` : ""}
          <dt>Category</dt><dd>${escapeHtml(file.category || "Other")}</dd>
          <dt>Type</dt><dd>${escapeHtml(file.kind || "file")}</dd>
          <dt>Size</dt><dd>${formatBytes(file.bytes) || "-"}</dd>
        </dl>
        <label>Review status
          <select data-review-path="${escapeHtml(file.path)}" aria-label="Review status for ${escapeHtml(file.label)}">
            ${reviewStatusOptions(review.status)}
          </select>
        </label>
        <div class="review-decision-actions">
          <button type="button" data-review-action="approved_internal" data-review-path="${escapeHtml(file.path)}">Approve</button>
          <button type="button" class="secondary-button" data-review-action="needs_revision" data-review-path="${escapeHtml(file.path)}">Request changes</button>
        </div>
        <a href="${withAuthUrl(file.url)}" target="_blank" rel="noopener">Open in new tab</a>
      </aside>
    </article>
  `;
}

function renderReviewPermitSetPage(file) {
  const pageCount = permitPdfPageCount(file);
  const pages = buildPermitPdfReviewPages(file);
  return `
    <article class="review-page-card">
      <div class="review-page-heading">
        <div>
          <h4>Permit drawing set guide</h4>
          <p>The permit PDF is split into sheet-by-sheet review pages so each drawing can be checked at maximum width.</p>
        </div>
        <span class="review-status-pill">${pageCount} pages</span>
      </div>
      <div class="review-two-column">
        <section>
          <h5>Keep in the AHJ package</h5>
          <ul class="review-compact-list">
            ${pages.filter((page) => page.reviewPriority === "core").map((page) => `
              <li><span>${escapeHtml(page.title)}</span><strong>core sheet</strong></li>
            `).join("")}
          </ul>
        </section>
        <section>
          <h5>Replace or verify before submission</h5>
          <ul class="review-compact-list">
            ${pages.filter((page) => page.reviewPriority !== "core").map((page) => `
              <li><span>${escapeHtml(page.title)}</span><strong>${escapeHtml(page.reviewNote || "review")}</strong></li>
            `).join("") || "<li><span>No conditional pages detected</span><strong>ready</strong></li>"}
          </ul>
        </section>
      </div>
      <p class="review-note">Layout checks should focus on text overlap, clipped title blocks, unreadable tables, language consistency, placeholder pages, and whether simulated evidence is clearly marked.</p>
    </article>
  `;
}

function renderReviewBomPage(bom) {
  const lines = bom.lines || [];
  const tiers = bom.quote_tiers || [];
  const categories = bom.installed_breakdown || bom.categories || [];
  return `
    <article class="review-page-card">
      <div class="review-page-heading">
        <div>
          <h4>BOM and cost estimate</h4>
          <p>Use this page to review major cost drivers before sending the estimate.</p>
        </div>
        <span class="review-status-pill pass">${money(bom.cost_after_itc_usd)} after ITC</span>
      </div>
      ${tiers.length ? `
        <div class="quote-cards review-quote-cards">
          ${tiers.map((tier) => `
            <article class="quote-card ${tier.is_selected ? "selected" : ""}">
              <div class="quote-title">${escapeHtml(tier.name)}</div>
              <div class="quote-price">${money(tier.cost_after_itc_usd)}</div>
              <div class="quote-sub">${money(tier.installed_cost_usd)} before 30% ITC</div>
            </article>
          `).join("")}
        </div>
      ` : ""}
      <dl class="review-metric-grid">
        <dt>Installed cost</dt><dd>${money(bom.installed_cost_usd)}</dd>
        <dt>Parts subtotal</dt><dd>${money(bom.parts_subtotal_usd)}</dd>
        <dt>Annual savings</dt><dd>${money(bom.annual_bill_savings_usd)}</dd>
        <dt>Payback</dt><dd>${bom.payback_after_itc_years ?? "-"} years</dd>
      </dl>
      <div class="review-two-column">
        <div>
          <h5>Cost categories</h5>
          <ul class="review-compact-list">
            ${categories.map((category) => `
              <li><span>${escapeHtml(category.name)}</span><strong>${money(category.total_usd)}</strong></li>
            `).join("") || "<li><span>No category detail</span></li>"}
          </ul>
        </div>
        <div>
          <h5>BOM lines</h5>
          <ul class="review-compact-list">
            ${lines.slice(0, 10).map((line) => `
              <li><span>${escapeHtml(line.label)}</span><strong>${line.quantity} · ${money(line.total_usd)}</strong></li>
            `).join("") || "<li><span>No BOM lines</span></li>"}
          </ul>
        </div>
      </div>
    </article>
  `;
}

function satelliteCropModeOptions(selected) {
  const value = satelliteCropModes.some((mode) => mode.value === selected)
    ? selected
    : "tight";
  return satelliteCropModes.map((mode) => `
    <option value="${escapeHtml(mode.value)}" ${mode.value === value ? "selected" : ""}>
      ${escapeHtml(mode.label)} — ${escapeHtml(mode.description)}
    </option>
  `).join("");
}

function satelliteCropModeLabel(value) {
  return satelliteCropModes.find((mode) => mode.value === value)?.label || "Tight";
}

function currentSatelliteCropMode(r8Validation = {}) {
  const mode = String(
    r8Validation.satellite_crop_mode
      || form.elements.satellite_crop_mode?.value
      || "tight"
  ).toLowerCase();
  return satelliteCropModes.some((item) => item.value === mode) ? mode : "tight";
}

function renderReviewEvidencePage(data) {
  const source = data.source_materials || {};
  const readiness = data.readiness || {};
  const roofTrace = readiness.roof_trace || source.roof_trace || {};
  const traceLayout = readiness.trace_module_layout || source.trace_module_layout || {};
  const r8Validation = readiness.r8_validation || source.r8_validation || {};
  const roofTopology = readiness.roof_topology || source.roof_topology || {};
  const satelliteCropMode = currentSatelliteCropMode(r8Validation);
  const satelliteOutline = readiness.satellite_roof_outline || source.satellite_roof_outline || r8Validation.satellite_roof_outline || {};
  const satelliteOutlinePng = findFileByLabel(currentFiles, "Satellite Roof Outline Candidate PNG");
  const satelliteOutlineYaml = findFileByLabel(currentFiles, "Satellite EE-4 Trace Candidate YAML");
  const satelliteOutlineJson = findFileByLabel(currentFiles, "Satellite Roof Outline Candidate JSON");
  const photos = source.site_photos || [];
  const missing = source.missing_photo_kinds || [];
  const specCoverage = source.spec_coverage || {};
  const reviewItems = readiness.review_items || [];
  return `
    <article class="review-page-card">
      <div class="review-page-heading">
        <div>
          <h4>Evidence readiness</h4>
          <p>Confirm whether this package is estimate-only or has enough real source data for engineering and AHJ handoff.</p>
        </div>
        <span class="review-status-pill ${source.site_data_source === "real" ? "pass" : "warning"}">
          ${source.site_data_source === "real" ? "Field evidence" : "Simulated evidence"}
        </span>
      </div>
      <dl class="review-metric-grid">
        <dt>PV-7 photos</dt><dd>${source.site_photo_count || 0}/${source.required_site_photo_count || 6}</dd>
        <dt>Utility bill</dt><dd>${source.utility_bill_uploaded ? "uploaded" : "not uploaded"}</dd>
        <dt>Monthly usage</dt><dd>${source.monthly_kwh_count || 0} month(s)</dd>
        <dt>Structural letter</dt><dd>${source.structural_letter_uploaded ? "uploaded" : "not uploaded"}</dd>
        <dt>Roof trace</dt><dd>${escapeHtml(roofTraceStatusLabel(roofTrace))}</dd>
        <dt>Module layout</dt><dd>${escapeHtml(traceModuleLayoutStatusLabel(traceLayout))}</dd>
        <dt>R8 validation</dt><dd>${escapeHtml(r8Validation.overall_status || "Not checked")}</dd>
        <dt>Roof workflow</dt><dd>${escapeHtml(roofTopology.stage || "not started")}</dd>
      </dl>
      ${renderRoofTopologyChecklist(roofTopology)}
      ${roofTrace.detail ? `
        <div class="gate-card ${roofTrace.can_ahj_ready ? "pass" : "warn"}">
          <strong>${escapeHtml(roofTrace.label || "Roof geometry")}</strong>
          <span>${escapeHtml(roofTrace.required_action || roofTrace.detail || "")}</span>
          ${!roofTrace.can_ahj_ready && currentJobId ? `
            <button type="button" class="secondary-button" data-roof-trace-action="accept-draft">
              Accept trace draft and regenerate
            </button>
          ` : ""}
        </div>
      ` : ""}
      ${traceLayout.detail ? `
        <div class="gate-card ${traceLayout.can_ahj_ready ? "pass" : "warn"}">
          <strong>${escapeHtml(traceLayout.label || "Module layout")}</strong>
          <span>${escapeHtml(traceLayout.required_action || traceLayout.detail || "")}</span>
        </div>
      ` : ""}
      <section class="satellite-range-card" data-satellite-range-card>
        <div>
          <h5>Satellite review range</h5>
          <p>Use a smaller crop when the review image includes neighboring roofs. Regeneration keeps the same project data and only updates the satellite review artifacts.</p>
        </div>
        <label>
          Crop range
          <select data-satellite-crop-select aria-label="Satellite review crop range">
            ${satelliteCropModeOptions(satelliteCropMode)}
          </select>
        </label>
        <button type="button" class="secondary-button" data-satellite-crop-action>
          Regenerate satellite review
        </button>
        <span class="review-status-pill">Current: ${escapeHtml(satelliteCropModeLabel(satelliteCropMode))}</span>
      </section>
      ${(satelliteOutline.detail || satelliteOutlinePng || satelliteOutlineYaml || satelliteOutlineJson) ? `
        <section class="satellite-outline-card">
          <div class="satellite-outline-copy">
            <span class="review-status-pill ${satelliteOutline.status === "PASS" ? "pass" : "warning"}">
              ${escapeHtml(satelliteOutline.status || "review")}
            </span>
            <h5>Satellite roof outline candidate</h5>
            <p>${escapeHtml(satelliteOutline.detail || "Review the Google Solar mask-derived outline before using it as an EE-4 trace draft.")}</p>
            <dl class="review-metric-grid compact">
              <dt>Vertices</dt><dd>${escapeHtml(String(satelliteOutline.vertex_count || "-"))}</dd>
              <dt>Area</dt><dd>${satelliteOutline.area_sqft ? `${escapeHtml(String(satelliteOutline.area_sqft))} sqft` : "-"}</dd>
              <dt>Candidate YAML</dt><dd>${satelliteOutlineYaml ? "available" : "not available"}</dd>
              <dt>Audit</dt><dd>${escapeHtml(satelliteOutline.audit_status || "not checked")}</dd>
            </dl>
            <div class="satellite-outline-actions">
              ${satelliteOutlinePng ? `<a href="${withAuthUrl(satelliteOutlinePng.url)}" target="_blank" rel="noopener">Open outline preview</a>` : ""}
              ${satelliteOutlineJson ? `<a href="${withAuthUrl(satelliteOutlineJson.url)}" target="_blank" rel="noopener">Open candidate JSON</a>` : ""}
              ${satelliteOutlineYaml ? `<a href="${withAuthUrl(satelliteOutlineYaml.url)}" target="_blank" rel="noopener">Open candidate YAML</a>` : ""}
              ${satelliteOutlineYaml && currentJobId ? `
                <button type="button" class="secondary-button" data-roof-trace-action="accept-satellite">
                  Accept satellite outline and regenerate
                </button>
              ` : ""}
            </div>
            <p class="review-note">This accepts the roof outline only. Roof facets, ridge/hip lines, fire pathways, and obstructions still need review before AHJ-ready handoff.</p>
          </div>
          ${satelliteOutlinePng ? `
            <a class="satellite-outline-preview" href="${withAuthUrl(satelliteOutlinePng.url)}" target="_blank" rel="noopener">
              <img src="${withAuthUrl(satelliteOutlinePng.url)}" alt="Satellite roof outline candidate preview" />
            </a>
          ` : ""}
        </section>
      ` : ""}
      ${currentJobId ? `
        <section class="manual-roof-trace-card">
          <div>
            <h5>Manual roof trace override</h5>
            <p>Paste a reviewed <code>site.ee4_trace</code> JSON object, then regenerate the package. Use this when Google roof segments do not match the real roof outline.</p>
          </div>
          <textarea
            class="manual-roof-trace-input"
            spellcheck="false"
            aria-label="Manual site.ee4_trace JSON"
          >${escapeHtml(manualRoofTraceEditorValue())}</textarea>
          <div class="manual-roof-trace-actions">
            <button type="button" class="secondary-button" data-roof-trace-action="save-manual">
              Save manual trace and regenerate
            </button>
          </div>
        </section>
      ` : ""}
      <div class="review-two-column">
        <div>
          <h5>Photo evidence</h5>
          <ul class="review-compact-list">
            ${photos.map((photo) => `
              <li><span>${escapeHtml(photo.kind || photo.label || "photo")}</span><strong>${escapeHtml(photo.filename || "uploaded")}</strong></li>
            `).join("") || "<li><span>No site photos uploaded</span></li>"}
          </ul>
        </div>
        <div>
          <h5>Missing / library documents</h5>
          <ul class="review-compact-list">
            ${missing.map((kind) => `<li><span>${escapeHtml(kind)}</span><strong>missing photo</strong></li>`).join("")}
            ${Object.entries(specCoverage).map(([key, value]) => `
              <li><span>${escapeHtml(key)}</span><strong>${escapeHtml(String(value))}</strong></li>
            `).join("") || (!missing.length ? "<li><span>No open source-material issue</span></li>" : "")}
          </ul>
        </div>
      </div>
      <h5>Readiness issues</h5>
      <ul class="review-compact-list">
        ${reviewItems.slice(0, 12).map((item) => `
          <li><span>${escapeHtml(item.key || item.field || "source data")}</span><strong>${escapeHtml(item.detail || item.status || "review")}</strong></li>
        `).join("") || "<li><span>No readiness issue reported</span><strong>ready</strong></li>"}
      </ul>
    </article>
  `;
}

function renderReviewDeliverablesPage(files) {
  const groups = reviewDownloadGroups(files);
  return `
    <article class="review-page-card">
      <div class="review-page-heading">
        <div>
          <h4>Advanced downloads</h4>
          <p>Use these files for internal engineering, CAD work, cost export, QA, or archiving. Customer and permit review happen on the earlier pages.</p>
        </div>
        <span class="review-status-pill">${files.length} files</span>
      </div>
      ${groups.map((group) => `
        <section class="review-download-group">
          <h5>${escapeHtml(group.title)}</h5>
          <p>${escapeHtml(group.description)}</p>
          <ul class="review-file-list">
            ${group.files.map((file) => {
              const review = artifactReviews[file.path] || { status: "not_reviewed" };
              return `
                <li>
                  <a href="${withAuthUrl(file.url)}" target="_blank" rel="noopener">${escapeHtml(file.label)}</a>
                  <span>${escapeHtml(file.category || "Other")} · ${formatBytes(file.bytes)}</span>
                  <select data-review-path="${escapeHtml(file.path)}" aria-label="Review status for ${escapeHtml(file.label)}">
                    ${reviewStatusOptions(review.status)}
                  </select>
                </li>
              `;
            }).join("") || "<li><span>No files in this group</span></li>"}
          </ul>
        </section>
      `).join("")}
    </article>
  `;
}

function renderReviewHandoffPage(data) {
  const readiness = data.readiness || {};
  const gate = readiness.gate || {};
  const qa = data.package_qa || {};
  const roofTopology = readiness.roof_topology || data.source_materials?.roof_topology || {};
  const archive = (data.files || []).find((file) => file.label === "Complete Project ZIP");
  const requiredReviews = gate.required_artifact_reviews || [];
  const blockers = gate.blockers || [];
  const statusClass = gate.can_submit_to_ahj ? "pass" : "warning";
  return `
    <article class="review-page-card">
      <div class="review-page-heading">
        <div>
          <h4>Final handoff</h4>
          <p>Use this page as the final readiness check before releasing an engineering or AHJ-ready package.</p>
        </div>
        <span class="review-status-pill ${statusClass}">${escapeHtml(gate.level || "Internal review")}</span>
      </div>
      <div class="review-handoff-grid">
        <section>
          <h5>Readiness gate</h5>
          <dl class="review-metric-grid compact">
            <dt>Status</dt><dd>${escapeHtml(readiness.status || "-")}</dd>
            <dt>Ready</dt><dd>${readiness.counts?.ready || 0}</dd>
            <dt>Missing</dt><dd>${readiness.counts?.missing || 0}</dd>
            <dt>Simulated</dt><dd>${readiness.counts?.simulated || 0}</dd>
          </dl>
        </section>
        <section>
          <h5>Roof workflow</h5>
          <dl class="review-metric-grid compact">
            <dt>Status</dt><dd>${escapeHtml(roofTopology.status || "not checked")}</dd>
            <dt>Stage</dt><dd>${escapeHtml(roofTopology.stage || "-")}</dd>
            <dt>Modules</dt><dd>${escapeHtml(moduleLayoutCountLabel(roofTopology, {}))}</dd>
            <dt>AHJ-ready</dt><dd>${roofTopology.can_ahj_ready ? "yes" : "no"}</dd>
          </dl>
        </section>
        <section>
          <h5>Package QA</h5>
          <dl class="review-metric-grid compact">
            <dt>Status</dt><dd>${escapeHtml(qa.status || "not run")}</dd>
            <dt>Doctor fail</dt><dd>${qa.summary?.doctor_failed || 0}</dd>
            <dt>Doctor warn</dt><dd>${qa.summary?.doctor_warned || 0}</dd>
            <dt>PDF warn</dt><dd>${qa.summary?.pdf_warned || 0}</dd>
          </dl>
          <button type="button" data-run-package-qa class="secondary-button">Run package QA</button>
        </section>
      </div>
      <div class="review-two-column">
        <div>
          <h5>Required artifact approvals</h5>
          <ul class="review-compact-list">
            ${requiredReviews.map((item) => `
              <li>
                <span>${escapeHtml(item.label || item.path || "")}</span>
                <strong class="${item.status === "approved_internal" ? "review-approved" : "review-pending"}">${escapeHtml(reviewStatusLabel(item.status))}</strong>
              </li>
            `).join("") || "<li><span>No required artifact approvals for selected outputs</span></li>"}
          </ul>
        </div>
        <div>
          <h5>Blocking items</h5>
          <ul class="review-compact-list">
            ${blockers.map((item) => `
              <li><span>${escapeHtml(item.field || item.key)}</span><strong>${escapeHtml(item.detail || "")}</strong></li>
            `).join("") || "<li><span>No AHJ-ready blockers detected</span></li>"}
          </ul>
        </div>
      </div>
      ${archive ? `<a class="package-link review-download" href="${withAuthUrl(archive.url)}" target="_blank" rel="noopener">Download final ZIP</a>` : ""}
    </article>
  `;
}

function renderReviewFocusStatus() {
  if (!reviewFocusBar || !currentResultData || currentStepId() !== "package-outputs") {
    return;
  }
  const counts = artifactReviewCounts();
  const readiness = currentReadiness || {};
  const gate = readiness.gate || {};
  const qa = currentResultData.package_qa || {};
  const archiveReady = (currentResultData.files || []).some((file) => file.label === "Complete Project ZIP");
  const remaining = Math.max(0, counts.required - counts.approved);
  reviewFocusBar.innerHTML = `
    <div class="review-focus-metrics">
      <span><strong>Page</strong>${artifactReviewPageIndex + 1}/${artifactReviewPages.length || 1}</span>
      <span class="${remaining ? "warning" : "pass"}"><strong>Approvals</strong>${counts.required ? `${counts.approved}/${counts.required}` : "optional"}</span>
      <span><strong>Readiness</strong>${escapeHtml(gate.level || readiness.status || "review")}</span>
      <span class="${qa.status === "PASS" ? "pass" : (qa.status ? "warning" : "")}"><strong>QA</strong>${escapeHtml(qa.status || "not run")}</span>
      <span class="${archiveReady ? "pass" : ""}"><strong>ZIP</strong>${archiveReady ? "ready" : "pending"}</span>
    </div>
    <button type="button" class="secondary-button" data-review-status-toggle>Status details</button>
  `;
  if (reviewStatusDrawer && !reviewStatusDrawer.classList.contains("hidden")) {
    renderReviewStatusDrawer();
  }
}

function handleReviewFocusBarClick(event) {
  if (event.target.closest("[data-review-status-toggle]")) {
    openReviewStatusDrawer();
  }
}

function handleReviewStatusDrawerClick(event) {
  if (event.target.closest("[data-review-status-close]")) {
    closeReviewStatusDrawer();
  }
}

function openReviewStatusDrawer() {
  if (!reviewStatusDrawer) {
    return;
  }
  renderReviewStatusDrawer();
  reviewStatusDrawer.classList.remove("hidden");
  reviewStatusDrawer.setAttribute("aria-hidden", "false");
}

function closeReviewStatusDrawer() {
  if (!reviewStatusDrawer) {
    return;
  }
  reviewStatusDrawer.classList.add("hidden");
  reviewStatusDrawer.setAttribute("aria-hidden", "true");
}

function renderReviewStatusDrawer() {
  if (!reviewStatusDrawerBody || !currentResultData) {
    return;
  }
  const payload = buildPayload(new FormData(form));
  const validation = validateStep("package-outputs", payload);
  const issues = [
    ...validation.errors.map((item) => ({ ...item, level: "error", label: "Error" })),
    ...validation.warnings.map((item) => ({ ...item, level: "warning", label: "Warning" })),
  ];
  const gate = currentReadiness?.gate || {};
  const blockers = gate.blockers || [];
  const requiredReviews = gate.required_artifact_reviews || [];
  const qa = currentResultData.package_qa || {};
  reviewStatusDrawerBody.innerHTML = `
    <section>
      <h4>Review progress</h4>
      <dl class="review-metric-grid compact">
        <dt>Page</dt><dd>${artifactReviewPageIndex + 1}/${artifactReviewPages.length || 1}</dd>
        <dt>Required approvals</dt><dd>${artifactReviewCounts().approved}/${artifactReviewCounts().required || 0}</dd>
        <dt>Gate</dt><dd>${escapeHtml(gate.level || "Internal review")}</dd>
        <dt>Package QA</dt><dd>${escapeHtml(qa.status || "not run")}</dd>
      </dl>
    </section>
    <section>
      <h4>Checklist</h4>
      <ul class="review-compact-list">
        ${issues.slice(0, 10).map((item) => `
          <li><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.message)}</strong></li>
        `).join("") || "<li><span>Checklist</span><strong>No blocking Step 6 issues</strong></li>"}
      </ul>
    </section>
    <section>
      <h4>Required approvals</h4>
      <ul class="review-compact-list">
        ${requiredReviews.map((item) => `
          <li>
            <span>${escapeHtml(item.label || item.path || "")}</span>
            <strong class="${item.status === "approved_internal" ? "review-approved" : "review-pending"}">${escapeHtml(reviewStatusLabel(item.status))}</strong>
          </li>
        `).join("") || "<li><span>Approvals</span><strong>No required artifact approvals</strong></li>"}
      </ul>
    </section>
    <section>
      <h4>Blocking items</h4>
      <ul class="review-compact-list">
        ${blockers.map((item) => `
          <li><span>${escapeHtml(item.field || item.key)}</span><strong>${escapeHtml(item.detail || "")}</strong></li>
        `).join("") || "<li><span>Gate</span><strong>No AHJ-ready blockers detected</strong></li>"}
      </ul>
    </section>
  `;
}

function handleArtifactReviewPagerClick(event) {
  const satelliteCropButton = event.target.closest("[data-satellite-crop-action]");
  if (satelliteCropButton) {
    updateSatelliteReviewRange(satelliteCropButton);
    return;
  }

  const pageButton = event.target.closest("[data-review-page]");
  if (pageButton) {
    artifactReviewPageIndex = Number(pageButton.dataset.reviewPage);
    renderArtifactReviewWorkbench();
    return;
  }
  if (event.target.closest("#artifact-review-prev")) {
    artifactReviewPageIndex = Math.max(0, artifactReviewPageIndex - 1);
    renderArtifactReviewWorkbench();
    return;
  }
  if (event.target.closest("#artifact-review-next")) {
    artifactReviewPageIndex = Math.min(artifactReviewPages.length - 1, artifactReviewPageIndex + 1);
    renderArtifactReviewWorkbench();
    return;
  }
  const reviewButton = event.target.closest("[data-review-action]");
  if (reviewButton) {
    saveArtifactReview(reviewButton.dataset.reviewPath, reviewButton.dataset.reviewAction);
    return;
  }
  if (event.target.closest("[data-run-package-qa]")) {
    runPackageQa();
    return;
  }
  const roofTraceButton = event.target.closest("[data-roof-trace-action]");
  if (roofTraceButton) {
    if (roofTraceButton.dataset.roofTraceAction === "save-manual") {
      saveManualRoofTrace(roofTraceButton);
    } else if (roofTraceButton.dataset.roofTraceAction === "accept-satellite") {
      acceptSatelliteRoofTrace(roofTraceButton);
    } else {
      acceptRoofTraceDraft(roofTraceButton);
    }
  }
}

function artifactReviewCounts() {
  const required = requiredReviewPaths();
  const approvedRequired = [...required].filter((path) => (
    (artifactReviews[path]?.status || "not_reviewed") === "approved_internal"
  )).length;
  const approved = Object.values(artifactReviews).filter((review) => review.status === "approved_internal").length;
  return {
    required: required.size,
    approved: required.size ? approvedRequired : approved,
  };
}

function requiredReviewPaths() {
  const reviews = currentReadiness?.gate?.required_artifact_reviews || [];
  return new Set(reviews.map((item) => item.path).filter(Boolean));
}

function reviewPageNavCode(page, index) {
  return page.navCode || String(index + 1).padStart(2, "0");
}

function reviewPageStatus(page) {
  if (page.reviewStatus) {
    return page.reviewStatus;
  }
  if (page.kind === "file") {
    const status = artifactReviews[page.file.path]?.status || "not_reviewed";
    if (requiredReviewPaths().has(page.file.path) && status !== "approved_internal") {
      return "required";
    }
    return reviewStatusLabel(status);
  }
  if (page.kind === "handoff") {
    return currentReadiness?.gate?.can_submit_to_ahj ? "ready" : "review";
  }
  if (page.kind === "overview") {
    return currentReadiness?.status || "ready";
  }
  if (page.kind === "permit_set") {
    return "guide";
  }
  if (page.kind === "bom") {
    return "cost";
  }
  if (page.kind === "evidence") {
    return currentResultData?.source_materials?.site_data_source === "real" ? "field" : "estimate";
  }
  return "files";
}

function reviewPageStatusClass(page) {
  const status = reviewPageStatus(page);
  if (["approved", "ready", "PASS", "field"].includes(status)) {
    return "pass";
  }
  if (["required", "needs revision", "review", "WARN", "estimate", "draft", "verify"].includes(status)) {
    return "warning";
  }
  if (status === "core") {
    return "core";
  }
  return "";
}

function reviewStatusClass(status) {
  if (status === "approved_internal") {
    return "pass";
  }
  if (status === "needs_revision") {
    return "warning";
  }
  return "";
}

function readinessStatusClass(status) {
  if (status === "PASS") {
    return "pass";
  }
  if (status === "FAIL") {
    return "fail";
  }
  return status ? "warning" : "";
}

function shortArtifactTitle(label) {
  return String(label || "Artifact")
    .replace(" Preview", "")
    .replace("PDF", "PDF")
    .slice(0, 34);
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
      if (currentResultData) {
        currentResultData.readiness = currentReadiness;
      }
    }
    renderFiles(currentFiles);
    renderPreviews(currentFiles);
    renderArtifactReviewWorkbench();
  } catch {
    artifactReviews = {};
  }
}

async function handleArtifactReviewChange(event) {
  const select = event.target.closest("[data-review-path]");
  if (!select || !currentJobId) {
    return;
  }
  await saveArtifactReview(select.dataset.reviewPath, select.value);
}

async function saveArtifactReview(path, status) {
  if (!path || !status || !currentJobId) {
    return;
  }
  try {
    const response = await apiFetch(`/api/jobs/${currentJobId}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path,
        status,
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
      if (currentResultData) {
        currentResultData.readiness = currentReadiness;
      }
    }
    renderFiles(currentFiles);
    renderPreviews(currentFiles);
    renderArtifactReviewWorkbench();
    statusEl.textContent = "Review status saved.";
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
}

async function updateSatelliteReviewRange(button) {
  if (!currentJobId) {
    return;
  }
  const card = button.closest("[data-satellite-range-card]") || artifactReviewPage;
  const select = card?.querySelector("[data-satellite-crop-select]");
  const satelliteCropMode = String(select?.value || "tight");
  if (form.elements.satellite_crop_mode) {
    form.elements.satellite_crop_mode.value = satelliteCropMode;
    localAutosave();
  }
  try {
    button.disabled = true;
    button.textContent = "Regenerating...";
    statusEl.textContent = `Regenerating satellite review with ${satelliteCropModeLabel(satelliteCropMode)} crop.`;
    const response = await apiFetch(`/api/jobs/${encodeURIComponent(currentJobId)}/satellite-review-range`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ satellite_crop_mode: satelliteCropMode, rerun: true }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    renderResult(data);
    if (roofPreviewPanel?.dataset.status && roofPreviewPanel.dataset.status !== "empty") {
      renderRoofPreviewResult(data);
    }
    statusEl.textContent = `Satellite review regenerated with ${satelliteCropModeLabel(satelliteCropMode)} crop.`;
    await loadHistory();
  } catch (error) {
    button.disabled = false;
    button.textContent = "Regenerate satellite review";
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
}

async function acceptSatelliteRoofTrace(button) {
  return acceptRoofTraceSource(
    button,
    "satellite_candidate",
    {
      pending: "Accepting satellite roof outline and regenerating package.",
      success: "Satellite roof outline accepted. Package regenerated with a review-only roof outline draft.",
      reset: "Accept satellite outline and regenerate",
    },
  );
}

async function acceptRoofTraceDraft(button) {
  const source = button?.dataset?.roofPreviewSource || "draft_yaml";
  const usesSatellite = source === "satellite_candidate";
  return acceptRoofTraceSource(
    button,
    source,
    {
      pending: usesSatellite
        ? "Accepting satellite roof topology and regenerating preview."
        : "Accepting full roof topology and regenerating preview.",
      success: usesSatellite
        ? "Satellite roof topology accepted. Downstream package generation will use the saved EE-4 trace."
        : "Roof topology accepted. Downstream package generation will use the saved EE-4 trace.",
      reset: usesSatellite
        ? "Accept satellite topology and regenerate preview"
        : "Accept full topology and regenerate preview",
    },
  );
}

async function acceptRoofTraceSource(button, source, messages) {
  if (!currentJobId) {
    return;
  }
  try {
    button.disabled = true;
    button.textContent = "Regenerating...";
    statusEl.textContent = messages.pending;
    const response = await apiFetch(`/api/jobs/${encodeURIComponent(currentJobId)}/roof-trace/accept-draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, rerun: true }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    try {
      const payloadResponse = await apiFetch(`/api/jobs/${encodeURIComponent(currentJobId)}/payload`);
      const payload = await payloadResponse.json();
      if (payloadResponse.ok) {
        lastEe4Trace = payload.ee4_trace || null;
      }
    } catch {
      // Keeping the regenerated result is enough; payload refresh is best-effort.
    }
    renderResult(data);
    if (roofPreviewPanel?.dataset.status && roofPreviewPanel.dataset.status !== "empty") {
      renderRoofPreviewResult(data);
    }
    renderCurrentStepValidation({ quiet: false });
    statusEl.textContent = messages.success;
    await loadHistory();
  } catch (error) {
    button.disabled = false;
    button.textContent = messages.reset;
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
}

async function saveEditedRoofOutline(button) {
  if (!currentJobId) {
    return;
  }
  const editor = button.closest("[data-roof-outline-editor]");
  if (!editor) {
    return;
  }
  let vertices = roofOutlineEditorVertices(editor);
  if (vertices.length < 3) {
    statusEl.textContent = "Roof outline needs at least 3 vertices.";
    statusEl.classList.add("error");
    return;
  }
  if (signedRoofArea(vertices) < 0) {
    vertices = [...vertices].reverse();
  }
  let baseTrace = {};
  try {
    const traceScript = editor.querySelector("[data-roof-editor-trace]");
    baseTrace = JSON.parse(traceScript?.textContent || "{}");
  } catch {
    baseTrace = {};
  }
  const trace = {
    ...baseTrace,
    enabled: true,
    roof_outline: {
      ...(baseTrace.roof_outline || {}),
      name: "Reviewed Step 2 roof outline",
      vertices,
    },
  };
  try {
    button.disabled = true;
    button.textContent = "Saving...";
    statusEl.textContent = "Saving edited roof outline and regenerating the topology preview.";
    const response = await apiFetch(`/api/jobs/${encodeURIComponent(currentJobId)}/roof-trace/accept-draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "manual", trace, rerun: true }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    lastEe4Trace = trace;
    renderResult(data);
    if (roofPreviewPanel?.dataset.status && roofPreviewPanel.dataset.status !== "empty") {
      renderRoofPreviewResult(data);
    }
    renderCurrentStepValidation({ quiet: false });
    statusEl.textContent = "Edited roof outline saved. Downstream drawings now use the reviewed Step 2 topology.";
    await loadHistory();
  } catch (error) {
    button.disabled = false;
    button.textContent = "Save edited outline";
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
}

async function generateRoofTopologyProposal(button) {
  if (!currentJobId) {
    return;
  }
  try {
    button.disabled = true;
    button.textContent = "Generating...";
    statusEl.textContent = "Generating a structured roof-topology proposal with the PVESS skill.";
    const response = await apiFetch(`/api/jobs/${encodeURIComponent(currentJobId)}/roof-topology/proposal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "deterministic", strict: false }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    currentFiles = data.files || currentFiles;
    if (currentResultData) {
      currentResultData.files = currentFiles;
      currentResultData.roof_topology_proposal = data.qa || {};
    }
    renderFiles(currentFiles);
    renderPreviews(currentFiles);
    renderDeliveryPackage(currentFiles);
    renderArtifactReviewWorkbench();
    statusEl.textContent = `Roof topology proposal generated: ${data.status || "review"}. Open the proposal YAML/PDF in Advanced downloads.`;
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Generate skill topology proposal";
  }
}

async function saveManualRoofTrace(button) {
  if (!currentJobId) {
    return;
  }
  const card = button.closest(".manual-roof-trace-card");
  const input = card?.querySelector(".manual-roof-trace-input");
  if (!input) {
    return;
  }
  let trace;
  try {
    trace = parseManualRoofTrace(input.value);
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
    return;
  }
  try {
    button.disabled = true;
    button.textContent = "Regenerating...";
    statusEl.textContent = "Saving manual roof trace and regenerating package.";
    const response = await apiFetch(`/api/jobs/${encodeURIComponent(currentJobId)}/roof-trace/accept-draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "manual", trace, rerun: true }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    lastEe4Trace = trace;
    renderResult(data);
    if (roofPreviewPanel?.dataset.status && roofPreviewPanel.dataset.status !== "empty") {
      renderRoofPreviewResult(data);
    }
    renderCurrentStepValidation({ quiet: false });
    statusEl.textContent = "Manual roof trace saved. Package regenerated with reviewed geometry.";
    await loadHistory();
  } catch (error) {
    button.disabled = false;
    button.textContent = "Save manual trace and regenerate";
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
}

function parseManualRoofTrace(value) {
  let parsed;
  try {
    parsed = JSON.parse(value || "{}");
  } catch (error) {
    throw new Error(`Manual roof trace JSON is invalid: ${error.message}`);
  }
  const trace = parsed?.site?.ee4_trace || parsed?.ee4_trace || parsed;
  if (!trace || typeof trace !== "object" || Array.isArray(trace)) {
    throw new Error("Manual roof trace must be a JSON object.");
  }
  if (!trace.roof_outline && !Array.isArray(trace.roof_facets)) {
    throw new Error("Manual roof trace must include roof_outline or roof_facets.");
  }
  return { ...trace, enabled: true };
}

function manualRoofTraceEditorValue() {
  return JSON.stringify(lastEe4Trace || manualRoofTraceTemplate(), null, 2);
}

function manualRoofTraceTemplate() {
  return {
    enabled: true,
    roof_outline: {
      name: "Reviewed roof outline",
      vertices: [
        [0, 0],
        [60, 0],
        [60, 28],
        [0, 28],
      ],
    },
    roof_facets: [],
    roof_lines: [
      {
        kind: "ridge",
        points: [
          [0, 14],
          [60, 14],
        ],
      },
    ],
    fire_pathways: [
      {
        name: "Fire setback",
        vertices: [
          [0, 26],
          [60, 26],
          [60, 28],
          [0, 28],
        ],
      },
    ],
    symbols: [],
  };
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
  hydrateMarkdownPreviews(previewPanel);
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
    hydrateMarkdownPreviews(previewPanel);
  }
}

function renderPreviewViewer(file, options = {}) {
  if (!file) {
    return "";
  }
  const url = previewUrl(file, options);
  let body = `<iframe src="${url}" title="${escapeHtml(file.label)}"></iframe>`;
  if (file.kind === "preview") {
    body = `<img src="${url}" alt="${escapeHtml(file.label)}" />`;
  } else if (file.kind === "pdf" && options.pageNumber) {
    body = `
      <img
        class="pdf-page-preview"
        src="${url}"
        alt="${escapeHtml(options.title || file.label)} page ${Number(options.pageNumber)}"
        onerror="this.closest('.preview-viewer').classList.add('preview-load-failed')"
      />
      <div class="preview-load-error">
        PDF page preview is unavailable. Open the PDF in a new tab while the preview service is checked.
      </div>
    `;
  } else if (file.kind === "markdown") {
    body = `
      <article class="markdown-preview" data-markdown-url="${url}">
        <div class="markdown-loading">Loading formatted report...</div>
      </article>
    `;
  }
  return `
    <div class="preview-viewer">
      <div class="preview-viewer-header">
        <strong>${escapeHtml(options.title || file.label)}</strong>
        <span>${formatBytes(file.bytes)}</span>
      </div>
      ${body}
    </div>
  `;
}

function previewUrl(file, options = {}) {
  if (file.kind === "pdf" && options.pageNumber) {
    const page = Number(options.pageNumber);
    const path = encodeURIComponent(file.path || "");
    return withAuthUrl(`/api/jobs/${encodeURIComponent(currentJobId)}/permit-preview/${page}?path=${path}`);
  }
  return withAuthUrl(file.url);
}

function hydrateMarkdownPreviews(scope = document) {
  for (const node of scope.querySelectorAll(".markdown-preview[data-markdown-url]")) {
    if (node.dataset.loaded === "true") {
      continue;
    }
    node.dataset.loaded = "true";
    fetch(requestUrl(node.dataset.markdownUrl))
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.text();
      })
      .then((text) => {
        node.innerHTML = renderMarkdownDocument(text);
      })
      .catch((error) => {
        node.innerHTML = `
          <div class="markdown-error">
            <strong>Report preview failed</strong>
            <span>${escapeHtml(error.message)}</span>
          </div>
        `;
      });
  }
}

function renderMarkdownDocument(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = Math.min(heading[1].length, 4);
      html.push(`<h${level}>${formatMarkdownInline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (isMarkdownTableRow(trimmed) && isMarkdownTableSeparator(lines[index + 1] || "")) {
      const headers = splitMarkdownTableRow(trimmed);
      index += 2;
      const rows = [];
      while (index < lines.length && isMarkdownTableRow(lines[index].trim())) {
        rows.push(splitMarkdownTableRow(lines[index].trim()));
        index += 1;
      }
      html.push(renderMarkdownTable(headers, rows));
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quote = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quote.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      html.push(`<blockquote>${formatMarkdownInline(quote.join(" "))}</blockquote>`);
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      html.push(`<ul>${items.map((item) => `<li>${formatMarkdownInline(item)}</li>`).join("")}</ul>`);
      continue;
    }

    const paragraph = [trimmed];
    index += 1;
    while (
      index < lines.length
      && lines[index].trim()
      && !/^(#{1,4})\s+/.test(lines[index].trim())
      && !(isMarkdownTableRow(lines[index].trim()) && isMarkdownTableSeparator(lines[index + 1] || ""))
      && !lines[index].trim().startsWith(">")
      && !/^[-*]\s+/.test(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    html.push(`<p>${formatMarkdownInline(paragraph.join(" "))}</p>`);
  }
  return html.join("");
}

function isMarkdownTableRow(line) {
  return line.startsWith("|") && (line.match(/\|/g) || []).length >= 2;
}

function isMarkdownTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line || "");
}

function splitMarkdownTableRow(line) {
  return line
    .replace(/^\s*\|/, "")
    .replace(/\|\s*$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderMarkdownTable(headers, rows) {
  return `
    <div class="markdown-table-wrap">
      <table class="markdown-table">
        <thead>
          <tr>${headers.map((cell) => `<th>${formatMarkdownInline(cell)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              ${headers.map((_header, index) => `<td>${formatMarkdownInline(row[index] || "")}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function formatMarkdownInline(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
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
  leadEmpty.textContent = "Public estimate requests appear here.";
  try {
    const response = await apiFetch(`/api/leads${leadQueryString()}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    renderLeads(data.leads || []);
    loadLeadDigest();
    loadLeadMetrics();
    loadLeadNotifications();
  } catch {
    leadList.innerHTML = "";
    leadEmpty.textContent = "Lead list is unavailable.";
    leadEmpty.classList.remove("hidden");
    leadMetricsPanel.classList.add("hidden");
    leadNotificationPanel.classList.add("hidden");
  }
}

async function loadLeadDigest() {
  try {
    const response = await apiFetch("/api/leads/digest");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    renderLeadDigest(data);
  } catch {
    leadDigest.classList.add("hidden");
  }
}

async function loadLeadMetrics() {
  try {
    const response = await apiFetch("/api/leads/metrics");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    renderLeadMetrics(data);
  } catch {
    leadMetricsPanel.classList.add("hidden");
  }
}

function renderLeadMetrics(data) {
  const bySource = data.by_source || [];
  const byCampaign = data.by_campaign || [];
  leadMetricsPanel.classList.toggle("hidden", !data.total);
  if (!data.total) {
    leadMetricsPanel.innerHTML = "";
    return;
  }
  leadMetricsPanel.innerHTML = `
    <div class="lead-metrics-head">
      <strong>Marketing attribution</strong>
      <span>${Number(data.total || 0)} leads · ${Math.round(Number(data.conversion_rate || 0) * 100)}% converted</span>
    </div>
    <dl>
      ${bySource.slice(0, 4).map((item) => `
        <dt>${escapeHtml(item.key || "direct")}</dt>
        <dd>${Number(item.count || 0)}</dd>
      `).join("") || "<dt>direct</dt><dd>0</dd>"}
    </dl>
    ${byCampaign.length ? `
      <small>Campaigns: ${byCampaign.slice(0, 3).map((item) => `${escapeHtml(item.key)} (${Number(item.count || 0)})`).join(", ")}</small>
    ` : ""}
  `;
}

async function loadLeadNotifications() {
  try {
    const response = await apiFetch("/api/leads/notifications?limit=5");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    renderLeadNotifications(data.notifications || []);
  } catch {
    leadNotificationPanel.classList.add("hidden");
  }
}

function renderLeadNotifications(notifications) {
  leadNotificationPanel.classList.toggle("hidden", notifications.length === 0);
  if (!notifications.length) {
    leadNotificationPanel.innerHTML = "";
    return;
  }
  leadNotificationPanel.innerHTML = `
    <div class="lead-notification-head">
      <strong>Lead notifications</strong>
      <span>${notifications.length} recent events</span>
    </div>
    <ul>
      ${notifications.map((item) => `
        <li class="lead-notification ${escapeHtml(item.status || "pending")}">
          <span>
            <strong>${escapeHtml(notificationStatusLabel(item.status))}</strong>
            <em>${escapeHtml(item.subject || item.event || "Lead notification")}</em>
            <small>${escapeHtml(item.channel || "")} · ${escapeHtml(formatLeadDate(item.created_at) || "recent")}${item.error ? ` · ${escapeHtml(item.error)}` : ""}</small>
          </span>
          ${item.status === "failed" ? `<button type="button" data-lead-notification-retry="${escapeHtml(item.notification_id)}">Retry</button>` : ""}
        </li>
      `).join("")}
    </ul>
  `;
}

function notificationStatusLabel(value) {
  if (value === "sent") {
    return "Sent";
  }
  if (value === "failed") {
    return "Failed";
  }
  if (value === "skipped") {
    return "Skipped";
  }
  return "Pending";
}

function renderLeadDigest(data) {
  const counts = data.counts || {};
  leadDigest.classList.toggle("hidden", !data.total);
  leadDigest.innerHTML = `
    <strong>${escapeHtml(data.summary || "No active leads")}</strong>
    <span>${Number(data.total || 0)} active leads</span>
    <span>${Number(counts.new || 0)} new</span>
    <span>${Number(counts.qualified || 0)} qualified</span>
    <span>${(data.stale_leads || []).length} need follow-up</span>
  `;
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
        <em>${escapeHtml(leadAttributionLabel(lead))}</em>
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
        <button type="button" data-lead-action="draft" data-lead-id="${escapeHtml(lead.lead_id)}">Email draft</button>
        <button type="button" data-lead-action="payload" data-lead-id="${escapeHtml(lead.lead_id)}">Load intake</button>
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

function leadAttributionLabel(lead) {
  const source = lead.campaign_source || "direct";
  const medium = lead.campaign_medium ? ` / ${lead.campaign_medium}` : "";
  const campaign = lead.campaign_name ? ` · ${lead.campaign_name}` : "";
  return `source ${source}${medium}${campaign}`;
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

leadNotificationPanel.addEventListener("click", async (event) => {
  const retryButton = event.target.closest("[data-lead-notification-retry]");
  if (!retryButton) {
    return;
  }
  retryButton.disabled = true;
  retryButton.textContent = "Retrying...";
  try {
    const response = await apiFetch(`/api/leads/notifications/${encodeURIComponent(retryButton.dataset.leadNotificationRetry)}/retry`, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data));
    }
    statusEl.textContent = `Retried lead notification ${data.notification_id}`;
    await loadLeadNotifications();
  } catch (error) {
    retryButton.disabled = false;
    retryButton.textContent = "Retry";
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
    renderError(error.message);
  }
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
    if (action === "draft") {
      actionButton.disabled = true;
      actionButton.textContent = "Drafting...";
      const response = await apiFetch(`/api/leads/${encodeURIComponent(leadId)}/followup-draft`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(data));
      }
      renderLeadDraft(data);
      statusEl.textContent = `Prepared follow-up draft for lead ${leadId}`;
      actionButton.disabled = false;
      actionButton.textContent = "Email draft";
      return;
    }
    if (action === "payload") {
      actionButton.disabled = true;
      actionButton.textContent = "Loading...";
      const response = await apiFetch(`/api/leads/${encodeURIComponent(leadId)}/payload`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(formatApiError(payload));
      }
      applyPayloadToForm(payload);
      statusEl.textContent = `Loaded intake fields from lead ${leadId}`;
      actionButton.disabled = false;
      actionButton.textContent = "Load intake";
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

function renderLeadDraft(data) {
  leadDraftPanel.classList.remove("hidden");
  leadDraftSubject.textContent = data.subject || "";
  leadDraftBody.value = data.body || "";
  leadDraftMailto.href = data.mailto_url || "#";
}

function renderReadiness(readiness) {
  const counts = readiness.counts || {};
  const reviewItems = readiness.review_items || [];
  const gate = readiness.gate || {};
  const roofTrace = readiness.roof_trace || {};
  const traceLayout = readiness.trace_module_layout || {};
  const r8Validation = readiness.r8_validation || {};
  const roofTopology = readiness.roof_topology || {};
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
    <div class="gate-card ${roofTrace.can_ahj_ready ? "pass" : "warn"}">
      <strong>Roof geometry</strong>
      <span>${escapeHtml(roofTraceStatusLabel(roofTrace))}</span>
    </div>
    <div class="gate-card ${traceLayout.can_ahj_ready ? "pass" : "warn"}">
      <strong>Module layout</strong>
      <span>${escapeHtml(traceModuleLayoutStatusLabel(traceLayout))}</span>
    </div>
    <div class="gate-card ${roofTopology.status === "PASS" ? "pass" : "warn"}">
      <strong>Roof workflow</strong>
      <span>${escapeHtml(roofTopology.stage || roofTopology.required_action || "Step 2 roof workflow not checked")}</span>
    </div>
    <div class="gate-card ${r8Validation.overall_status === "PASS" ? "pass" : "warn"}">
      <strong>R8 validation sequence</strong>
      <span>${escapeHtml(r8Validation.overall_status || "Not checked")} · address, satellite, roof trace, and panel layout</span>
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
    if (currentResultData) {
      currentResultData = {
        ...currentResultData,
        files: data.files || currentResultData.files || [],
        package_qa: data.package_qa || currentResultData.package_qa || {},
      };
    }
    renderArtifactReviewWorkbench();
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

function applyPayloadToForm(payload, options = {}) {
  for (const [key, value] of Object.entries(payload || {})) {
    if (key === "outputs") {
      continue;
    }
    if (key === "monthly_kwh") {
      const monthly = Array.isArray(value) ? value.join(", ") : "";
      setFieldValue("monthly_usage_mode", monthly ? "monthly_detail" : "local_default");
      setFieldValue("monthly_kwh_text", monthly);
      continue;
    }
    if (key === "roof_sections") {
      lastLookupRoofSections = normalizeRoofSections(value);
      continue;
    }
    if (key === "ee4_trace") {
      lastEe4Trace = value && typeof value === "object" ? value : null;
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
  syncUsageMode();
  syncSelfConsumptionProfile();
  syncRoofAssumptionSummary();
  const message = options.message || "Loaded a prior project form. Reattach file uploads before rerunning with new source materials.";
  renderValidation([], [message]);
  if (!options.preserveStep) {
    setWizardStep(0, { validate: false });
  } else {
    renderCurrentStepValidation({ quiet: false });
  }
  localAutosave();
}

function setFieldValue(name, value) {
  if (name === "site_address") {
    setRawFieldValue("site_address", value);
    applyUsAddressString(value);
    return;
  }
  if (name === "location") {
    setRawFieldValue("location", value);
    applyLocationString(value);
    return;
  }
  setRawFieldValue(name, value);
}

function setRawFieldValue(name, value) {
  const field = form.elements[name] || document.querySelector(`[name="${name}"]`);
  if (!field || field.type === "file") {
    return;
  }
  if (field.type === "checkbox") {
    field.checked = Boolean(value);
    return;
  }
  const normalized = legacySelectValues[name]?.[value] || value;
  if (name === "self_consumption_fraction" && selfConsumptionProfile) {
    const fraction = Number(normalized);
    const match = [...selfConsumptionProfile.options].find((option) => (
      Math.abs(Number(option.dataset.fraction || 0) - fraction) < 0.001
    ));
    if (match) {
      selfConsumptionProfile.value = match.value;
    }
  }
  field.value = normalized ?? "";
}

function applyUsAddressString(value) {
  const text = String(value || "").trim();
  if (!text) {
    return;
  }
  const parts = text.split(",").map((part) => part.trim()).filter(Boolean);
  if (/^(united states|usa|us)$/i.test(parts[parts.length - 1] || "")) {
    parts.pop();
  }
  if (parts[0]) {
    setRawFieldValue("address_line1", parts[0]);
  }
  let unit = "";
  let city = parts.length >= 3 ? parts[parts.length - 2] : "";
  let stateZip = parts.length >= 2 ? parts[parts.length - 1] : "";
  const hasSeparateZip = parts.length >= 4
    && /^\d{5}(?:-\d{4})?$/.test(parts[parts.length - 1])
    && /^[A-Z]{2}$/i.test(parts[parts.length - 2]);
  if (hasSeparateZip) {
    city = parts[parts.length - 3] || "";
    stateZip = `${parts[parts.length - 2]} ${parts[parts.length - 1]}`.trim();
    unit = parts.slice(1, -3).join(", ");
  } else if (parts.length >= 4) {
    unit = parts.slice(1, -2).join(", ");
  }
  setRawFieldValue("address_line2", unit);
  const match = stateZip.match(/\b([A-Z]{2})\b\s*(\d{5}(?:-\d{4})?)?/i);
  if (city) {
    setRawFieldValue("address_city", city);
  }
  if (match?.[1]) {
    setRawFieldValue("address_state", match[1].toUpperCase());
  }
  if (match?.[2]) {
    setRawFieldValue("address_postal_code", match[2]);
  }
}

function applyLocationString(value) {
  const text = String(value || "").trim();
  const [city, state] = text.split(",").map((part) => part.trim());
  if (city) {
    setRawFieldValue("address_city", city);
  }
  if (state) {
    setRawFieldValue("address_state", state.toUpperCase());
  }
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
  button.textContent = isBusy ? "Generating package..." : "Generate package";
  resultsAside.classList.toggle("job-active", isBusy);
  if (isBusy) {
    resultsAside.classList.remove("has-results");
  }
  statusEl.textContent = message;
}

function clearError() {
  statusEl.classList.remove("error");
  renderError("");
}

function clearStepActionStatus() {
  clearError();
  statusEl.textContent = "";
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
