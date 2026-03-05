let cy = null;
let lastResponse = null;

const SIDEBAR_STORAGE_KEY = "vedalang.viz.sidebarCollapsed";

const MODE_OPTIONS = [
  { value: "compiled", label: "compiled" },
  { value: "source", label: "source" },
];

const GRANULARITY_OPTIONS = [
  { value: "role", label: "role" },
  { value: "provider", label: "provider" },
  { value: "provider_variant", label: "provider×variant" },
  { value: "provider_variant_mode", label: "provider×variant×mode" },
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

const STAGE_ORDER = ["supply", "conversion", "distribution", "storage", "end_use", "sink"];
const STAGE_RANK = new Map(STAGE_ORDER.map((stage, index) => [stage, index]));
const PROCESS_NODE_TYPES = new Set([
  "role",
  "provider",
  "provider_variant",
  "provider_variant_mode",
  "instance",
]);
const MAX_AUTO_FIT_ZOOM = 1.6;

const state = {
  file: "",
  mode: "compiled",
  granularity: "role",
  lens: "system",
  commodityView: "collapse_scope",
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
  if (nodeType === "provider") {
    return { shape: "round-rectangle", color: "#0f766e" };
  }
  if (nodeType === "provider_variant" || nodeType === "variant") {
    return { shape: "round-rectangle", color: "#9333ea" };
  }
  if (nodeType === "provider_variant_mode" || nodeType === "mode") {
    return { shape: "round-rectangle", color: "#f97316" };
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
  const usedStageRanks = [...new Set(
    processNodesWithStage.map((node) => Number(node.data.stageRank)),
  )].sort((a, b) => a - b);
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

    if (Number.isFinite(sourceProcessCol) && isCommodityNodeType(targetNode.data.type)) {
      const list = producerAnchors.get(edge.target) || [];
      list.push(sourceProcessCol + 1);
      producerAnchors.set(edge.target, list);
    }

    if (isCommodityNodeType(sourceNode.data.type) && Number.isFinite(targetProcessCol)) {
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

  const assignedColumns = [...nodeColumns.values()].filter((value) => Number.isFinite(value));
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

  const columnGap = 170;
  const yGap = 88;
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

function fitViewportWithZoomCap() {
  cy.fit(cy.elements(), 40);
  if (cy.zoom() > MAX_AUTO_FIT_ZOOM) {
    cy.zoom(MAX_AUTO_FIT_ZOOM);
    cy.center();
  }
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

  const nodes = (response.graph.nodes || []).map((node) => {
    const style = styleForNode(node.type);
    const details = detailNodes[node.id] || {};
    const stage = typeof details.stage === "string" ? details.stage : null;
    const stageRankValue = isProcessNodeType(node.type) ? stageRank(stage) : null;
    const label = isProcessNodeType(node.type) && stage
      ? `${node.label}\n[${formatStageLabel(stage)}]`
      : node.label;

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
    fitViewportWithZoomCap();
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
    fitViewportWithZoomCap();
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
    if (value === "instance" && state.commodityView !== "scoped") {
      state.commodityView = "scoped";
    } else if (value !== "instance" && state.commodityView === "scoped") {
      state.commodityView = "collapse_scope";
    }
    runQuery();
  });

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
