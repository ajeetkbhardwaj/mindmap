"""MCP App HTML UI for Mindmap Interactive Graph Visualization.

Follows the MCP Apps (SEP-1865) and Antigravity UI specifications:
- Protocol handshake (ui/initialize, ui/notifications/initialized)
- ontoolresult message listener
- Antigravity theme variables (--color-background-primary, etc.)
- Interactive SVG-based force graph with search, zoom, filter, and detail inspection
"""

MINDMAP_APP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mindmap Knowledge Graph</title>
<style>
:root {
  --bg-primary: var(--color-background-primary, #0f172a);
  --bg-secondary: var(--color-background-secondary, #1e293b);
  --bg-tertiary: var(--color-background-tertiary, #334155);
  --text-primary: var(--color-text-primary, #f8fafc);
  --text-secondary: var(--color-text-secondary, #94a3b8);
  --border-color: var(--color-border-primary, #334155);
  --accent-color: var(--color-ring-primary, #3b82f6);
  --font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-family);
  overflow: hidden;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

header {
  padding: 10px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  z-index: 10;
}

.logo {
  font-weight: 700;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
}

.logo-badge {
  background: #3b82f6;
  color: #fff;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 500px;
}

.search-input {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  width: 100%;
  outline: none;
}
.search-input:focus {
  border-color: var(--accent-color);
}

.filter-btn {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}
.filter-btn.active {
  background: var(--accent-color);
  color: #fff;
  border-color: var(--accent-color);
}

.actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.action-btn:hover {
  background: var(--bg-tertiary);
}

#main-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}

svg#graph-canvas {
  width: 100%;
  height: 100%;
  cursor: grab;
}
svg#graph-canvas:active {
  cursor: grabbing;
}

#drawer {
  position: absolute;
  top: 0;
  right: -360px;
  width: 350px;
  height: 100%;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-color);
  transition: right 0.25s ease;
  padding: 16px;
  overflow-y: auto;
  box-shadow: -4px 0 16px rgba(0,0,0,0.3);
  z-index: 20;
}
#drawer.open {
  right: 0;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 8px;
}
.drawer-title {
  font-size: 15px;
  font-weight: 600;
  word-break: break-all;
}
.close-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 18px;
  cursor: pointer;
}

.drawer-section {
  margin-bottom: 14px;
}
.drawer-label {
  font-size: 11px;
  text-transform: uppercase;
  color: var(--text-secondary);
  margin-bottom: 4px;
  letter-spacing: 0.5px;
}
.drawer-value {
  font-size: 12px;
  line-height: 1.5;
  background: var(--bg-primary);
  padding: 8px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  word-break: break-all;
}
code {
  font-family: monospace;
}

.legend {
  position: absolute;
  bottom: 12px;
  left: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 11px;
  display: flex;
  gap: 12px;
  z-index: 10;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

#empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: var(--text-secondary);
}
</style>
</head>
<body>

<header>
  <div class="logo">
    <span>Mindmap</span>
    <span class="logo-badge">Graph UI</span>
  </div>
  <div class="controls">
    <input type="text" id="search-input" class="search-input" placeholder="Search functions, classes, modules..." />
    <button class="filter-btn active" data-type="all">All</button>
    <button class="filter-btn" data-type="Function">Funcs</button>
    <button class="filter-btn" data-type="Class">Classes</button>
    <button class="filter-btn" data-type="File">Files</button>
  </div>
  <div class="actions">
    <button class="action-btn" id="zoom-in">+</button>
    <button class="action-btn" id="zoom-out">-</button>
    <button class="action-btn" id="reset-view">Reset</button>
  </div>
</header>

<div id="main-container">
  <div id="empty-state">
    <p>Waiting for project graph data...</p>
    <span style="font-size:11px;margin-top:4px;display:block;">Call <code>view_mindmap()</code> or <code>get_project_overview()</code></span>
  </div>

  <svg id="graph-canvas">
    <g id="viewport">
      <g id="edge-layer"></g>
      <g id="node-layer"></g>
      <g id="label-layer"></g>
    </g>
  </svg>

  <div id="drawer">
    <div class="drawer-header">
      <div id="drawer-title" class="drawer-title">Symbol Detail</div>
      <button class="close-btn" id="close-drawer">&times;</button>
    </div>
    <div class="drawer-section">
      <div class="drawer-label">Kind</div>
      <div id="drawer-kind" class="drawer-value"></div>
    </div>
    <div class="drawer-section">
      <div class="drawer-label">File Path</div>
      <div id="drawer-file" class="drawer-value"></div>
    </div>
    <div class="drawer-section">
      <div class="drawer-label">Signature / Details</div>
      <pre id="drawer-sig" class="drawer-value"><code></code></pre>
    </div>
    <div class="drawer-section" id="doc-section">
      <div class="drawer-label">Documentation</div>
      <div id="drawer-doc" class="drawer-value"></div>
    </div>
  </div>

  <div class="legend">
    <div class="legend-item"><span class="legend-dot" style="background:#3b82f6;"></span> Module</div>
    <div class="legend-item"><span class="legend-dot" style="background:#06b6d4;"></span> File</div>
    <div class="legend-item"><span class="legend-dot" style="background:#10b981;"></span> Function</div>
    <div class="legend-item"><span class="legend-dot" style="background:#f59e0b;"></span> Class</div>
    <div class="legend-item"><span class="legend-dot" style="background:#ec4899;"></span> Concept</div>
  </div>
</div>

<script>
// Colors per node type
const COLORS = {
  Module: '#3b82f6',
  File: '#06b6d4',
  Function: '#10b981',
  Class: '#f59e0b',
  Concept: '#ec4899',
  WikiPage: '#8b5cf6',
  Default: '#64748b'
};

let graphData = { nodes: [], edges: [] };
let activeFilter = 'all';
let zoomLevel = 1;
let panX = 0;
let panY = 0;
let isPanning = false;
let startX = 0;
let startY = 0;

// Host context handshake for Antigravity Ext-Apps (SEP-1865)
window.addEventListener('message', (event) => {
  const msg = event.data;
  if (!msg) return;

  // Handshake initialization request
  if (msg.method === 'ui/initialize') {
    window.parent.postMessage({
      jsonrpc: '2.0',
      id: msg.id,
      result: {
        protocolVersion: '2024-11-05',
        capabilities: {}
      }
    }, '*');
    window.parent.postMessage({
      jsonrpc: '2.0',
      method: 'ui/notifications/initialized',
      params: {}
    }, '*');
  }

  // Tool results delivered to App
  if (msg.method === 'ui/notifications/tool-result' || msg.method === 'ontoolresult') {
    const res = msg.params?.result || msg.params;
    handleToolResult(res);
  }

  // Live theme / style changes
  if (msg.method === 'ui/notifications/host-context-changed') {
    const ctx = msg.params;
    if (ctx?.styles?.variables) {
      for (const [k, v] of Object.entries(ctx.styles.variables)) {
        document.documentElement.style.setProperty(k, v);
      }
    }
  }
});

function handleToolResult(result) {
  const structured = result?.structuredContent || result;
  if (!structured) return;

  if (structured.nodes && structured.edges) {
    graphData = { nodes: structured.nodes, edges: structured.edges };
    renderGraph();
  } else if (structured.tree) {
    // Convert project tree to nodes/edges
    const nodes = [];
    const edges = [];
    structured.tree.forEach((item, idx) => {
      nodes.push({
        id: 'node_' + idx,
        name: item.name || item.path,
        type: item.type?.[0] || 'File',
        path: item.path
      });
    });
    graphData = { nodes, edges };
    renderGraph();
  }
}

function renderGraph() {
  const emptyState = document.getElementById('empty-state');
  if (graphData.nodes.length === 0) {
    emptyState.style.display = 'block';
    return;
  }
  emptyState.style.display = 'none';

  const nodeLayer = document.getElementById('node-layer');
  const edgeLayer = document.getElementById('edge-layer');
  const labelLayer = document.getElementById('label-layer');
  nodeLayer.innerHTML = '';
  edgeLayer.innerHTML = '';
  labelLayer.innerHTML = '';

  const width = window.innerWidth;
  const height = window.innerHeight - 50;
  const centerX = width / 2;
  const centerY = height / 2;

  // Simple deterministic circular/radial layout
  const filteredNodes = graphData.nodes.filter(n => {
    if (activeFilter === 'all') return true;
    return n.type === activeFilter;
  });

  const nodeMap = new Map();
  const count = filteredNodes.length;
  const radius = Math.min(width, height) * 0.38;

  filteredNodes.forEach((node, i) => {
    const angle = (i / count) * 2 * Math.PI;
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    nodeMap.set(node.id, { ...node, x, y });
  });

  // Render edges
  graphData.edges.forEach(edge => {
    const from = nodeMap.get(edge.from);
    const to = nodeMap.get(edge.to);
    if (from && to) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', from.x);
      line.setAttribute('y1', from.y);
      line.setAttribute('x2', to.x);
      line.setAttribute('y2', to.y);
      line.setAttribute('stroke', '#334155');
      line.setAttribute('stroke-width', '1.5');
      line.setAttribute('stroke-dasharray', edge.rel === 'IMPORTS' ? '4,4' : 'none');
      edgeLayer.appendChild(line);
    }
  });

  // Render nodes and labels
  nodeMap.forEach(node => {
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', node.x);
    circle.setAttribute('cy', node.y);
    circle.setAttribute('r', node.type === 'Module' ? '14' : node.type === 'Class' ? '11' : '8');
    circle.setAttribute('fill', COLORS[node.type] || COLORS.Default);
    circle.setAttribute('stroke', '#1e293b');
    circle.setAttribute('stroke-width', '2');
    circle.style.cursor = 'pointer';

    circle.addEventListener('click', () => openDrawer(node));
    nodeLayer.appendChild(circle);

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', node.x);
    text.setAttribute('y', node.y + 16);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('fill', '#94a3b8');
    text.setAttribute('font-size', '10px');
    text.textContent = (node.name || node.title || node.path || '').slice(0, 18);
    labelLayer.appendChild(text);
  });
}

function openDrawer(node) {
  document.getElementById('drawer-title').textContent = node.name || node.title || 'Symbol';
  document.getElementById('drawer-kind').textContent = node.type || 'Unknown';
  document.getElementById('drawer-file').textContent = node.file_path || node.path || '(root)';
  document.getElementById('drawer-sig').querySelector('code').textContent = node.signature || node.name || '';
  document.getElementById('drawer-doc').textContent = node.docstring || node.description || 'No docstring available.';
  document.getElementById('drawer').classList.add('open');
}

document.getElementById('close-drawer').addEventListener('click', () => {
  document.getElementById('drawer').classList.remove('open');
});

// Search input
document.getElementById('search-input').addEventListener('input', (e) => {
  const query = e.target.value.toLowerCase();
  const circles = document.querySelectorAll('#node-layer circle');
  const texts = document.querySelectorAll('#label-layer text');

  graphData.nodes.forEach((n, idx) => {
    const match = (n.name || n.path || '').toLowerCase().includes(query);
    if (circles[idx]) circles[idx].style.opacity = match ? '1' : '0.2';
    if (texts[idx]) texts[idx].style.opacity = match ? '1' : '0.2';
  });
});

// Type filters
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeFilter = btn.dataset.type;
    renderGraph();
  });
});

// Zoom / Pan handlers
function updateTransform() {
  document.getElementById('viewport').setAttribute('transform', `translate(${panX}, ${panY}) scale(${zoomLevel})`);
}
document.getElementById('zoom-in').addEventListener('click', () => { zoomLevel *= 1.2; updateTransform(); });
document.getElementById('zoom-out').addEventListener('click', () => { zoomLevel /= 1.2; updateTransform(); });
document.getElementById('reset-view').addEventListener('click', () => { zoomLevel = 1; panX = 0; panY = 0; updateTransform(); });

const svg = document.getElementById('graph-canvas');
svg.addEventListener('mousedown', (e) => { isPanning = true; startX = e.clientX - panX; startY = e.clientY - panY; });
window.addEventListener('mousemove', (e) => { if (isPanning) { panX = e.clientX - startX; panY = e.clientY - startY; updateTransform(); } });
window.addEventListener('mouseup', () => { isPanning = false; });
</script>
</body>
</html>
"""

def get_mindmap_app_html() -> str:
    """Return the self-contained HTML for the Mindmap Graph MCP App."""
    return MINDMAP_APP_HTML

