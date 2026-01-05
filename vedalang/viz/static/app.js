// VedaLang RES Visualizer - Frontend Application

const PROCESS_COLORS = {
    import: '#22c55e',
    export: '#10b981',
    generation: '#3b82f6',
    demand: '#f59e0b',
    storage: '#8b5cf6',
    trade: '#06b6d4',
    conversion: '#64748b'
};

const COMMODITY_COLORS = {
    energy: '#06b6d4',
    emission: '#ef4444',
    demand: '#f97316',
    material: '#a855f7'
};

let cy = null;
let ws = null;
let reconnectTimeout = null;

let baseGraph = null;
let currentViewMode = 'all';
let selectedRegion = null;
let selectedRegions = [];
let availableRegions = [];

function initCytoscape() {
    cy = cytoscape({
        container: document.getElementById('cy'),
        style: [
            // Process nodes (rounded rectangles)
            {
                selector: 'node[type="process"]',
                style: {
                    'shape': 'round-rectangle',
                    'width': 100,
                    'height': 40,
                    'label': 'data(label)',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': '11px',
                    'font-weight': '500',
                    'color': '#ffffff',
                    'text-outline-width': 0,
                    'background-color': function(ele) {
                        return PROCESS_COLORS[ele.data('processClass')] || PROCESS_COLORS.conversion;
                    },
                    'border-width': 2,
                    'border-color': function(ele) {
                        const base = PROCESS_COLORS[ele.data('processClass')] || PROCESS_COLORS.conversion;
                        return shadeColor(base, -20);
                    }
                }
            },
            // Commodity nodes (circles)
            {
                selector: 'node[type="commodity"]',
                style: {
                    'shape': 'ellipse',
                    'width': 50,
                    'height': 50,
                    'label': 'data(label)',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': '11px',
                    'font-weight': '600',
                    'color': '#ffffff',
                    'background-color': function(ele) {
                        return COMMODITY_COLORS[ele.data('commodityType')] || COMMODITY_COLORS.energy;
                    },
                    'border-width': 2,
                    'border-color': function(ele) {
                        const base = COMMODITY_COLORS[ele.data('commodityType')] || COMMODITY_COLORS.energy;
                        return shadeColor(base, -20);
                    }
                }
            },
            // Trade view commodity nodes (with region label)
            {
                selector: 'node[?isTradeNode]',
                style: {
                    'width': 80,
                    'height': 80,
                    'font-size': '11px',
                    'label': function(ele) {
                        return ele.data('label') + '\n' + ele.data('sublabel');
                    },
                    'text-wrap': 'wrap',
                    'line-height': 1.4
                }
            },
            // Input edges
            {
                selector: 'edge[kind="input"]',
                style: {
                    'width': 2,
                    'line-color': '#52525b',
                    'target-arrow-color': '#52525b',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'arrow-scale': 0.8
                }
            },
            // Output edges
            {
                selector: 'edge[kind="output"]',
                style: {
                    'width': 3,
                    'line-color': '#71717a',
                    'target-arrow-color': '#71717a',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'arrow-scale': 1
                }
            },
            // Emission edges
            {
                selector: 'edge[kind="emission"]',
                style: {
                    'width': 2,
                    'line-color': '#ef4444',
                    'line-style': 'dashed',
                    'target-arrow-color': '#ef4444',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'arrow-scale': 0.8
                }
            },
            // Trade edges
            {
                selector: 'edge[kind="trade"]',
                style: {
                    'width': 2,
                    'line-color': '#06b6d4',
                    'line-style': 'dotted',
                    'target-arrow-color': '#06b6d4',
                    'target-arrow-shape': 'diamond',
                    'curve-style': 'bezier',
                    'arrow-scale': 0.8,
                    'opacity': 0.7
                }
            },
            // Hover states
            {
                selector: 'node:active',
                style: {
                    'overlay-color': '#ffffff',
                    'overlay-padding': 4,
                    'overlay-opacity': 0.2
                }
            }
        ],
        layout: { name: 'preset' },
        wheelSensitivity: 0.3,
        minZoom: 0.1,
        maxZoom: 3
    });

    // Tooltip on tap
    cy.on('tap', 'node', function(evt) {
        const node = evt.target;
        console.log('Node clicked:', node.data());
    });
}

function shadeColor(color, percent) {
    const num = parseInt(color.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = Math.max(0, Math.min(255, (num >> 16) + amt));
    const G = Math.max(0, Math.min(255, (num >> 8 & 0x00FF) + amt));
    const B = Math.max(0, Math.min(255, (num & 0x0000FF) + amt));
    return '#' + (0x1000000 + R * 0x10000 + G * 0x100 + B).toString(16).slice(1);
}

function runLayout() {
    if (!cy || cy.nodes().length === 0) return;

    const layout = cy.layout({
        name: 'dagre',
        rankDir: 'LR',
        nodeSep: 60,
        rankSep: 100,
        edgeSep: 20,
        animate: true,
        animationDuration: 300,
        fit: true,
        padding: 50
    });

    layout.run();
}

function updateGraph(data) {
    if (!cy) return;

    cy.elements().remove();
    cy.add(data.nodes);
    cy.add(data.edges);

    document.getElementById('nodeCount').textContent = data.nodes.length;
    document.getElementById('edgeCount').textContent = data.edges.length;

    runLayout();

    document.getElementById('errorBanner').classList.remove('visible');
}

function rebuildView() {
    if (!cy || !baseGraph) return;
    console.log('rebuildView called, mode:', currentViewMode);
    const viewGraph = buildViewGraph(baseGraph, {
        mode: currentViewMode,
        singleRegion: selectedRegion,
        regions: selectedRegions
    });
    console.log('viewGraph:', viewGraph.modelName, 'nodes:', viewGraph.nodes.length, 'edges:', viewGraph.edges.length);
    document.getElementById('modelName').textContent = viewGraph.modelName;
    updateGraph(viewGraph);
}

function buildViewGraph(base, options) {
    const { mode, singleRegion, regions } = options;

    if (mode === 'all') {
        return {
            modelName: base.modelName,
            nodes: base.nodes,
            edges: base.edges
        };
    }

    if (mode === 'single') {
        const edges = base.edges.filter(e => e.data.kind !== 'trade');
        return {
            modelName: base.modelName + ' (' + (singleRegion || 'region') + ')',
            nodes: base.nodes,
            edges: edges
        };
    }

    if (mode === 'multi') {
        const selected = new Set(regions || []);
        const tradeEdges = base.edges.filter(e => e.data.kind === 'trade');

        const nodesByRegionComm = new Map();
        const nodes = [];
        const edges = [];

        for (const e of tradeEdges) {
            const { commodity, origin, destination } = e.data;
            if (!selected.has(origin) || !selected.has(destination)) continue;

            const baseCommNode = base.nodes.find(n => n.data.id === 'C:' + commodity);
            const commodityType = baseCommNode ? baseCommNode.data.commodityType : 'energy';

            function ensureNode(region) {
                const key = commodity + ':' + region;
                if (!nodesByRegionComm.has(key)) {
                    const node = {
                        data: {
                            id: 'C:' + commodity + ':' + region,
                            label: commodity,
                            sublabel: region,
                            type: 'commodity',
                            commodityType: commodityType,
                            region: region,
                            baseCommodityId: 'C:' + commodity,
                            isTradeNode: true
                        }
                    };
                    nodesByRegionComm.set(key, node);
                    nodes.push(node);
                }
                return nodesByRegionComm.get(key);
            }

            ensureNode(origin);
            ensureNode(destination);

            edges.push({
                data: {
                    id: 'T:' + commodity + ':' + origin + '->' + destination,
                    source: 'C:' + commodity + ':' + origin,
                    target: 'C:' + commodity + ':' + destination,
                    kind: 'trade',
                    commodity: commodity,
                    origin: origin,
                    destination: destination,
                    bidirectional: e.data.bidirectional,
                    efficiency: e.data.efficiency
                }
            });
        }

        return {
            modelName: base.modelName + ' (trade flows)',
            nodes: nodes,
            edges: edges
        };
    }

    return base;
}

function initRegionControls(regions) {
    console.log('initRegionControls called with regions:', regions);
    availableRegions = regions;
    selectedRegion = regions[0] || null;
    selectedRegions = [...regions];
    console.log('selectedRegions initialized:', selectedRegions);

    renderRegionPills();
    updateRegionControlVisibility();
}

function renderRegionPills() {
    const pillsContainer = document.getElementById('regionPills');
    if (!pillsContainer) return;

    pillsContainer.innerHTML = '';

    availableRegions.forEach(r => {
        const pill = document.createElement('button');
        pill.className = 'region-pill';
        pill.textContent = r;
        pill.dataset.region = r;

        if (currentViewMode === 'single') {
            if (r === selectedRegion) {
                pill.classList.add('single-selected');
            }
        } else if (currentViewMode === 'multi') {
            if (selectedRegions.includes(r)) {
                pill.classList.add('selected');
            }
        }

        pill.addEventListener('click', () => handlePillClick(r));
        pillsContainer.appendChild(pill);
    });
}

function handlePillClick(region) {
    if (currentViewMode === 'single') {
        selectedRegion = region;
        renderRegionPills();
        rebuildView();
    } else if (currentViewMode === 'multi') {
        if (selectedRegions.includes(region)) {
            selectedRegions = selectedRegions.filter(r => r !== region);
        } else {
            selectedRegions.push(region);
        }
        renderRegionPills();
        rebuildView();
    }
}

function updateRegionControlVisibility() {
    const regionSection = document.getElementById('regionSection');
    const sectionTitle = document.getElementById('regionSectionTitle');

    if (currentViewMode === 'all') {
        regionSection.classList.add('hidden');
    } else {
        regionSection.classList.remove('hidden');
        sectionTitle.textContent = currentViewMode === 'single' ? 'Select Region' : 'Trade Between';
    }

    renderRegionPills();
}

function showError(message) {
    document.getElementById('errorMessage').textContent = message;
    document.getElementById('errorBanner').classList.add('visible');
}

function setStatus(connected, hasError = false) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');

    dot.classList.remove('disconnected', 'error');

    if (!connected) {
        dot.classList.add('disconnected');
        text.textContent = 'Disconnected';
    } else if (hasError) {
        dot.classList.add('error');
        text.textContent = 'Parse Error';
    } else {
        text.textContent = 'Watching';
    }
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log('WebSocket connected');
        setStatus(true);
        if (reconnectTimeout) {
            clearTimeout(reconnectTimeout);
            reconnectTimeout = null;
        }
    };

    ws.onmessage = function(event) {
        try {
            const msg = JSON.parse(event.data);

            if (msg.type === 'graph') {
                baseGraph = msg.data;
                availableRegions = baseGraph.regions || [];
                initRegionControls(availableRegions);
                document.getElementById('modelName').textContent = baseGraph.modelName || 'Model';
                rebuildView();
                setStatus(true, false);
            } else if (msg.type === 'error') {
                showError(msg.message);
                setStatus(true, true);
            }
        } catch (e) {
            console.error('Failed to parse message:', e);
        }
    };

    ws.onclose = function() {
        console.log('WebSocket disconnected');
        setStatus(false);
        // Reconnect after delay
        reconnectTimeout = setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = function(err) {
        console.error('WebSocket error:', err);
    };
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initCytoscape();
    connectWebSocket();

    // Control buttons
    document.getElementById('fitBtn').addEventListener('click', function() {
        cy.fit(50);
    });

    document.getElementById('layoutBtn').addEventListener('click', function() {
        runLayout();
    });

    document.getElementById('zoomInBtn').addEventListener('click', function() {
        cy.zoom(cy.zoom() * 1.2);
        cy.center();
    });

    document.getElementById('zoomOutBtn').addEventListener('click', function() {
        cy.zoom(cy.zoom() / 1.2);
        cy.center();
    });

    // View mode tabs
    document.querySelectorAll('.view-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            document.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            currentViewMode = this.dataset.mode;
            updateRegionControlVisibility();
            rebuildView();
        });
    });

    // Sidebar collapse toggle
    document.getElementById('sidebarToggle').addEventListener('click', function() {
        document.getElementById('sidebar').classList.toggle('collapsed');
    });
});
