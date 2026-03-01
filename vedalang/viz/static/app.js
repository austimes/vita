let cy = null;
let lastResponse = null;

const state = {
  file: "",
  mode: "compiled",
  granularity: "role",
  lens: "system",
  caseName: "",
  regions: [],
  sectors: [],
  segments: [],
};

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

function parseCsv(value) {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
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
      segments: state.segments,
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

  cy.on("tap", "node", (evt) => {
    const id = evt.target.id();
    const details = (lastResponse && lastResponse.details && lastResponse.details.nodes[id]) || {};
    document.getElementById("details").textContent = JSON.stringify(details, null, 2);
  });

  cy.on("tap", "edge", (evt) => {
    const id = evt.target.id();
    const details = (lastResponse && lastResponse.details && lastResponse.details.edges[id]) || {};
    document.getElementById("details").textContent = JSON.stringify(details, null, 2);
  });
}

function renderGraph(response) {
  lastResponse = response;
  const nodes = (response.graph.nodes || []).map((n) => {
    const style = styleForNode(n.type);
    return {
      data: {
        id: n.id,
        label: n.label,
        type: n.type,
        shape: style.shape,
        color: style.color,
      },
    };
  });
  const edges = (response.graph.edges || []).map((e) => ({
    data: {
      id: e.id,
      source: e.source,
      target: e.target,
      type: e.type,
    },
  }));

  cy.elements().remove();
  cy.add(nodes);
  cy.add(edges);

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

  document.getElementById("diagnostics").textContent = JSON.stringify(response.diagnostics || [], null, 2);
}

function updateFacetControls(response) {
  const facets = response.facets || {};

  const caseSelect = document.getElementById("caseSelect");
  const currentCase = state.caseName;
  caseSelect.innerHTML = '<option value="">(default)</option>';
  (facets.cases || []).forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    if (c === currentCase) {
      opt.selected = true;
    }
    caseSelect.appendChild(opt);
  });

  const regionFilters = document.getElementById("regionFilters");
  regionFilters.innerHTML = "";
  const available = facets.regions || [];
  available.forEach((region) => {
    const label = document.createElement("label");
    label.className = "region-pill";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = region;
    checkbox.checked = state.regions.length === 0 || state.regions.includes(region);
    checkbox.addEventListener("change", () => {
      const selected = Array.from(regionFilters.querySelectorAll("input:checked")).map((el) => el.value);
      state.regions = selected.length === available.length ? [] : selected;
      runQuery();
    });
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(" " + region));
    regionFilters.appendChild(label);
  });
}

async function runQuery() {
  if (!state.file) {
    return;
  }
  setStatus("Querying...");
  try {
    const resp = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getRequest()),
    });
    const data = await resp.json();
    renderGraph(data);
    updateFacetControls(data);
    setStatus(`${data.status} (${data.mode_used})`);
  } catch (err) {
    setStatus("Query failed");
    document.getElementById("diagnostics").textContent = String(err);
  }
}

async function loadFiles() {
  const response = await fetch("/api/files");
  const payload = await response.json();

  const select = document.getElementById("fileSelect");
  select.innerHTML = "";

  (payload.files || []).forEach((file) => {
    const opt = document.createElement("option");
    opt.value = file;
    opt.textContent = file;
    select.appendChild(opt);
  });

  if (payload.initial_file) {
    state.file = payload.initial_file;
    select.value = payload.initial_file;
  } else if ((payload.files || []).length > 0) {
    state.file = payload.files[0];
    select.value = payload.files[0];
  }
}

function wireControls() {
  document.getElementById("fileSelect").addEventListener("change", (evt) => {
    state.file = evt.target.value;
    runQuery();
  });

  document.getElementById("modeSelect").addEventListener("change", (evt) => {
    state.mode = evt.target.value;
    runQuery();
  });

  document.getElementById("granularitySelect").addEventListener("change", (evt) => {
    state.granularity = evt.target.value;
    runQuery();
  });

  document.getElementById("lensSelect").addEventListener("change", (evt) => {
    state.lens = evt.target.value;
    runQuery();
  });

  document.getElementById("caseSelect").addEventListener("change", (evt) => {
    state.caseName = evt.target.value;
    runQuery();
  });

  document.getElementById("sectorInput").addEventListener("change", (evt) => {
    state.sectors = parseCsv(evt.target.value);
    runQuery();
  });

  document.getElementById("segmentInput").addEventListener("change", (evt) => {
    state.segments = parseCsv(evt.target.value);
    runQuery();
  });

  document.getElementById("refreshBtn").addEventListener("click", () => runQuery());
}

async function bootstrap() {
  initCy();
  wireControls();
  await loadFiles();
  await runQuery();
}

bootstrap();
