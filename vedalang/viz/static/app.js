let cy = null;
let lastResponse = null;

const SIDEBAR_STORAGE_KEY = "vedalang.viz.sidebarCollapsed";

const MODE_OPTIONS = [
  { value: "compiled", label: "compiled" },
  { value: "source", label: "source" },
];

const GRANULARITY_OPTIONS = [
  { value: "role", label: "role" },
  { value: "variant", label: "variant" },
  { value: "instance", label: "instance" },
];

const LENS_OPTIONS = [
  { value: "system", label: "system" },
  { value: "trade", label: "trade" },
];

const STAGE_ORDER = ["supply", "conversion", "distribution", "storage", "end_use", "sink"];
const STAGE_RANK = new Map(STAGE_ORDER.map((stage, index) => [stage, index]));
const PROCESS_NODE_TYPES = new Set(["role", "variant", "instance"]);

const state = {
  file: "",
  mode: "compiled",
  granularity: "role",
  lens: "system",
  caseName: "",
  regions: [],
  sectors: [],
  scopes: [],
  availableCases: [],
  availableRegions: [],
  availableSectors: [],
  availableScopes: [],
  workspaceRoot: "",
  currentDir: "",
  parentDir: null,
  currentEntries: [],
  sidebarCollapsed: false,
};

function setStatus(text) {
  document.getElementById("status").textContent = text;
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

function setSidebarCollapsed(collapsed) {
  state.sidebarCollapsed = collapsed;
  const appRoot = document.getElementById("appRoot");
  const toggleButton = document.getElementById("toggleSidebarBtn");

  appRoot.classList.toggle("sidebar-collapsed", collapsed);
  toggleButton.textContent = collapsed ? "▶" : "◀";
  toggleButton.title = collapsed ? "Expand file sidebar" : "Collapse file sidebar";

  try {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
  } catch (error) {
    void error;
  }
}

function loadSidebarPreference() {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
  } catch (error) {
    void error;
    return false;
  }
}

function getRequest() {
  return {
    version: "1",
    file: state.file,
    mode: state.mode,
    granularity: state.granularity,
    lens: state.lens,
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
  if (nodeType === "variant") {
    return { shape: "round-rectangle", color: "#9333ea" };
  }
  return { shape: "round-rectangle", color: "#16a34a" };
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

function inferCommodityRank(nodeId, graphEdges, processRanks) {
  let inputBound = Number.POSITIVE_INFINITY;
  let outputBound = Number.NEGATIVE_INFINITY;
  let hasInputBound = false;
  let hasOutputBound = false;

  for (const edge of graphEdges) {
    if (edge.source === nodeId) {
      const processRank = processRanks.get(edge.target);
      if (Number.isFinite(processRank)) {
        inputBound = Math.min(inputBound, processRank - 0.5);
        hasInputBound = true;
      }
    }

    if (edge.target === nodeId) {
      const processRank = processRanks.get(edge.source);
      if (Number.isFinite(processRank)) {
        outputBound = Math.max(outputBound, processRank + 0.5);
        hasOutputBound = true;
      }
    }
  }

  if (hasInputBound && hasOutputBound) {
    return (inputBound + outputBound) / 2;
  }
  if (hasInputBound) {
    return inputBound;
  }
  if (hasOutputBound) {
    return outputBound;
  }
  return null;
}

function buildStageLanePositions(nodes) {
  const processNodesWithStage = nodes.filter(
    (node) => isProcessNodeType(node.data.type) && Number.isFinite(node.data.stageRank),
  );
  if (processNodesWithStage.length === 0) {
    return null;
  }

  const columns = new Map();
  for (const node of nodes) {
    if (!Number.isFinite(node.data.stageRank)) {
      continue;
    }
    const bucket = columns.get(node.data.stageRank) || [];
    bucket.push(node);
    columns.set(node.data.stageRank, bucket);
  }

  if (columns.size === 0) {
    return null;
  }

  const xGap = 260;
  const yGap = 90;
  const positions = {};
  const sortedRanks = [...columns.keys()].sort((a, b) => a - b);

  for (const rank of sortedRanks) {
    const bucket = columns.get(rank) || [];
    bucket.sort((left, right) => {
      const leftProcess = isProcessNodeType(left.data.type) ? 0 : 1;
      const rightProcess = isProcessNodeType(right.data.type) ? 0 : 1;
      if (leftProcess !== rightProcess) {
        return leftProcess - rightProcess;
      }
      return String(left.data.label || left.data.id).localeCompare(
        String(right.data.label || right.data.id),
      );
    });

    const columnCenterOffset = ((bucket.length - 1) * yGap) / 2;
    bucket.forEach((node, index) => {
      positions[node.data.id] = {
        x: rank * xGap,
        y: index * yGap - columnCenterOffset,
      };
    });
  }

  return positions;
}

function initCy() {
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
          "border-width": 1,
          "border-color": "#0f172a",
          width: 60,
          height: 40,
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
    const details = (lastResponse && lastResponse.details && lastResponse.details.nodes[id]) || {};
    document.getElementById("details").textContent = JSON.stringify(details, null, 2);
  });

  cy.on("tap", "edge", (event) => {
    const id = event.target.id();
    const details = (lastResponse && lastResponse.details && lastResponse.details.edges[id]) || {};
    document.getElementById("details").textContent = JSON.stringify(details, null, 2);
  });
}

function renderGraph(response) {
  lastResponse = response;
  const detailNodes = (response.details && response.details.nodes) || {};
  const graphEdges = response.graph.edges || [];
  const processRanks = new Map();

  const nodes = (response.graph.nodes || []).map((node) => {
    const style = styleForNode(node.type);
    const details = detailNodes[node.id] || {};
    const stage = typeof details.stage === "string" ? details.stage : null;
    const stageRankValue = isProcessNodeType(node.type) ? stageRank(stage) : null;
    const label = isProcessNodeType(node.type) && stage
      ? `${node.label}\n[${formatStageLabel(stage)}]`
      : node.label;
    if (Number.isFinite(stageRankValue)) {
      processRanks.set(node.id, stageRankValue);
    }

    return {
      data: {
        id: node.id,
        label,
        type: node.type,
        shape: style.shape,
        color: style.color,
        stage,
        stageRank: stageRankValue,
      },
    };
  });

  nodes.forEach((node) => {
    if (node.data.type !== "commodity" && node.data.type !== "trade_commodity") {
      return;
    }
    const rank = inferCommodityRank(node.data.id, graphEdges, processRanks);
    if (Number.isFinite(rank)) {
      node.data.stageRank = rank;
    }
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
  const stagePositions = buildStageLanePositions(nodes);
  if (stagePositions) {
    cy.layout({
      name: "preset",
      positions: (ele) => stagePositions[ele.id()] || { x: 0, y: 0 },
      fit: true,
      padding: 40,
      animate: false,
    }).run();
  } else {
    cy.layout({
      name: "dagre",
      rankDir: "LR",
      nodeSep: 60,
      rankSep: 100,
      edgeSep: 25,
      fit: true,
      padding: 40,
      animate: false,
    }).run();
  }

  document.getElementById("diagnostics").textContent = JSON.stringify(response.diagnostics || [], null, 2);
}

function createOptionButton({ label, active, title, className, onClick }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `option-btn${active ? " is-active" : ""}${className ? ` ${className}` : ""}`;
  button.textContent = label;
  if (title) {
    button.title = title;
  }
  button.addEventListener("click", (event) => {
    Promise.resolve(onClick(event)).catch((error) => {
      setStatus("Sidebar action failed");
      document.getElementById("diagnostics").textContent = String(error);
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

  const directories = state.currentEntries.filter((entry) => entry.kind === "directory");
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

  const uiSelected = state.regions.length === 0 ? [...available] : normalizeToKnown(state.regions, available);

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

function renderFacetMultiGroup({ containerId, available, selected, anyLabel, onSelect }) {
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

function renderControls() {
  renderFileExplorer();

  renderSingleGroup("modeButtons", MODE_OPTIONS, state.mode, (value) => {
    state.mode = value;
    runQuery();
  });

  renderSingleGroup("granularityButtons", GRANULARITY_OPTIONS, state.granularity, (value) => {
    state.granularity = value;
    runQuery();
  });

  renderSingleGroup("lensButtons", LENS_OPTIONS, state.lens, (value) => {
    state.lens = value;
    runQuery();
  });

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
  state.availableRegions = [...state.availableRegions];
  state.availableSectors = [...state.availableSectors];
  state.availableScopes = [...state.availableScopes];

  if (state.caseName && !state.availableCases.includes(state.caseName)) {
    state.caseName = "";
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
  state.availableRegions = facets.regions || [];
  state.availableSectors = facets.sectors || [];
  state.availableScopes = facets.scopes || [];

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
    setStatus(`${data.status} (${data.mode_used})`);
  } catch (error) {
    setStatus("Query failed");
    document.getElementById("diagnostics").textContent = String(error);
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

  if (!state.file) {
    const firstFile = state.currentEntries.find((entry) => entry.kind === "file");
    if (firstFile) {
      state.file = firstFile.path;
    }
  }

  renderControls();
}

function wireControls() {
  document.getElementById("refreshBtn").addEventListener("click", () => runQuery());
  document.getElementById("toggleSidebarBtn").addEventListener("click", () => {
    setSidebarCollapsed(!state.sidebarCollapsed);
  });
  document.getElementById("upDirBtn").addEventListener("click", async () => {
    if (!state.parentDir) {
      return;
    }
    await loadDirectory(state.parentDir);
  });
}

async function bootstrap() {
  initCy();
  wireControls();
  setSidebarCollapsed(loadSidebarPreference());

  try {
    await loadDirectory();
    await runQuery();
  } catch (error) {
    setStatus("Failed to initialize sidebar");
    document.getElementById("diagnostics").textContent = String(error);
  }
}

bootstrap();
