"""Mermaid diagram renderer with zoom, pan, and click-to-view."""

from __future__ import annotations

import streamlit.components.v1 as components

MERMAID_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0D0D0F; overflow: hidden; }

  .controls {
    position: fixed; top: 8px; right: 12px; z-index: 100;
    display: flex; gap: 4px;
  }
  .controls button {
    background: #1a1a1f; border: 1px solid #333; color: #e0e0e0;
    padding: 4px 10px; cursor: pointer; border-radius: 4px; font-size: 13px;
    transition: background 0.15s;
  }
  .controls button:hover { background: #2a2a2f; }

  .zoom-info {
    position: fixed; bottom: 8px; right: 12px; z-index: 100;
    color: #666; font-size: 11px; font-family: monospace;
  }

  #container {
    width: 100%; height: 100vh; overflow: hidden; cursor: grab;
    position: relative;
  }
  #container.dragging { cursor: grabbing; }

  #svg-wrap {
    transform-origin: 0 0;
    position: absolute;
    padding: 20px;
  }

  /* Prevent text cutoff in nodes */
  .node rect, .node polygon, .node circle, .node .label-container {
    min-width: 160px !important;
  }
  .nodeLabel { white-space: pre-wrap !important; text-align: center; }
  .edgeLabel { font-size: 12px !important; }

  .node:hover rect, .node:hover polygon {
    filter: brightness(1.15);
    transition: filter 0.15s;
  }
</style>
</head>
<body>

<div class="controls">
  <button onclick="zoomIn()" title="Zoom in">+</button>
  <button onclick="zoomOut()" title="Zoom out">&minus;</button>
  <button onclick="fitToView()" title="Fit diagram to view">Fit</button>
  <button onclick="resetView()" title="Reset zoom and position">Reset</button>
</div>
<div class="zoom-info" id="zoom-info">100%</div>

<div id="container">
  <div id="svg-wrap">
    <pre class="mermaid">
MERMAID_PLACEHOLDER
    </pre>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
(function() {
  var container = document.getElementById('container');
  var wrap = document.getElementById('svg-wrap');
  var zoomInfo = document.getElementById('zoom-info');

  var scale = 1;
  var panX = 0, panY = 0;
  var isDragging = false;
  var startX, startY, startPanX, startPanY;
  var svg = null;

  function updateTransform() {
    wrap.style.transform = 'translate(' + panX + 'px, ' + panY + 'px) scale(' + scale + ')';
    zoomInfo.textContent = Math.round(scale * 100) + '%';
  }

  // Zoom controls — assigned to window so onclick="" attributes work
  window.zoomIn = function() { scale = Math.min(scale * 1.25, 5); updateTransform(); };
  window.zoomOut = function() { scale = Math.max(scale / 1.25, 0.1); updateTransform(); };
  window.resetView = function() { scale = 1; panX = 0; panY = 0; updateTransform(); };
  window.fitToView = function() {
    if (!svg) return;
    var svgRect = svg.getBoundingClientRect();
    var contRect = container.getBoundingClientRect();
    var scaleX = contRect.width / (svgRect.width / scale + 40);
    var scaleY = contRect.height / (svgRect.height / scale + 40);
    scale = Math.min(scaleX, scaleY, 1.5);
    panX = 0;
    panY = 0;
    updateTransform();
  };

  // Pan via mouse drag
  container.addEventListener('mousedown', function(e) {
    if (e.button !== 0) return;
    isDragging = true;
    startX = e.clientX; startY = e.clientY;
    startPanX = panX; startPanY = panY;
    container.classList.add('dragging');
    e.preventDefault();
  });

  window.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    panX = startPanX + (e.clientX - startX);
    panY = startPanY + (e.clientY - startY);
    updateTransform();
  });

  window.addEventListener('mouseup', function() {
    isDragging = false;
    container.classList.remove('dragging');
  });

  // Zoom with scroll wheel
  container.addEventListener('wheel', function(e) {
    e.preventDefault();
    var delta = e.deltaY > 0 ? 0.9 : 1.1;
    scale = Math.max(0.1, Math.min(5, scale * delta));
    updateTransform();
  }, { passive: false });

  // Prevent Mermaid link clicks from navigating the iframe away
  document.addEventListener('click', function(e) {
    var el = e.target;
    while (el && el !== document) {
      if (el.tagName === 'A' || el.tagName === 'a') {
        e.preventDefault();
        return;
      }
      el = el.parentNode;
    }
  });

  // Initialize Mermaid and set up after render
  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    securityLevel: 'loose',
    flowchart: {
      htmlLabels: true,
      curve: 'basis',
      nodeSpacing: 30,
      rankSpacing: 50,
      wrappingWidth: 200,
      useMaxWidth: false
    },
    themeVariables: {
      primaryColor: '#2d5a3d',
      primaryTextColor: '#e0e0e0',
      primaryBorderColor: '#5dcaa5',
      lineColor: '#555',
      secondaryColor: '#2d3d5a',
      tertiaryColor: '#1a1a1f',
      background: '#0D0D0F',
      mainBkg: '#1a1a1f',
      nodeBorder: '#555',
      clusterBkg: '#111115',
      clusterBorder: '#333',
      titleColor: '#e0e0e0',
      edgeLabelBackground: '#0D0D0F'
    }
  });

  mermaid.run().then(function() {
    svg = wrap.querySelector('svg');
    if (svg) {
      try {
        var bbox = svg.getBBox();
        var h = Math.max((bbox.height + 80) * scale, 400);
        window.parent.postMessage({
          type: 'streamlit:setFrameHeight',
          height: Math.min(h, 2000)
        }, '*');
      } catch(e) {}
      setTimeout(function() { window.fitToView(); }, 150);
    }
  });
})();
</script>
</body>
</html>"""


def render_mermaid(mermaid_str: str, height: int = 600, key: str = "diagram") -> None:
    """Render a Mermaid diagram with zoom/pan controls."""
    html = MERMAID_HTML.replace("MERMAID_PLACEHOLDER", mermaid_str)
    components.html(html, height=height, scrolling=False)
