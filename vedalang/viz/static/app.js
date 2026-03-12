let cy = null;
let lastResponse = null;
let labelLayer = null;
let labelRefreshScheduled = false;
let viewportResetScheduled = false;
let windowResizeTimer = null;

const SIDEBAR_STORAGE_KEY = "vedalang.viz.sidebarCollapsed";
const SIDEBAR_TAB_STORAGE_KEY = "vedalang.viz.sidebarTab";
const DETAILS_PANE_STORAGE_KEY = "vedalang.viz.detailsPaneCollapsed";
const DETAILS_PANE_WIDTH_STORAGE_KEY = "vedalang.viz.detailsPaneWidth";
const VEDA_TABLES_STORAGE_KEY = "vedalang.viz.vedaTablesEnabled";
const OBJECT_EXPLORER_SHOW_ALL_STORAGE_KEY =
  "vedalang.viz.objectExplorerShowAllAttributes";
const SIDEBAR_TABS = new Set(["files", "view", "filters"]);
const PROCESS_NODE_WIDTH = 168;
const PROCESS_NODE_HEIGHT = 82;
const PROCESS_LABEL_WIDTH = 148;
const MIN_LABEL_SCALE = 0.35;
const MAX_LABEL_SCALE = 6;
const DEFAULT_DETAILS_PANE_WIDTH = 440;
const MIN_DETAILS_PANE_WIDTH = 400;
const MAX_DETAILS_PANE_WIDTH = 620;
const INSPECTOR_RENDERED_SECTION_KEYS = new Set(["dsl", "semantic", "transitions", "lowered"]);
const OBJECT_EXPLAINERS = {
  facility:
    "Binds a technology role to a concrete place and can carry stock, build limits, and policies.",
  fleet:
    "Binds a technology role to distributed stock and can carry stock, build limits, and policies.",
  zone_opportunity:
    "Represents a zone-bound candidate build option with capped new-build potential.",
  technology_role:
    "Groups interchangeable technologies delivering the same primary service.",
  technology: "Describes inputs, outputs, performance, costs, lifetime, and emissions.",
  commodity:
    "Defines a flow type used as an input, output, service, resource, emission ledger, or financial commodity.",
  transition:
    "Describes a change path from one technology to another, including retrofit cost or lead time when present.",
};

const MODE_OPTIONS = [
  { value: "compiled", label: "compiled" },
  { value: "source", label: "source" },
];

const GRANULARITY_OPTIONS = [
  { value: "role", label: "role" },
  { value: "instance", label: "instance" },
];

const LENS_OPTIONS = [
  { value: "system", label: "system" },
  { value: "trade", label: "trade" },
];

const COMMODITY_VIEW_OPTIONS = [
  { value: "collapse_scope", label: "collapse scope" },
  { value: "scoped", label: "scoped" },
];

const STAGE_ORDER = [
  "supply",
  "conversion",
  "distribution",
  "storage",
  "end_use",
  "sink",
];
const STAGE_RANK = new Map(STAGE_ORDER.map((stage, index) => [stage, index]));
const PROCESS_NODE_TYPES = new Set(["role", "instance"]);
const LEDGER_GAS_COLORS = {
  co2: "#ef4444",
  ch4: "#f97316",
  n2o: "#38bdf8",
  other: "#c084fc",
};

const state = {
  file: "",
  mode: "compiled",
  granularity: "role",
  lens: "system",
  commodityView: "collapse_scope",
  caseName: "",
  runId: "",
  regions: [],
  sectors: [],
  scopes: [],
  availableCases: [],
  availableRuns: [],
  availableRegions: [],
  availableSectors: [],
  availableScopes: [],
  workspaceRoot: "",
  currentDir: "",
  parentDir: null,
  currentEntries: [],
  sidebarCollapsed: false,
  activeSidebarTab: "files",
  detailsPaneCollapsed: false,
  detailsPaneWidth: DEFAULT_DETAILS_PANE_WIDTH,
  vedaTablesEnabled: false,
  vedaTrayCollapsed: false,
  vedaTrayTitle: "VEDA Tables",
  objectExplorerShowAllAttributes: false,
  selectedNodeId: "",
  selectedSelectionType: "",
  selectedInspector: null,
};

function setStatus(text) {
  const el = document.getElementById("status");
  const value = String(text || "");
  el.textContent = value;
  el.hidden = value.length === 0;
}

function normalizeToKnown(values, available) {
  const known = new Set(available);
  return [...new Set(values)].filter((value) => known.has(value));
}

function compactPath(path) {
  const parts = path.split("/").filter((part) => part.length > 0);
  if (parts.length <= 3) {
    return path;
  }
  return `.../${parts.slice(-3).join("/")}`;
}

function relativeToWorkspace(path) {
  if (!path) {
    return "";
  }
  if (!state.workspaceRoot || !path.startsWith(state.workspaceRoot)) {
    return path;
  }
  const rel = path.slice(state.workspaceRoot.length).replace(/^\/+/, "");
  return rel || ".";
}

function savePreference(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    void error;
  }
}

function setSidebarCollapsed(collapsed) {
  state.sidebarCollapsed = collapsed;
  const appRoot = document.getElementById("appRoot");
  const toggleButton = document.getElementById("toggleSidebarBtn");

  appRoot.classList.toggle("sidebar-collapsed", collapsed);
  toggleButton.textContent = collapsed ? "▶" : "◀";
  toggleButton.title = collapsed ? "Expand left sidebar" : "Collapse left sidebar";
  savePreference(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
  scheduleViewportReset();
}

function loadSidebarPreference() {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
  } catch (error) {
    void error;
    return false;
  }
}

function setSidebarTab(tab) {
  const nextTab = SIDEBAR_TABS.has(tab) ? tab : "files";
  state.activeSidebarTab = nextTab;
  document.querySelectorAll(".sidebar-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.panel === nextTab);
  });
  document.querySelectorAll(".sidebar-panel").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== nextTab;
  });
  savePreference(SIDEBAR_TAB_STORAGE_KEY, nextTab);
}

function loadSidebarTabPreference() {
  try {
    const stored = localStorage.getItem(SIDEBAR_TAB_STORAGE_KEY);
    return SIDEBAR_TABS.has(stored) ? stored : "files";
  } catch (error) {
    void error;
    return "files";
  }
}

function clampDetailsPaneWidth(width) {
  if (!Number.isFinite(width)) {
    return DEFAULT_DETAILS_PANE_WIDTH;
  }
  return Math.max(
    MIN_DETAILS_PANE_WIDTH,
    Math.min(MAX_DETAILS_PANE_WIDTH, Math.round(width)),
  );
}

function setDetailsPaneWidth(width, { persist = true } = {}) {
  const nextWidth = clampDetailsPaneWidth(width);
  state.detailsPaneWidth = nextWidth;
  document
    .getElementById("appRoot")
    .style.setProperty("--details-pane-width", `${nextWidth}px`);
  if (persist) {
    savePreference(DETAILS_PANE_WIDTH_STORAGE_KEY, String(nextWidth));
  }
}

function loadDetailsPaneWidthPreference() {
  try {
    const stored = localStorage.getItem(DETAILS_PANE_WIDTH_STORAGE_KEY);
    if (stored === null || stored === "") {
      return DEFAULT_DETAILS_PANE_WIDTH;
    }
    const raw = Number(stored);
    return clampDetailsPaneWidth(raw);
  } catch (error) {
    void error;
    return DEFAULT_DETAILS_PANE_WIDTH;
  }
}

function updateInspectorToggleButtons(collapsed) {
  const headerButton = document.getElementById("toggleInspectorBtn");
  const paneButton = document.getElementById("toggleDetailsPaneBtn");
  headerButton.textContent = collapsed ? "Show Inspector" : "Hide Inspector";
  headerButton.title = collapsed ? "Show inspector sidebar" : "Hide inspector sidebar";
  paneButton.textContent = collapsed ? "Show" : "Hide";
  paneButton.title = collapsed ? "Show inspector sidebar" : "Hide inspector sidebar";
}

function setDetailsPaneCollapsed(collapsed) {
  state.detailsPaneCollapsed = collapsed;
  document.getElementById("appRoot").classList.toggle("details-collapsed", collapsed);
  updateInspectorToggleButtons(collapsed);
  savePreference(DETAILS_PANE_STORAGE_KEY, collapsed ? "1" : "0");
  scheduleViewportReset();
}

function loadDetailsPaneCollapsedPreference() {
  try {
    return localStorage.getItem(DETAILS_PANE_STORAGE_KEY) === "1";
  } catch (error) {
    void error;
    return false;
  }
}

function setVedaTablesEnabled(enabled) {
  state.vedaTablesEnabled = enabled;
  savePreference(VEDA_TABLES_STORAGE_KEY, enabled ? "1" : "0");
}

function loadVedaTablesPreference() {
  try {
    return localStorage.getItem(VEDA_TABLES_STORAGE_KEY) === "1";
  } catch (error) {
    void error;
    return false;
  }
}

function setObjectExplorerShowAllAttributes(showAll) {
  state.objectExplorerShowAllAttributes = Boolean(showAll);
  savePreference(OBJECT_EXPLORER_SHOW_ALL_STORAGE_KEY, showAll ? "1" : "0");
  if (state.selectedInspector) {
    renderInspector(state.selectedInspector);
  }
}

function loadObjectExplorerShowAllPreference() {
  try {
    return localStorage.getItem(OBJECT_EXPLORER_SHOW_ALL_STORAGE_KEY) === "1";
  } catch (error) {
    void error;
    return false;
  }
}

function getObjectExplorerSection(inspector) {
  if (!inspector || !Array.isArray(inspector.sections)) {
    return null;
  }
  const section = inspector.sections.find((item) => item.key === "dsl") || null;
  if (!section || !Array.isArray(section.items) || section.items.length === 0) {
    return null;
  }
  return section;
}

function updateObjectExplorerToggle(inspector) {
  const control = document.getElementById("objectExplorerToggle");
  const input = document.getElementById("objectExplorerShowAllAttributes");
  if (!control || !input) {
    return;
  }
  const showToggle = Boolean(getObjectExplorerSection(inspector));
  control.hidden = !showToggle;
  input.checked = state.objectExplorerShowAllAttributes;
  input.disabled = !showToggle;
}

function clearDetailsInspector() {
  const container = document.getElementById("detailsInspector");
  container.innerHTML = "";
  return container;
}

function renderDetailsPlaceholder(text) {
  updateObjectExplorerToggle(null);
  const container = clearDetailsInspector();
  const placeholder = document.createElement("div");
  placeholder.className = "details-placeholder";
  placeholder.textContent = text;
  container.appendChild(placeholder);
}

function createJsonPre(value) {
  const pre = document.createElement("pre");
  pre.className = "details-pre";
  pre.textContent = JSON.stringify(value, null, 2);
  return pre;
}

function isPrimitiveValue(value) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

function isScalarArray(value) {
  return Array.isArray(value) && value.every((item) => isPrimitiveValue(item));
}

function isFlatRecord(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  return Object.values(value).every(
    (item) => isPrimitiveValue(item) || isScalarArray(item),
  );
}

function formatDetailValue(value) {
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => String(item)).join(", ") : "[]";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function formatFieldLabel(key) {
  return String(key || "item").replaceAll("_", " ");
}

function visibleObjectExplorerAttributes(item, showAllAttributes) {
  const attributes = { ...(item && item.attributes ? item.attributes : {}) };
  if (showAllAttributes) {
    return attributes;
  }
  if (item && item.id && attributes.id === item.id) {
    delete attributes.id;
  }
  const hidden = item && item.presentation && Array.isArray(item.presentation.compact_hidden_attributes)
    ? item.presentation.compact_hidden_attributes
    : [];
  hidden.forEach((key) => {
    delete attributes[key];
  });
  return attributes;
}

function renderStructuredAttributes(attributes) {
  if (!attributes || typeof attributes !== "object" || Array.isArray(attributes)) {
    return createJsonPre(attributes);
  }

  const fields = document.createElement("dl");
  fields.className = "details-fields";

  Object.entries(attributes).forEach(([key, value]) => {
    const term = document.createElement("dt");
    term.className = "details-field-key";
    term.textContent = key;
    fields.appendChild(term);

    const description = document.createElement("dd");
    description.className = "details-field";

    if (isFlatRecord(value)) {
      description.appendChild(renderStructuredAttributes(value));
    } else if (isPrimitiveValue(value) || isScalarArray(value)) {
      const text = document.createElement("div");
      text.className = "details-field-value";
      text.textContent = formatDetailValue(value);
      description.appendChild(text);
    } else {
      description.appendChild(createJsonPre(value));
    }

    fields.appendChild(description);
  });

  return fields;
}

function displayKindLabel(kind) {
  return String(kind || "item").replaceAll("_", " ");
}

function badgeKindToken(kind) {
  return String(kind || "item")
    .trim()
    .replaceAll(" ", "_")
    .toLowerCase();
}

function objectExplorerTitle(item) {
  if (item && item.id) {
    return String(item.id);
  }
  return item.label || displayKindLabel(item.kind || "item");
}

function renderDescriptionBlock(descriptionText) {
  const block = document.createElement("div");
  block.className = "details-description";

  const label = document.createElement("div");
  label.className = "details-description-label";
  label.textContent = "Description";
  block.appendChild(label);

  const text = document.createElement("div");
  text.className = "details-description-value";
  text.textContent = descriptionText;
  block.appendChild(text);

  return block;
}

function renderSourceLocation(container, sourceLocation) {
  if (
    !sourceLocation ||
    !Array.isArray(sourceLocation.lines) ||
    sourceLocation.lines.length === 0
  ) {
    return;
  }
  const block = document.createElement("details");
  block.className = "details-item-source";

  const summary = document.createElement("summary");
  const fileLabel = fileNameOnly(sourceLocation.file || "");
  const startLine = sourceLocation.start_line || sourceLocation.line || 0;
  const endLine = sourceLocation.end_line || startLine;
  const lineLabel = startLine === endLine ? `${startLine}` : `${startLine}-${endLine}`;
  summary.textContent = `Source · ${fileLabel}:${lineLabel}`;
  block.appendChild(summary);

  const code = document.createElement("div");
  code.className = "details-source-code";
  sourceLocation.lines.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "details-source-line";

    const gutter = document.createElement("div");
    gutter.className = "details-source-line-number";
    gutter.textContent = String(entry.line ?? "");
    row.appendChild(gutter);

    const text = document.createElement("div");
    text.className = "details-source-line-text";
    text.textContent = entry.text ?? "";
    row.appendChild(text);

    code.appendChild(row);
  });
  block.appendChild(code);
  container.appendChild(block);
}

function renderNestedArrayItems(items, depth) {
  if (!Array.isArray(items) || items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "details-field-value";
    empty.textContent = "No items";
    return empty;
  }

  if (items.every((item) => isPrimitiveValue(item) || isScalarArray(item))) {
    const list = document.createElement("div");
    list.className = "details-inline-list";
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "details-inline-list-item";
      row.textContent = formatDetailValue(item);
      list.appendChild(row);
    });
    return list;
  }

  if (items.every((item) => isFlatRecord(item))) {
    const list = document.createElement("div");
    list.className = "details-object-array-list";
    items.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "details-object-array-item details-object-array-item-flat";

      if (items.length > 1) {
        const indexLabel = document.createElement("div");
        indexLabel.className = "details-object-array-item-label";
        indexLabel.textContent = `Item ${index + 1}`;
        row.appendChild(indexLabel);
      }

      row.appendChild(renderNestedStructuredAttributes(item, depth + 1));
      list.appendChild(row);
    });
    return list;
  }

  if (items.length === 1) {
    const only = items[0];
    if (isPrimitiveValue(only) || isScalarArray(only)) {
      const text = document.createElement("div");
      text.className = "details-field-value";
      text.textContent = formatDetailValue(only);
      return text;
    }
    return renderNestedStructuredAttributes(only, depth + 1);
  }

  const list = document.createElement("div");
  list.className = "details-object-array-list";
  items.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "details-object-array-item";

    const label = document.createElement("div");
    label.className = "details-object-array-item-label";
    label.textContent = `Item ${index + 1}`;
    row.appendChild(label);

    if (isPrimitiveValue(item) || isScalarArray(item)) {
      const text = document.createElement("div");
      text.className = "details-field-value";
      text.textContent = formatDetailValue(item);
      row.appendChild(text);
    } else {
      row.appendChild(renderNestedStructuredAttributes(item, depth + 1));
    }
    list.appendChild(row);
  });
  return list;
}

function createObjectKindBadge(kind) {
  const label = displayKindLabel(kind || "");
  const explainer = OBJECT_EXPLAINERS[kind];

  if (!explainer) {
    const badge = document.createElement("div");
    badge.className = "details-item-kind";
    badge.textContent = label;
    badge.dataset.kind = badgeKindToken(kind);
    return { badge, panel: null };
  }

  const badge = document.createElement("button");
  badge.type = "button";
  badge.className = "details-item-kind details-item-kind-button";
  badge.textContent = label;
  badge.dataset.kind = badgeKindToken(kind);
  badge.title = explainer;
  badge.setAttribute("aria-expanded", "false");
  badge.setAttribute("aria-label", `About ${label}`);

  const panel = document.createElement("div");
  panel.className = "details-item-kind-popover";
  panel.hidden = true;
  panel.textContent = explainer;

  badge.addEventListener("click", () => {
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    badge.setAttribute("aria-expanded", isOpen ? "false" : "true");
  });

  return { badge, panel };
}

function renderNestedStructuredAttributes(attributes, depth = 0) {
  if (!attributes || typeof attributes !== "object" || Array.isArray(attributes)) {
    const text = document.createElement("div");
    text.className = "details-field-value";
    text.textContent = formatDetailValue(attributes);
    return text;
  }

  const fields = document.createElement("div");
  fields.className = "details-object-fields";
  fields.dataset.depth = String(depth);

  Object.entries(attributes).forEach(([key, value]) => {
    if (
      value === null ||
      value === "" ||
      (Array.isArray(value) && value.length === 0)
    ) {
      return;
    }

    const row = document.createElement("div");
    const label = document.createElement("div");
    label.className = "details-field-key";
    label.textContent = Array.isArray(value)
      ? `${formatFieldLabel(key)} (${value.length})`
      : formatFieldLabel(key);

    const content = document.createElement("div");
    content.className = "details-object-field-value";
    const isStructuredValue = !isPrimitiveValue(value) && !isScalarArray(value);
    if (isStructuredValue) {
      content.classList.add("details-object-field-value-structured");
    }
    if (isStructuredValue && depth >= 1) {
      row.className = "details-field-row details-field-row-stacked";
      row.appendChild(label);
    } else {
      row.className = "details-field-row";
      row.appendChild(label);
    }

    if (isPrimitiveValue(value) || isScalarArray(value)) {
      const text = document.createElement("div");
      text.className = "details-field-value";
      text.textContent = formatDetailValue(value);
      content.appendChild(text);
    } else if (Array.isArray(value)) {
      content.appendChild(renderNestedArrayItems(value, depth + 1));
    } else {
      content.appendChild(renderNestedStructuredAttributes(value, depth + 1));
    }
    row.appendChild(content);

    fields.appendChild(row);
  });

  if (!fields.childNodes.length) {
    const empty = document.createElement("div");
    empty.className = "details-field-value";
    empty.textContent = "No fields";
    fields.appendChild(empty);
  }

  return fields;
}

function renderObjectExplorerItem(item, depth = 0) {
  const card = document.createElement("div");
  card.className = "details-item details-item-object";
  card.dataset.depth = String(depth);

  const header = document.createElement("div");
  header.className = "details-item-header details-item-header-object";

  const { badge, panel } = createObjectKindBadge(item.kind);
  header.appendChild(badge);

  const title = document.createElement("div");
  title.className = "details-item-title";
  title.textContent = objectExplorerTitle(item);
  header.appendChild(title);

  card.appendChild(header);
  if (panel) {
    card.appendChild(panel);
  }

  const attributes = visibleObjectExplorerAttributes(
    item,
    state.objectExplorerShowAllAttributes,
  );
  const descriptionText =
    typeof attributes.description === "string" ? attributes.description.trim() : "";
  delete attributes.description;

  if (descriptionText) {
    card.appendChild(renderDescriptionBlock(descriptionText));
  }

  card.appendChild(renderNestedStructuredAttributes(attributes, depth));
  renderSourceLocation(card, item.source_location);

  const children = Array.isArray(item.children) ? item.children : [];
  if (children.length > 0) {
    const childContainer = document.createElement("div");
    childContainer.className = "details-item-children";
    children.forEach((child) => {
      childContainer.appendChild(renderObjectExplorerItem(child, depth + 1));
    });
    card.appendChild(childContainer);
  }
  return card;
}

function formatSectionStatus(status) {
  const text = String(status || "ok");
  if (text === "ok") {
    return "";
  }
  return text.replace(/_/g, " ");
}

function formatQueryStatus(status, modeUsed) {
  const statusText = String(status || "");
  if (!statusText || statusText === "ok") {
    return "";
  }
  if (modeUsed) {
    return `${statusText} (${modeUsed})`;
  }
  return statusText;
}

function renderRawDetails(details) {
  updateObjectExplorerToggle(null);
  const container = clearDetailsInspector();
  container.appendChild(createJsonPre(details));
}

function renderDiagnostics(diagnostics) {
  const items = Array.isArray(diagnostics) ? diagnostics : [];
  const section = document.getElementById("diagnosticsSection");
  const summary = document.getElementById("diagnosticsSummary");
  const container = document.getElementById("diagnostics");
  summary.textContent = items.length ? `Diagnostics (${items.length})` : "Diagnostics";
  container.textContent = JSON.stringify(items, null, 2);
  section.open = items.length > 0;
}

function getVedaSection(inspector) {
  if (!inspector || !Array.isArray(inspector.sections)) {
    return null;
  }
  return inspector.sections.find((section) => section.key === "veda") || null;
}

function isVedaTrayEligibleInspector(inspector) {
  return Boolean(
    inspector &&
      state.lens === "system" &&
      (inspector.kind === "process" || inspector.kind === "commodity"),
  );
}

function clearVedaTrayContent() {
  const header = document.getElementById("vedaTrayHeader");
  const content = document.getElementById("vedaTrayContent");
  header.innerHTML = "";
  content.innerHTML = "";
  return { header, content };
}

function setVedaTrayVisible(visible) {
  const tray = document.getElementById("vedaTray");
  const wasVisible = !tray.hidden;
  tray.hidden = !visible;
  if (visible) {
    document.getElementById("vedaTrayCollapsedBar").hidden = true;
  } else {
    updateVedaTrayCollapsedBar();
  }
  if (wasVisible !== visible) {
    scheduleViewportReset();
  }
}

function setVedaTrayCollapsed(collapsed) {
  state.vedaTrayCollapsed = collapsed;
  updateVedaTrayCollapsedBar();
}

function currentVedaTrayInspector() {
  if (!state.vedaTablesEnabled || state.lens !== "system") {
    return null;
  }
  if (
    !state.selectedSelectionType ||
    state.selectedSelectionType !== "node" ||
    !lastResponse
  ) {
    return null;
  }
  const details =
    (((lastResponse || {}).details || {}).nodes || {})[state.selectedNodeId] || null;
  if (
    !details ||
    !details.inspector ||
    !isVedaTrayEligibleInspector(details.inspector)
  ) {
    return null;
  }
  return details.inspector;
}

function updateVedaTrayCollapsedBar() {
  const bar = document.getElementById("vedaTrayCollapsedBar");
  const label = document.getElementById("vedaTrayCollapsedLabel");
  const inspector = currentVedaTrayInspector();
  const shouldShow = Boolean(state.vedaTrayCollapsed && inspector);
  label.textContent = state.vedaTrayTitle || "VEDA Tables";
  bar.hidden = !shouldShow;
}

function fileNameOnly(path) {
  if (!path) {
    return "";
  }
  const parts = String(path).split("/");
  return parts[parts.length - 1] || String(path);
}

function createVedaTrayHeader({ title, statusText, partial }) {
  const header = document.getElementById("vedaTrayHeader");
  header.innerHTML = "";
  state.vedaTrayTitle = title;

  const titleRow = document.createElement("div");
  titleRow.className = "veda-tray-title-row";

  const titleEl = document.createElement("div");
  titleEl.className = "veda-tray-title";
  titleEl.textContent = title;
  titleRow.appendChild(titleEl);

  if (partial) {
    const badge = document.createElement("span");
    badge.className = "veda-tray-badge";
    badge.textContent = "partial";
    titleRow.appendChild(badge);
  }

  header.appendChild(titleRow);

  if (statusText) {
    const status = document.createElement("div");
    status.className = "veda-tray-status";
    status.textContent = statusText;
    header.appendChild(status);
  }
}

function renderVedaTrayPlaceholder(title, text, { partial = false } = {}) {
  if (state.vedaTrayCollapsed) {
    hideVedaTray();
    return;
  }
  const { content } = clearVedaTrayContent();
  createVedaTrayHeader({
    title,
    statusText: text,
    partial,
  });

  const placeholder = document.createElement("div");
  placeholder.className = "veda-tray-placeholder";
  placeholder.textContent = text;
  content.appendChild(placeholder);
  setVedaTrayVisible(true);
}

function hideVedaTray() {
  clearVedaTrayContent();
  setVedaTrayVisible(false);
}

function vedaRowsForItem(item) {
  const attributes = item && item.attributes ? item.attributes : {};
  if (item.kind === "veda_process") {
    return []
      .concat(attributes.fi_process_rows || [])
      .concat(attributes.fi_t_rows || [])
      .concat(attributes.tfm_ins_rows || []);
  }
  const summary = attributes.times_summary || {};
  if (item.kind === "veda_commodity") {
    return []
      .concat(summary.fi_comm_rows || [])
      .concat(summary.fi_t_rows || [])
      .concat(summary.tfm_ins_rows || []);
  }
  return [];
}

function normalizeVedaTables(inspector) {
  const vedaSection = getVedaSection(inspector);
  const tables = [];
  const tableMap = new Map();

  if (!vedaSection || !Array.isArray(vedaSection.items)) {
    return { partial: false, tables };
  }

  vedaSection.items.forEach((item) => {
    vedaRowsForItem(item).forEach((ref) => {
      if (!ref || typeof ref !== "object" || !ref.row || typeof ref.row !== "object") {
        return;
      }
      const tableKey =
        ref.table_key ||
        `${ref.file || ""}::${ref.sheet || ""}::${ref.table_index ?? 0}::${ref.tag || ""}`;
      if (!tableMap.has(tableKey)) {
        const table = {
          tableKey,
          tableIndex: ref.table_index ?? 0,
          file: ref.file || "",
          sheet: ref.sheet || "",
          tag: ref.tag || "",
          rows: [],
          columns: [],
          columnSet: new Set(),
        };
        tableMap.set(tableKey, table);
        tables.push(table);
      }
      const table = tableMap.get(tableKey);
      table.rows.push(ref.row);
      Object.keys(ref.row).forEach((column) => {
        if (!table.columnSet.has(column)) {
          table.columnSet.add(column);
          table.columns.push(column);
        }
      });
    });
  });

  return {
    partial: vedaSection.status === "partial",
    tables: tables.map((table) => ({
      tableKey: table.tableKey,
      tableIndex: table.tableIndex,
      file: table.file,
      sheet: table.sheet,
      tag: table.tag,
      rows: table.rows,
      columns: table.columns,
    })),
  };
}

function renderVedaTableCard(tableGroup) {
  const card = document.createElement("section");
  card.className = "veda-table-card";

  const header = document.createElement("div");
  header.className = "veda-table-card-header";

  const tag = document.createElement("div");
  tag.className = "veda-table-card-tag";
  tag.textContent = tableGroup.tag || "VEDA table";
  header.appendChild(tag);

  const meta = document.createElement("div");
  meta.className = "veda-table-card-meta";
  [
    `Workbook: ${fileNameOnly(tableGroup.file) || "(unknown)"}`,
    `Sheet: ${tableGroup.sheet || "(unknown)"}`,
    `Rows: ${tableGroup.rows.length}`,
  ].forEach((text) => {
    const part = document.createElement("span");
    part.textContent = text;
    meta.appendChild(part);
  });
  header.appendChild(meta);
  card.appendChild(header);

  const wrap = document.createElement("div");
  wrap.className = "veda-table-wrap";

  const table = document.createElement("table");
  table.className = "veda-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  tableGroup.columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  tableGroup.rows.forEach((row) => {
    const tr = document.createElement("tr");
    tableGroup.columns.forEach((column) => {
      const td = document.createElement("td");
      const value = row[column];
      td.textContent = value === undefined || value === null ? "" : String(value);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  wrap.appendChild(table);
  card.appendChild(wrap);
  return card;
}

function renderVedaTrayForInspector(inspector) {
  if (!state.vedaTablesEnabled || state.vedaTrayCollapsed) {
    hideVedaTray();
    return;
  }

  if (state.lens !== "system") {
    hideVedaTray();
    return;
  }

  if (!inspector || !isVedaTrayEligibleInspector(inspector)) {
    hideVedaTray();
    return;
  }

  const { content } = clearVedaTrayContent();
  const normalized = normalizeVedaTables(inspector);
  const title = inspector.title ? `VEDA Tables: ${inspector.title}` : "VEDA Tables";
  const statusText = normalized.tables.length
    ? `${normalized.tables.length} rendered table${normalized.tables.length === 1 ? "" : "s"}`
    : "No rendered VEDA/TIMES tables for this selection.";

  createVedaTrayHeader({
    title,
    statusText,
    partial: normalized.partial,
  });

  if (!normalized.tables.length) {
    const placeholder = document.createElement("div");
    placeholder.className = "veda-tray-placeholder";
    placeholder.textContent = "No rendered VEDA/TIMES tables for this selection.";
    content.appendChild(placeholder);
  } else {
    normalized.tables.forEach((tableGroup) => {
      content.appendChild(renderVedaTableCard(tableGroup));
    });
  }
  setVedaTrayVisible(true);
}

function renderInspector(inspector) {
  updateObjectExplorerToggle(inspector);
  const container = clearDetailsInspector();
  if (!inspector || !Array.isArray(inspector.sections)) {
    renderDetailsPlaceholder("No structured inspector data for this selection.");
    return;
  }

  const title = document.createElement("div");
  title.className = "details-title";
  title.textContent = inspector.title || "Details";
  container.appendChild(title);

  const vedaSection = getVedaSection(inspector);
  if (vedaSection && !state.vedaTablesEnabled) {
    const hint = document.createElement("div");
    hint.className = "details-hint";
    hint.textContent = "Enable VEDA tables to inspect emitted VEDA/TIMES rows.";
    container.appendChild(hint);
  }

  const renderedSections = inspector.sections.filter((section) =>
    INSPECTOR_RENDERED_SECTION_KEYS.has(section.key),
  );

  if (renderedSections.length === 0) {
    const placeholder = document.createElement("div");
    placeholder.className = "details-placeholder";
    placeholder.textContent =
      "No DSL, resolved semantic, or lowered IR details for this selection.";
    container.appendChild(placeholder);
    return;
  }

  renderedSections.forEach((section) => {
    const details = document.createElement("details");
    details.className = "details-section";
    details.open = Boolean(section.default_open);

    const summary = document.createElement("summary");
    summary.textContent = section.label || section.key || "Section";
    details.appendChild(summary);

    const body = document.createElement("div");
    body.className = "details-section-body";

    const sectionStatus = formatSectionStatus(section.status);
    if (sectionStatus) {
      const status = document.createElement("div");
      status.className = "details-section-status";
      status.textContent = sectionStatus;
      body.appendChild(status);
    }

    if (!Array.isArray(section.items) || section.items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "details-placeholder";
      empty.textContent = "No items";
      body.appendChild(empty);
    } else {
      section.items.forEach((item) => {
        let card = null;
        if (section.key === "dsl") {
          card = renderObjectExplorerItem(item);
        } else {
          card = document.createElement("div");
          card.className = "details-item";

          const header = document.createElement("div");
          header.className = "details-item-header";

          const left = document.createElement("div");
          left.className = "details-item-label";
          const idText = item.id ? `: ${item.id}` : "";
          left.textContent = `${item.label || item.kind || "item"}${idText}`;
          header.appendChild(left);

          const right = document.createElement("div");
          right.className = "details-item-kind";
          right.dataset.kind = badgeKindToken(item.kind);
          right.textContent = displayKindLabel(item.kind || "");
          header.appendChild(right);

          card.appendChild(header);
          card.appendChild(renderStructuredAttributes(item.attributes || {}));
          renderSourceLocation(card, item.source_location);
        }
        body.appendChild(card);
      });
    }

    details.appendChild(body);
    container.appendChild(details);
  });
}

function getRequest() {
  return {
    version: "1",
    file: state.file,
    mode: state.mode,
    granularity: state.granularity,
    lens: state.lens,
    run: state.runId || null,
    commodity_view: state.commodityView,
    filters: {
      regions: state.regions,
      case: state.caseName || null,
      sectors: state.sectors,
      scopes: state.scopes,
    },
    compiled: {
      truth: "auto",
      cache: true,
      allow_partial: true,
    },
  };
}

function styleForNode(nodeType) {
  if (nodeType === "commodity" || nodeType === "trade_commodity") {
    return { shape: "ellipse", color: "#0891b2" };
  }
  if (nodeType === "role") {
    return { shape: "round-rectangle", color: "#6366f1" };
  }
  return { shape: "round-rectangle", color: "#16a34a" };
}

function normalizeLedgerEmissions(raw) {
  if (!raw || typeof raw !== "object" || !raw.present) {
    return { present: false, state: "none", coverage: "none", gases: [] };
  }
  const gases = Array.isArray(raw.gases) ? raw.gases : [];
  return {
    present: true,
    state: String(raw.state || "none"),
    coverage: String(raw.coverage || "none"),
    gases,
  };
}

function ledgerBorderStyle(ledgerEmissions) {
  const state = ledgerEmissions && ledgerEmissions.present ? ledgerEmissions.state : "none";
  if (state === "emit") {
    return { color: "#ef4444", width: 3 };
  }
  if (state === "remove") {
    return { color: "#22c55e", width: 3 };
  }
  if (state === "mixed") {
    return { color: "#f59e0b", width: 3 };
  }
  return { color: "#0f172a", width: 1 };
}

function ledgerGasColor(colorKey) {
  return LEDGER_GAS_COLORS[colorKey] || LEDGER_GAS_COLORS.other;
}

function isProcessNodeType(nodeType) {
  return PROCESS_NODE_TYPES.has(nodeType);
}

function formatStageLabel(stage) {
  if (stage === "end_use") {
    return "End Use";
  }
  return String(stage || "")
    .split("_")
    .filter((part) => part.length > 0)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function stageRank(stage) {
  if (typeof stage !== "string" || stage.length === 0) {
    return null;
  }
  const rank = STAGE_RANK.get(stage);
  return rank === undefined ? STAGE_ORDER.length : rank;
}

function isCommodityNodeType(nodeType) {
  return nodeType === "commodity" || nodeType === "trade_commodity";
}

function mod2(value) {
  return ((value % 2) + 2) % 2;
}

function snapToParity(value, parity) {
  if (!Number.isFinite(value)) {
    return parity === 0 ? 0 : 1;
  }
  let lower = Math.floor(value);
  while (mod2(lower) !== parity) {
    lower -= 1;
  }
  let upper = Math.ceil(value);
  while (mod2(upper) !== parity) {
    upper += 1;
  }
  return Math.abs(value - lower) <= Math.abs(upper - value) ? lower : upper;
}

function median(values) {
  if (!values.length) {
    return null;
  }
  const ordered = [...values].sort((a, b) => a - b);
  const mid = Math.floor(ordered.length / 2);
  if (ordered.length % 2 === 0) {
    return (ordered[mid - 1] + ordered[mid]) / 2;
  }
  return ordered[mid];
}

function chooseCommodityColumn(producerColumns, consumerColumns) {
  if (producerColumns.length && consumerColumns.length) {
    const low = Math.max(...producerColumns);
    const high = Math.min(...consumerColumns);

    if (low <= high) {
      let bestColumn = null;
      let bestScore = Number.POSITIVE_INFINITY;
      const firstOdd = mod2(low) === 1 ? low : low + 1;
      for (let col = firstOdd; col <= high; col += 2) {
        let score = 0;
        for (const anchor of producerColumns) {
          const diff = col - anchor;
          score += diff * diff;
        }
        for (const anchor of consumerColumns) {
          const diff = col - anchor;
          score += diff * diff;
        }
        if (score < bestScore) {
          bestScore = score;
          bestColumn = col;
        }
      }
      if (Number.isFinite(bestColumn)) {
        return bestColumn;
      }
      return snapToParity((low + high) / 2, 1);
    }

    const medianAnchor = median([...producerColumns, ...consumerColumns]);
    return snapToParity(medianAnchor, 1);
  }

  if (producerColumns.length) {
    return Math.max(...producerColumns);
  }
  if (consumerColumns.length) {
    return Math.min(...consumerColumns);
  }

  return null;
}

function buildAlternatingColumnPositions(nodes, graphEdges) {
  const processNodesWithStage = nodes.filter(
    (node) => isProcessNodeType(node.data.type) && Number.isFinite(node.data.stageRank),
  );
  if (processNodesWithStage.length === 0) {
    return null;
  }

  const nodeById = new Map(nodes.map((node) => [node.data.id, node]));
  const nodeColumns = new Map();
  const producerAnchors = new Map();
  const consumerAnchors = new Map();
  const neighbors = new Map();
  const usedStageRanks = [
    ...new Set(processNodesWithStage.map((node) => Number(node.data.stageRank))),
  ].sort((a, b) => a - b);
  const denseProcessColumns = new Map(
    usedStageRanks.map((rank, index) => [rank, index * 2]),
  );

  for (const node of processNodesWithStage) {
    const denseColumn = denseProcessColumns.get(Number(node.data.stageRank));
    if (Number.isFinite(denseColumn)) {
      nodeColumns.set(node.data.id, denseColumn);
    }
  }

  for (const edge of graphEdges) {
    const sourceNode = nodeById.get(edge.source);
    const targetNode = nodeById.get(edge.target);
    if (!sourceNode || !targetNode) {
      continue;
    }

    if (!neighbors.has(edge.source)) {
      neighbors.set(edge.source, new Set());
    }
    if (!neighbors.has(edge.target)) {
      neighbors.set(edge.target, new Set());
    }
    neighbors.get(edge.source).add(edge.target);
    neighbors.get(edge.target).add(edge.source);

    const sourceProcessCol = nodeColumns.get(edge.source);
    const targetProcessCol = nodeColumns.get(edge.target);

    if (
      Number.isFinite(sourceProcessCol) &&
      isCommodityNodeType(targetNode.data.type)
    ) {
      const list = producerAnchors.get(edge.target) || [];
      list.push(sourceProcessCol + 1);
      producerAnchors.set(edge.target, list);
    }

    if (
      isCommodityNodeType(sourceNode.data.type) &&
      Number.isFinite(targetProcessCol)
    ) {
      const list = consumerAnchors.get(edge.source) || [];
      list.push(targetProcessCol - 1);
      consumerAnchors.set(edge.source, list);
    }
  }

  for (const node of nodes) {
    if (!isCommodityNodeType(node.data.type)) {
      continue;
    }
    const selectedColumn = chooseCommodityColumn(
      producerAnchors.get(node.data.id) || [],
      consumerAnchors.get(node.data.id) || [],
    );
    if (Number.isFinite(selectedColumn)) {
      nodeColumns.set(node.data.id, selectedColumn);
    }
  }

  for (let iteration = 0; iteration < 3; iteration += 1) {
    let changed = false;
    for (const node of nodes) {
      if (nodeColumns.has(node.data.id)) {
        continue;
      }
      const near = neighbors.get(node.data.id);
      if (!near || near.size === 0) {
        continue;
      }

      const assigned = [];
      for (const otherId of near) {
        const col = nodeColumns.get(otherId);
        if (Number.isFinite(col)) {
          assigned.push(col);
        }
      }
      if (!assigned.length) {
        continue;
      }

      const avg = assigned.reduce((acc, value) => acc + value, 0) / assigned.length;
      const parity = isCommodityNodeType(node.data.type) ? 1 : 0;
      nodeColumns.set(node.data.id, snapToParity(avg, parity));
      changed = true;
    }

    if (!changed) {
      break;
    }
  }

  const assignedColumns = [...nodeColumns.values()].filter((value) =>
    Number.isFinite(value),
  );
  let fallbackColumn = assignedColumns.length ? Math.max(...assignedColumns) + 1 : 0;
  const unresolved = nodes.filter((node) => !nodeColumns.has(node.data.id));
  unresolved.sort((left, right) => {
    const leftLabel = String(left.data.label || left.data.id);
    const rightLabel = String(right.data.label || right.data.id);
    return leftLabel.localeCompare(rightLabel);
  });
  for (const node of unresolved) {
    const parity = isCommodityNodeType(node.data.type) ? 1 : 0;
    fallbackColumn = snapToParity(fallbackColumn, parity);
    nodeColumns.set(node.data.id, fallbackColumn);
    fallbackColumn += 1;
  }

  const columns = new Map();
  for (const node of nodes) {
    const col = nodeColumns.get(node.data.id);
    if (!Number.isFinite(col)) {
      continue;
    }
    const bucket = columns.get(col) || [];
    bucket.push(node);
    columns.set(col, bucket);
  }
  if (columns.size === 0) {
    return null;
  }

  const sortedColumns = [...columns.keys()].sort((a, b) => a - b);
  for (const col of sortedColumns) {
    const bucket = columns.get(col) || [];
    bucket.sort((left, right) => {
      const leftLabel = String(left.data.label || left.data.id);
      const rightLabel = String(right.data.label || right.data.id);
      return leftLabel.localeCompare(rightLabel);
    });
  }

  const yIndexByNode = new Map();
  const refreshYIndex = () => {
    yIndexByNode.clear();
    for (const col of sortedColumns) {
      const bucket = columns.get(col) || [];
      bucket.forEach((node, index) => {
        yIndexByNode.set(node.data.id, index);
      });
    }
  };
  refreshYIndex();

  const barycenter = (nodeId) => {
    const near = neighbors.get(nodeId);
    if (!near || near.size === 0) {
      return null;
    }
    const ys = [];
    for (const otherId of near) {
      if (yIndexByNode.has(otherId)) {
        ys.push(yIndexByNode.get(otherId));
      }
    }
    if (!ys.length) {
      return null;
    }
    return ys.reduce((acc, value) => acc + value, 0) / ys.length;
  };

  for (let sweep = 0; sweep < 2; sweep += 1) {
    const forward = [...sortedColumns];
    const backward = [...sortedColumns].reverse();
    for (const passColumns of [forward, backward]) {
      for (const col of passColumns) {
        const bucket = columns.get(col) || [];
        bucket.sort((left, right) => {
          const leftBary = barycenter(left.data.id);
          const rightBary = barycenter(right.data.id);
          if (Number.isFinite(leftBary) && Number.isFinite(rightBary)) {
            if (leftBary !== rightBary) {
              return leftBary - rightBary;
            }
          } else if (Number.isFinite(leftBary)) {
            return -1;
          } else if (Number.isFinite(rightBary)) {
            return 1;
          }
          const leftLabel = String(left.data.label || left.data.id);
          const rightLabel = String(right.data.label || right.data.id);
          return leftLabel.localeCompare(rightLabel);
        });
      }
      refreshYIndex();
    }
  }

  const columnGap = 220;
  const yGap = 116;
  const positions = {};
  for (const col of sortedColumns) {
    const bucket = columns.get(col) || [];
    const yOffset = ((bucket.length - 1) * yGap) / 2;
    bucket.forEach((node, index) => {
      positions[node.data.id] = {
        x: col * columnGap,
        y: index * yGap - yOffset,
      };
    });
  }

  return positions;
}

function resetGraphViewport() {
  if (!cy || cy.elements().length === 0) {
    return;
  }
  cy.fit(cy.elements(), 48);
  cy.center();
  scheduleProcessLabelRefresh();
}

function scheduleViewportReset() {
  if (viewportResetScheduled) {
    return;
  }
  viewportResetScheduled = true;
  window.requestAnimationFrame(() => {
    viewportResetScheduled = false;
    resetGraphViewport();
  });
}

function ensureLabelLayer() {
  if (labelLayer) {
    return labelLayer;
  }
  const graph = document.getElementById("graph");
  labelLayer = document.createElement("div");
  labelLayer.className = "graph-label-layer";
  graph.appendChild(labelLayer);
  return labelLayer;
}

function splitProcessLabel(label) {
  const lines = String(label || "").split("\n");
  return {
    primary: lines[0] || "",
    secondary: lines[1] || "",
    meta: lines.slice(2).join("\n"),
  };
}

function refreshProcessLabelLayer() {
  labelRefreshScheduled = false;
  const layer = ensureLabelLayer();
  layer.innerHTML = "";

  if (!cy) {
    return;
  }

  const labelScale = Math.max(MIN_LABEL_SCALE, Math.min(MAX_LABEL_SCALE, cy.zoom()));

  cy.nodes().forEach((node) => {
    const nodeType = node.data("type");
    if (!isProcessNodeType(nodeType) || !node.visible()) {
      return;
    }

    const { primary, secondary, meta } = splitProcessLabel(node.data("label"));
    const detail =
      (lastResponse &&
        lastResponse.details &&
        lastResponse.details.nodes &&
        lastResponse.details.nodes[node.id()]) ||
      {};
    const transitionSemantics =
      detail && typeof detail.transition_semantics === "object"
        ? detail.transition_semantics
        : null;
    const position = node.renderedPosition();
    const labelEl = document.createElement("div");
    labelEl.className = `graph-process-label ${nodeType === "role" ? "is-role" : "is-instance"}`;
    labelEl.style.left = `${position.x}px`;
    labelEl.style.top = `${position.y}px`;
    labelEl.style.width = `${PROCESS_LABEL_WIDTH}px`;
    labelEl.style.transform = `translate(-50%, -50%) scale(${labelScale})`;
    const ledgerEmissions = normalizeLedgerEmissions(detail.ledger_emissions);
    labelEl.dataset.ledgerState = ledgerEmissions.state;

    if (ledgerEmissions.present && ledgerEmissions.gases.length > 0) {
      const railEl = document.createElement("div");
      railEl.className = "graph-process-label-gas-rail";
      ledgerEmissions.gases.forEach((gas) => {
        const segmentEl = document.createElement("div");
        segmentEl.className = "graph-process-label-gas-segment";
        segmentEl.dataset.state = String(gas.state || "emit");
        segmentEl.style.backgroundColor = ledgerGasColor(String(gas.color_key || "other"));
        segmentEl.title = `${gas.code || gas.commodity_id || "Emission"} (${gas.state || "emit"})`;
        railEl.appendChild(segmentEl);
      });
      labelEl.appendChild(railEl);
    }

    if (transitionSemantics && transitionSemantics.badge_label) {
      const badgeEl = document.createElement("div");
      badgeEl.className = "graph-process-label-badge";
      badgeEl.dataset.transitionKind = transitionSemantics.kind_basis || "transition";
      badgeEl.dataset.transitionParticipation =
        transitionSemantics.participation || "none";
      badgeEl.textContent = transitionSemantics.badge_label;
      labelEl.appendChild(badgeEl);
    }

    const primaryEl = document.createElement("div");
    primaryEl.className = "graph-process-label-primary";
    primaryEl.textContent = primary;
    labelEl.appendChild(primaryEl);

    if (secondary) {
      const secondaryEl = document.createElement("div");
      secondaryEl.className = "graph-process-label-secondary";
      secondaryEl.textContent = secondary;
      labelEl.appendChild(secondaryEl);
    }

    if (meta) {
      const metaEl = document.createElement("div");
      metaEl.className = "graph-process-label-meta";
      metaEl.textContent = meta;
      labelEl.appendChild(metaEl);
    }

    layer.appendChild(labelEl);
  });
}

function scheduleProcessLabelRefresh() {
  if (labelRefreshScheduled) {
    return;
  }
  labelRefreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshProcessLabelLayer();
  });
}

function clearSelectionState() {
  state.selectedNodeId = "";
  state.selectedSelectionType = "";
  state.selectedInspector = null;
}

function selectNode(id, inspector) {
  state.selectedNodeId = id;
  state.selectedSelectionType = "node";
  state.selectedInspector = inspector || null;
}

function selectEdge(id) {
  state.selectedNodeId = id;
  state.selectedSelectionType = "edge";
  state.selectedInspector = null;
}

function renderVedaTrayForCurrentSelection() {
  if (!state.vedaTablesEnabled || state.vedaTrayCollapsed) {
    hideVedaTray();
    return;
  }

  if (state.lens !== "system") {
    hideVedaTray();
    return;
  }

  if (!state.selectedSelectionType || !state.selectedNodeId || !lastResponse) {
    hideVedaTray();
    return;
  }

  if (state.selectedSelectionType === "edge") {
    hideVedaTray();
    return;
  }

  const details =
    (((lastResponse || {}).details || {}).nodes || {})[state.selectedNodeId] || null;
  if (details && details.inspector && isVedaTrayEligibleInspector(details.inspector)) {
    renderVedaTrayForInspector(details.inspector);
    return;
  }

  hideVedaTray();
}

function renderSelectionFromState() {
  if (!lastResponse) {
    renderDetailsPlaceholder(
      "Select a process or commodity node to inspect its layers.",
    );
    hideVedaTray();
    return;
  }

  if (!state.selectedSelectionType || !state.selectedNodeId) {
    renderDetailsPlaceholder(
      "Select a process or commodity node to inspect its layers.",
    );
    renderVedaTrayForCurrentSelection();
    return;
  }

  if (state.selectedSelectionType === "node") {
    const details = (((lastResponse || {}).details || {}).nodes || {})[
      state.selectedNodeId
    ];
    if (!details) {
      clearSelectionState();
      renderDetailsPlaceholder(
        "Select a process or commodity node to inspect its layers.",
      );
      renderVedaTrayForCurrentSelection();
      return;
    }
    if (details.inspector) {
      state.selectedInspector = details.inspector;
      renderInspector(details.inspector);
    } else {
      state.selectedInspector = null;
      renderRawDetails(details);
    }
    renderVedaTrayForCurrentSelection();
    return;
  }

  const details = (((lastResponse || {}).details || {}).edges || {})[
    state.selectedNodeId
  ];
  if (!details) {
    clearSelectionState();
    renderDetailsPlaceholder(
      "Select a process or commodity node to inspect its layers.",
    );
    renderVedaTrayForCurrentSelection();
    return;
  }
  if (details.inspector) {
    renderInspector(details.inspector);
  } else {
    renderRawDetails(details);
  }
  renderVedaTrayForCurrentSelection();
}

function initCy() {
  ensureLabelLayer();
  cy = cytoscape({
    container: document.getElementById("graph"),
    style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "text-wrap": "wrap",
          "text-max-width": 160,
          "font-size": 10,
          shape: "data(shape)",
          "background-color": "data(color)",
          color: "#e5e7eb",
          "text-valign": "center",
          "text-halign": "center",
          "border-width": "data(borderWidth)",
          "border-color": "data(borderColor)",
          width: 60,
          height: 40,
        },
      },
      {
        selector: 'node[type="role"], node[type="instance"]',
        style: {
          label: "",
          width: PROCESS_NODE_WIDTH,
          height: PROCESS_NODE_HEIGHT,
          padding: 8,
        },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#6b7280",
          "target-arrow-color": "#6b7280",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
        },
      },
      {
        selector: 'edge[type="emission"]',
        style: {
          "line-style": "dashed",
          "line-color": "#ef4444",
          "target-arrow-color": "#ef4444",
        },
      },
      {
        selector: 'edge[type="trade"]',
        style: {
          "line-style": "dotted",
          "line-color": "#22d3ee",
          "target-arrow-color": "#22d3ee",
          "target-arrow-shape": "diamond",
        },
      },
    ],
    layout: { name: "preset" },
    wheelSensitivity: 0.25,
  });

  cy.on("tap", "node", (event) => {
    const id = event.target.id();
    const details =
      (lastResponse && lastResponse.details && lastResponse.details.nodes[id]) || {};
    selectNode(id, details.inspector || null);
    setVedaTrayCollapsed(false);
    if (details.inspector) {
      renderInspector(details.inspector);
      if (state.vedaTablesEnabled) {
        renderVedaTrayForInspector(details.inspector);
      }
    } else {
      renderRawDetails(details);
      renderVedaTrayForCurrentSelection();
    }
  });

  cy.on("tap", "edge", (event) => {
    const id = event.target.id();
    const details =
      (lastResponse && lastResponse.details && lastResponse.details.edges[id]) || {};
    selectEdge(id);
    if (details.inspector) {
      renderInspector(details.inspector);
    } else {
      renderRawDetails(details);
    }
    renderVedaTrayForCurrentSelection();
  });

  cy.on("render layoutstop resize pan zoom", () => {
    scheduleProcessLabelRefresh();
  });
}

function renderGraph(response) {
  lastResponse = response;
  const detailNodes = (response.details && response.details.nodes) || {};
  const graphEdges = response.graph.edges || [];

  const nodes = (response.graph.nodes || []).map((node) => {
    const style = styleForNode(node.type);
    const details = detailNodes[node.id] || {};
    const stage = typeof details.stage === "string" ? details.stage : null;
    const stageRankValue = isProcessNodeType(node.type) ? stageRank(stage) : null;
    const label =
      isProcessNodeType(node.type) && stage
        ? `${node.label}\n[${formatStageLabel(stage)}]`
        : node.label;
    const ledgerEmissions = normalizeLedgerEmissions(details.ledger_emissions);
    const border = ledgerBorderStyle(ledgerEmissions);

    return {
      data: {
        id: node.id,
        label,
        type: node.type,
        shape: style.shape,
        color: style.color,
        stage,
        stageRank: stageRankValue,
        borderColor: border.color,
        borderWidth: border.width,
        ledgerEmissions,
      },
    };
  });

  const edges = (response.graph.edges || []).map((edge) => ({
    data: {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: edge.type,
    },
  }));

  cy.elements().remove();
  cy.add(nodes);
  cy.add(edges);
  const stagePositions = buildAlternatingColumnPositions(nodes, graphEdges);
  if (stagePositions) {
    cy.layout({
      name: "preset",
      positions: (ele) => stagePositions[ele.id()] || { x: 0, y: 0 },
      fit: false,
      animate: false,
    }).run();
    resetGraphViewport();
  } else {
    cy.layout({
      name: "dagre",
      rankDir: "LR",
      nodeSep: 60,
      rankSep: 100,
      edgeSep: 25,
      fit: false,
      animate: false,
    }).run();
    resetGraphViewport();
  }

  renderDiagnostics(response.diagnostics || []);
  renderSelectionFromState();
  scheduleProcessLabelRefresh();
}

function createOptionButton({ label, active, title, className, disabled, onClick }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `option-btn${active ? " is-active" : ""}${className ? ` ${className}` : ""}`;
  button.textContent = label;
  button.disabled = Boolean(disabled);
  if (title) {
    button.title = title;
  }
  button.addEventListener("click", (event) => {
    if (button.disabled) {
      return;
    }
    Promise.resolve(onClick(event)).catch((error) => {
      setStatus("Sidebar action failed");
      renderDiagnostics([{ severity: "error", message: String(error) }]);
    });
  });
  return button;
}

function renderPlaceholder(container, text) {
  const placeholder = document.createElement("div");
  placeholder.className = "option-placeholder";
  placeholder.textContent = text;
  container.appendChild(placeholder);
}

function renderFileExplorer() {
  const container = document.getElementById("fileButtons");
  const currentDirLabel = document.getElementById("currentDirLabel");
  const selectedFileLabel = document.getElementById("selectedFileLabel");
  const upButton = document.getElementById("upDirBtn");

  container.innerHTML = "";
  currentDirLabel.textContent = `Dir: ${relativeToWorkspace(state.currentDir) || "(none)"}`;
  selectedFileLabel.textContent = state.file
    ? `Selected: ${relativeToWorkspace(state.file)}`
    : "Selected: (none)";
  upButton.disabled = !state.parentDir;

  const directories = state.currentEntries.filter(
    (entry) => entry.kind === "directory",
  );
  const files = state.currentEntries.filter((entry) => entry.kind === "file");

  directories.forEach((entry) => {
    container.appendChild(
      createOptionButton({
        label: `[DIR] ${entry.name}/`,
        title: relativeToWorkspace(entry.path),
        className: "is-directory",
        onClick: async () => {
          await loadDirectory(entry.path);
        },
      }),
    );
  });

  files.forEach((entry) => {
    container.appendChild(
      createOptionButton({
        label: entry.name,
        title: relativeToWorkspace(entry.path),
        active: entry.path === state.file,
        className: "is-file",
        onClick: () => {
          if (entry.path === state.file) {
            return;
          }
          state.file = entry.path;
          runQuery();
        },
      }),
    );
  });

  if (directories.length === 0 && files.length === 0) {
    renderPlaceholder(container, "No folders or .veda.yaml files in this directory.");
  }
}

function renderSingleGroup(containerId, options, selectedValue, onSelect) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  if (options.length === 0) {
    renderPlaceholder(container, "No options");
    return;
  }

  options.forEach((option) => {
    container.appendChild(
      createOptionButton({
        label: option.label,
        title: option.title || option.label,
        active: option.value === selectedValue,
        onClick: () => {
          if (option.value === selectedValue) {
            return;
          }
          onSelect(option.value);
        },
      }),
    );
  });
}

function updateMultiSelection(currentValues, value, event) {
  const useMultiSelect = event.ctrlKey || event.metaKey;
  const currentSet = new Set(currentValues);

  if (useMultiSelect) {
    if (currentSet.has(value)) {
      currentSet.delete(value);
    } else {
      currentSet.add(value);
    }
    return [...currentSet];
  }

  return [value];
}

function renderRegionGroup() {
  const container = document.getElementById("regionButtons");
  container.innerHTML = "";

  const available = state.availableRegions;
  if (available.length === 0) {
    renderPlaceholder(container, "No regions");
    return;
  }

  const uiSelected =
    state.regions.length === 0
      ? [...available]
      : normalizeToKnown(state.regions, available);

  container.appendChild(
    createOptionButton({
      label: "(all regions)",
      active: state.regions.length === 0,
      onClick: () => {
        if (state.regions.length === 0) {
          return;
        }
        state.regions = [];
        runQuery();
      },
    }),
  );

  available.forEach((region) => {
    container.appendChild(
      createOptionButton({
        label: region,
        active: uiSelected.includes(region),
        onClick: (event) => {
          let next = updateMultiSelection(uiSelected, region, event);
          next = normalizeToKnown(next, available);

          if (next.length === 0 || next.length === available.length) {
            state.regions = [];
          } else {
            state.regions = next;
          }

          runQuery();
        },
      }),
    );
  });
}

function renderFacetMultiGroup({
  containerId,
  available,
  selected,
  anyLabel,
  onSelect,
}) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  if (available.length === 0) {
    renderPlaceholder(container, "No options");
    return;
  }

  const knownSelected = normalizeToKnown(selected, available);

  container.appendChild(
    createOptionButton({
      label: anyLabel,
      active: knownSelected.length === 0,
      onClick: () => {
        if (knownSelected.length === 0) {
          return;
        }
        onSelect([]);
        runQuery();
      },
    }),
  );

  available.forEach((value) => {
    container.appendChild(
      createOptionButton({
        label: value,
        active: knownSelected.includes(value),
        onClick: (event) => {
          let next = updateMultiSelection(knownSelected, value, event);
          next = normalizeToKnown(next, available);
          if (next.length === available.length) {
            next = [];
          }
          onSelect(next);
          runQuery();
        },
      }),
    );
  });
}

function renderVedaTablesControl() {
  const container = document.getElementById("vedaTablesControls");
  const hint = document.getElementById("vedaTablesHint");
  const disabled = state.lens !== "system";

  container.innerHTML = "";
  hint.textContent = disabled
    ? "Available in system lens only."
    : "Enable rendered VEDA/TIMES tables for the current selection.";

  container.appendChild(
    createOptionButton({
      label: state.vedaTablesEnabled ? "Hide VEDA tables" : "Show VEDA tables",
      active: state.vedaTablesEnabled,
      disabled,
      onClick: () => {
        const nextEnabled = !state.vedaTablesEnabled;
        setVedaTablesEnabled(nextEnabled);
        if (nextEnabled) {
          setVedaTrayCollapsed(false);
        } else {
          hideVedaTray();
        }
        renderControls();
        renderSelectionFromState();
      },
    }),
  );
}

function renderControls() {
  renderFileExplorer();
  setSidebarTab(state.activeSidebarTab);

  renderSingleGroup("modeButtons", MODE_OPTIONS, state.mode, (value) => {
    state.mode = value;
    runQuery();
  });

  renderSingleGroup(
    "granularityButtons",
    GRANULARITY_OPTIONS,
    state.granularity,
    (value) => {
      state.granularity = value;
      if (value === "instance" && state.commodityView !== "scoped") {
        state.commodityView = "scoped";
      } else if (value !== "instance" && state.commodityView === "scoped") {
        state.commodityView = "collapse_scope";
      }
      runQuery();
    },
  );

  renderSingleGroup("lensButtons", LENS_OPTIONS, state.lens, (value) => {
    state.lens = value;
    runQuery();
  });

  renderSingleGroup(
    "commodityViewButtons",
    COMMODITY_VIEW_OPTIONS,
    state.commodityView,
    (value) => {
      state.commodityView = value;
      runQuery();
    },
  );

  renderSingleGroup(
    "caseButtons",
    [{ value: "", label: "(default case)" }].concat(
      state.availableCases.map((item) => ({ value: item, label: item })),
    ),
    state.caseName,
    (value) => {
      state.caseName = value;
      runQuery();
    },
  );

  renderSingleGroup(
    "runButtons",
    [{ value: "", label: "(auto run)" }].concat(
      state.availableRuns.map((item) => ({ value: item, label: item })),
    ),
    state.runId,
    (value) => {
      state.runId = value;
      runQuery();
    },
  );

  renderVedaTablesControl();
  renderRegionGroup();

  renderFacetMultiGroup({
    containerId: "sectorButtons",
    available: state.availableSectors,
    selected: state.sectors,
    anyLabel: "(any sector)",
    onSelect: (values) => {
      state.sectors = values;
    },
  });

  renderFacetMultiGroup({
    containerId: "scopeButtons",
    available: state.availableScopes,
    selected: state.scopes,
    anyLabel: "(any scope)",
    onSelect: (values) => {
      state.scopes = values;
    },
  });
}

function reconcileStateWithFacets() {
  state.availableCases = [...state.availableCases];
  state.availableRuns = [...state.availableRuns];
  state.availableRegions = [...state.availableRegions];
  state.availableSectors = [...state.availableSectors];
  state.availableScopes = [...state.availableScopes];

  if (state.caseName && !state.availableCases.includes(state.caseName)) {
    state.caseName = "";
  }
  if (state.runId && !state.availableRuns.includes(state.runId)) {
    state.runId = "";
  }

  state.regions = normalizeToKnown(state.regions, state.availableRegions);
  if (state.regions.length === state.availableRegions.length) {
    state.regions = [];
  }

  state.sectors = normalizeToKnown(state.sectors, state.availableSectors);
  if (state.sectors.length === state.availableSectors.length) {
    state.sectors = [];
  }

  state.scopes = normalizeToKnown(state.scopes, state.availableScopes);
  if (state.scopes.length === state.availableScopes.length) {
    state.scopes = [];
  }
}

function updateFacetControls(response) {
  const facets = response.facets || {};
  state.availableCases = facets.cases || [];
  state.availableRuns = facets.runs || [];
  state.availableRegions = facets.regions || [];
  state.availableSectors = facets.sectors || [];
  state.availableScopes = facets.scopes || [];
  const availableCommodityViews = facets.commodity_views || [];
  if (
    availableCommodityViews.length > 0 &&
    !availableCommodityViews.includes(state.commodityView)
  ) {
    state.commodityView = availableCommodityViews[0];
  }

  reconcileStateWithFacets();
  renderControls();
}

async function runQuery() {
  if (!state.file) {
    setStatus("Select a .veda.yaml file from the sidebar");
    return;
  }

  setStatus("Querying...");
  try {
    const response = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getRequest()),
    });
    const data = await response.json();
    renderGraph(data);
    updateFacetControls(data);
    setStatus(formatQueryStatus(data.status, data.mode_used));
  } catch (error) {
    setStatus("Query failed");
    renderDiagnostics([{ severity: "error", message: String(error) }]);
  }
}

async function loadDirectory(targetDir) {
  const url = new URL("/api/files", window.location.origin);
  if (targetDir) {
    url.searchParams.set("dir", targetDir);
  }

  const response = await fetch(`${url.pathname}${url.search}`);
  if (!response.ok) {
    throw new Error(`Directory load failed (${response.status})`);
  }

  const payload = await response.json();
  state.workspaceRoot = payload.workspace_root || state.workspaceRoot;
  state.currentDir = payload.current_dir || "";
  state.parentDir = payload.parent_dir || null;
  state.currentEntries = payload.entries || [];

  if (!state.file && payload.initial_file) {
    state.file = payload.initial_file;
  }
  if (!state.runId && payload.initial_run) {
    state.runId = payload.initial_run;
  }

  if (!state.file) {
    const firstFile = state.currentEntries.find((entry) => entry.kind === "file");
    if (firstFile) {
      state.file = firstFile.path;
    }
  }

  renderControls();
}

function wireControls() {
  document.getElementById("resetViewBtn").addEventListener("click", () => {
    resetGraphViewport();
  });
  document.getElementById("refreshBtn").addEventListener("click", () => runQuery());
  document.getElementById("toggleSidebarBtn").addEventListener("click", () => {
    setSidebarCollapsed(!state.sidebarCollapsed);
  });
  document.querySelectorAll(".sidebar-tab").forEach((button) => {
    button.addEventListener("click", () => {
      setSidebarTab(button.dataset.panel);
    });
  });
  const toggleDetails = () => {
    setDetailsPaneCollapsed(!state.detailsPaneCollapsed);
  };
  document
    .getElementById("toggleInspectorBtn")
    .addEventListener("click", toggleDetails);
  document
    .getElementById("toggleDetailsPaneBtn")
    .addEventListener("click", toggleDetails);
  document
    .getElementById("objectExplorerShowAllAttributes")
    .addEventListener("change", (event) => {
      setObjectExplorerShowAllAttributes(event.target.checked);
    });
  document.getElementById("closeVedaTrayBtn").addEventListener("click", () => {
    setVedaTrayCollapsed(true);
    hideVedaTray();
  });
  document.getElementById("openVedaTrayBtn").addEventListener("click", () => {
    setVedaTrayCollapsed(false);
    renderVedaTrayForCurrentSelection();
  });
  document.getElementById("upDirBtn").addEventListener("click", async () => {
    if (!state.parentDir) {
      return;
    }
    await loadDirectory(state.parentDir);
  });
  document
    .getElementById("detailsResizeHandle")
    .addEventListener("pointerdown", (event) => {
      if (state.detailsPaneCollapsed) {
        return;
      }
      const appRoot = document.getElementById("appRoot");
      const container = document.getElementById("resMainTop");
      appRoot.classList.add("is-resizing");
      const onPointerMove = (moveEvent) => {
        const rect = container.getBoundingClientRect();
        setDetailsPaneWidth(rect.right - moveEvent.clientX);
        scheduleProcessLabelRefresh();
      };
      const onPointerUp = () => {
        appRoot.classList.remove("is-resizing");
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("pointerup", onPointerUp);
        scheduleViewportReset();
      };
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
      event.preventDefault();
    });
  window.addEventListener("resize", () => {
    scheduleProcessLabelRefresh();
    if (windowResizeTimer) {
      window.clearTimeout(windowResizeTimer);
    }
    windowResizeTimer = window.setTimeout(() => {
      scheduleViewportReset();
    }, 120);
  });
}

async function bootstrap() {
  initCy();
  wireControls();
  setSidebarCollapsed(loadSidebarPreference());
  setSidebarTab(loadSidebarTabPreference());
  setDetailsPaneWidth(loadDetailsPaneWidthPreference(), { persist: false });
  setDetailsPaneCollapsed(loadDetailsPaneCollapsedPreference());
  setVedaTablesEnabled(loadVedaTablesPreference());
  setObjectExplorerShowAllAttributes(loadObjectExplorerShowAllPreference());
  renderDiagnostics([]);

  try {
    await loadDirectory();
    await runQuery();
  } catch (error) {
    setStatus("Failed to initialize sidebar");
    renderDiagnostics([{ severity: "error", message: String(error) }]);
  }
}

bootstrap();
