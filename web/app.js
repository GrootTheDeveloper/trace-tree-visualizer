let currentAnalysis = null;
let selected = { cell: null, event: null, line: null, previousLine: null, finding: null };
let currentStep = 0;
let playTimer = null;
let playbackDelayMs = 1000;
let selectedTreeId = null;
let selectedFocusField = "Auto";

const $ = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function discoverAndPopulateFields(analysis) {
  const selector = $("fieldFocusSelector");
  if (!selector) return;
  
  const steps = analysis.tree_timeline?.steps || [];
  const discoveredKeys = new Set();
  const ignoredKeys = ["id", "idx", "l", "r", "lo", "hi", "mid", "pos", "index", "u", "v", "ql", "qr", "n"];
  
  for (const step of steps) {
    const states = step.states || {};
    for (const cellId of Object.keys(states)) {
      const fields = states[cellId]?.fields || {};
      for (const key of Object.keys(fields)) {
        if (!ignoredKeys.includes(key)) {
          discoveredKeys.add(key);
        }
      }
    }
  }
  
  // Standard preset keys as fallbacks
  const presets = ["sum", "mn", "mx", "lazy", "count"];
  for (const p of presets) {
    discoveredKeys.add(p);
  }
  
  const currentVal = selector.value || "Auto";
  
  selector.innerHTML = `<option value="Auto">Auto</option>` +
    Array.from(discoveredKeys).map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join("");
    
  if (Array.from(discoveredKeys).includes(currentVal) || currentVal === "Auto") {
    selector.value = currentVal;
  } else {
    selector.value = "Auto";
  }
  selectedFocusField = selector.value;
}

function loadAnalysis(analysis) {
  currentAnalysis = analysis;
  selected = { cell: null, event: null, line: null, previousLine: null, finding: null };
  selectedTreeId = defaultTreeId(analysis);
  const steps = analysis.tree_timeline?.steps || [];
  currentStep = steps.length ? steps.length - 1 : 0;
  
  discoverAndPopulateFields(analysis);
  
  renderSummary(analysis);
  renderTree(analysis);
  renderSource(analysis);
  renderTimeline(analysis);
  renderFindingsClean(analysis);
  renderInspector();
  
  // Auto collapse findings panel if 0 actionable findings
  const findings = analysis.findings || [];
  const actionable = findings.filter(isActionableFinding).length;
  const findingsPanel = $("findingsPanel");
  if (findingsPanel) {
    if (actionable === 0) {
      findingsPanel.classList.add("collapsed");
    } else {
      findingsPanel.classList.remove("collapsed");
    }
  }
  
  if (typeof setPipelineStep === "function") {
    setPipelineStep("code", "done");
    setPipelineStep("instrument", "done");
    setPipelineStep("run", "done");
    setPipelineStep("analyze", "done");
    setPipelineStep("visualize", "active");
  }
}

function showMessage(message) {
  const runStatus = $("runStatus");
  if (runStatus) {
    runStatus.textContent = message;
    runStatus.className = "run-status";
  }
}

function renderSummary(analysis) {
  const summary = analysis.summary || {};
  const findings = analysis.findings || [];
  const computedActionable = findings.filter(isActionableFinding).length;
  const actionable = summary.actionable_finding_count ?? computedActionable;

  $("statOps").textContent = summary.operation_count || 0;
  $("statFindings").textContent = actionable;
  $("statSteps").textContent = summary.timeline_step_count || 0;
  $("statNodes").textContent = summary.graph_node_count || 0;

  const findingsBadge = $("badgeFindings");
  if (findingsBadge) {
    findingsBadge.classList.toggle("has-findings", actionable > 0);
  }
}

function graphParts(analysis) {
  const graph = analysis.graph || {};
  return {
    nodes: graph.nodes || [],
    edges: graph.edges || [],
  };
}

function timelineParts(analysis = currentAnalysis) {
  const timeline = analysis?.tree_timeline || {};
  const steps = timeline.steps || [];
  const step = steps[Math.max(0, Math.min(currentStep, steps.length - 1))] || null;
  return { timeline, steps, step };
}

function flashTimeReadout() {
  const readout = document.querySelector(".time-readout");
  if (!readout) return;
  readout.classList.add("stepping");
  setTimeout(() => readout.classList.remove("stepping"), 200);
}

function setCurrentStep(nextStep, autoSelect = true) {
  setCurrentStepInternal(nextStep, autoSelect, true);
}

function setCurrentStepInternal(nextStep, autoSelect = true, refreshTimeline = true) {
  if (!currentAnalysis) return;
  const { steps } = timelineParts(currentAnalysis);
  if (!steps.length) return;
  currentStep = Math.max(0, Math.min(Number(nextStep) || 0, steps.length - 1));
  const step = steps[currentStep];
  if (autoSelect) {
    selected.finding = null;
    selected.cell = step.node_id || selected.cell;
    selectedTreeId = treeIdForCell(currentAnalysis, selected.cell) || selectedTreeId;
    selected.event = step.seq ? (graphNode(`event:${step.seq}`) ? `event:${step.seq}` : (graphNode(`watch:${step.seq}`) ? `watch:${step.seq}` : null)) : null;
    selected.line = step.line || null;
    selected.previousLine = previousTimelineLine(currentAnalysis, currentStep, selected.line);
  }
  renderTree(currentAnalysis);
  if (refreshTimeline) {
    renderTimeline(currentAnalysis);
  } else {
    updateTimelinePanel(currentAnalysis);
  }
  applySelection(false);
  flashTimeReadout();
}

function previousTimelineLine(analysis, stepIndex, currentLine = null) {
  const steps = analysis?.tree_timeline?.steps || [];
  for (let index = Number(stepIndex) - 1; index >= 0; index -= 1) {
    const line = Number(steps[index]?.line || 0);
    if (line > 0 && line !== Number(currentLine || 0)) return line;
  }
  return null;
}

function togglePlayback() {
  if (playTimer) {
    clearInterval(playTimer);
    playTimer = null;
    renderTimeline(currentAnalysis);
    return;
  }
  const { steps } = timelineParts(currentAnalysis);
  if (!steps.length) return;
  if (currentStep >= steps.length - 1) currentStep = 0;
  playTimer = setInterval(() => {
    if (currentStep >= steps.length - 1) {
      clearInterval(playTimer);
      playTimer = null;
      renderTimeline(currentAnalysis);
      return;
    }
    setCurrentStepInternal(currentStep + 1, true, false);
  }, playbackDelayMs);
  renderTimeline(currentAnalysis);
}

function setPlaybackSpeed(delayMs) {
  const nextDelay = Number(delayMs);
  if (!Number.isFinite(nextDelay) || nextDelay <= 0) return;
  const wasPlaying = Boolean(playTimer);
  if (playTimer) {
    clearInterval(playTimer);
    playTimer = null;
  }
  playbackDelayMs = nextDelay;
  renderTimeline(currentAnalysis);
  if (wasPlaying) {
    togglePlayback();
  }
}

function setPlaybackSpeedSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return;
  setPlaybackSpeed(Math.round(seconds * 1000));
}

function speedSecondsValue() {
  const seconds = playbackDelayMs / 1000;
  return Number.isInteger(seconds) ? String(seconds) : seconds.toFixed(1);
}

function svgEl(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, String(value));
  }
  return element;
}

function numericIndex(cell) {
  const value = Number(cell.attributes?.index ?? cell.id.split(":").pop());
  return Number.isFinite(value) ? value : 0;
}

function coverageForCell(cell, coverByCell, treeEdges = []) {
  const cover = coverByCell.get(cell.id);
  if (cover?.left !== undefined && cover?.right !== undefined) {
    return { left: Number(cover.left), right: Number(cover.right) };
  }
  let currentId = cell.id;
  while (true) {
    const parentEdge = treeEdges.find(e => e.target === currentId);
    if (!parentEdge) break;
    currentId = parentEdge.source;
    const pCover = coverByCell.get(currentId);
    if (pCover?.left !== undefined && pCover?.right !== undefined) {
      return { left: Number(pCover.left), right: Number(pCover.right) };
    }
  }
  const index = numericIndex(cell);
  return { left: index, right: index };
}

function uniqueTreeEdges(edges) {
  const seen = new Set();
  const result = [];
  for (const edge of edges) {
    const key = `${edge.source}->${edge.target}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(edge);
  }
  return result;
}

function derivedCoverageEdges(cells, coverByCell) {
  const rows = cells.map((cell) => ({ cell, cover: coverageForCell(cell, coverByCell) }));
  const edges = [];
  for (const child of rows) {
    const childSize = child.cover.right - child.cover.left + 1;
    let parent = null;
    for (const candidate of rows) {
      if (candidate.cell.id === child.cell.id) continue;
      const candidateSize = candidate.cover.right - candidate.cover.left + 1;
      const contains =
        candidate.cover.left <= child.cover.left &&
        candidate.cover.right >= child.cover.right &&
        candidateSize > childSize;
      if (!contains) continue;
      if (!parent || candidateSize < parent.size) {
        parent = { cell: candidate.cell, size: candidateSize };
      }
    }
    if (parent) {
      edges.push({ source: parent.cell.id, target: child.cell.id, kind: "derived_tree_link", attributes: {} });
    }
  }
  return uniqueTreeEdges(edges);
}

function treeDepths(cells, treeEdges) {
  const children = new Map();
  const hasParent = new Set();
  for (const edge of treeEdges) {
    if (!children.has(edge.source)) children.set(edge.source, []);
    children.get(edge.source).push(edge.target);
    hasParent.add(edge.target);
  }

  const roots = cells
    .filter((cell) => !hasParent.has(cell.id))
    .sort((a, b) => numericIndex(a) - numericIndex(b));
  const depthById = new Map();
  const queue = roots.map((cell) => ({ id: cell.id, depth: 0 }));
  while (queue.length) {
    const item = queue.shift();
    if (!item || depthById.has(item.id)) continue;
    depthById.set(item.id, item.depth);
    for (const child of children.get(item.id) || []) {
      queue.push({ id: child, depth: item.depth + 1 });
    }
  }

  for (const cell of cells) {
    if (!depthById.has(cell.id)) depthById.set(cell.id, 0);
  }
  return depthById;
}

function renderTimelineTree(analysis, svg) {
  const { timeline, step } = timelineParts(analysis);
  const allNodes = timeline.nodes || [];
  const allEdges = timeline.edges || [];
  const activeInstance = activeTreeInstance(analysis);
  const activeTreeArray = activeInstance?.array || "";
  const activeTreeId = activeInstance?.tree_id || activeTreeArray || selectedTreeId;
  const nodes = activeTreeId
    ? allNodes.filter((node) => (node.tree_id || node.array) === activeTreeId || node.array === activeTreeArray)
    : allNodes;
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = allEdges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
  const states = step?.states || {};
  const activeNodes = step?.active_nodes || [];
  const activeNodeSet = new Set(activeNodes);
  const activeEdgeSet = activePathEdges(activeNodes);
  const visibleNodes = nodes.filter(
    (node) => $("showSynthesized").checked || states[node.id]?.created || activeNodeSet.has(node.id) || step?.node_id === node.id,
  );
  
  if (!nodes.length) {
    svg.setAttribute("viewBox", "0 0 900 520");
    const message = svgEl("text", { x: 40, y: 70, class: "tree-empty" });
    message.textContent = "Move the timeline slider or run a sample to create tree nodes.";
    svg.appendChild(message);
    return;
  }

  // Calculate static layout dimensions using all nodes and edges
  const depthById = timelineDepths(nodes, edges);
  
  // Fix ghost node ranges (nodes generated out of bounds) dynamically
  const rangeById = new Map();
  for (const node of nodes) {
    rangeById.set(node.id, node.range ? [...node.range] : [node.index, node.index]);
  }
  let changed = true;
  while (changed) {
    changed = false;
    for (const edge of edges) {
      const pRange = rangeById.get(edge.source);
      const cRange = rangeById.get(edge.target);
      if (pRange && cRange && Number(pRange[0]) === Number(pRange[1])) {
        if (Number(cRange[0]) !== Number(pRange[0]) || Number(cRange[1]) !== Number(pRange[1])) {
          rangeById.set(edge.target, [...pRange]);
          changed = true;
        }
      }
    }
  }

  const ranges = nodes.map((node) => rangeById.get(node.id));
  const minLeft = Math.min(...ranges.map((range) => Number(range[0])));
  const maxRight = Math.max(...ranges.map((range) => Number(range[1])));
  const maxDepth = Math.max(...depthById.values());
  const isSegmentTimeline = nodes.some((node) => node.kind === "segment_tree");
  const treeArray = activeTreeArray || nodes.find((node) => node.kind === "segment_tree")?.array || "";
  const baseInfo = (timeline.base_arrays || []).find((item) => item.source_tree === treeArray) || null;
  const baseArrayName = baseInfo?.array || "";
  const baseStates = step?.base_states || {};
  const currentFrameRange = currentSegmentFrameRange(step);
  const queryFrameRange = currentQueryRange(step);
  const updatePosition = currentUpdatePosition(step);
  const baseRowHeight = isSegmentTimeline ? 86 : 0;
  const width = Math.max(900, (maxRight - minLeft + 1) * 95 + 180);
  const height = Math.max(520 + baseRowHeight, maxDepth * 118 + 190 + baseRowHeight);
  
  const leftPad = 90;
  const rightPad = 90;
  const topPad = 96;
  const treeAreaHeight = height - baseRowHeight;
  const depthStep = maxDepth > 0 ? Math.min(118, (treeAreaHeight - 190) / maxDepth) : 95;
  const rangeWidth = Math.max(1, maxRight - minLeft);
  const xFor = (value) => leftPad + ((value - minLeft) / rangeWidth) * (width - leftPad - rightPad);
  const cellStep = (width - leftPad - rightPad) / Math.max(1, maxRight - minLeft);
  const cellHalfWidth = Math.min(34, Math.max(18, cellStep * 0.32));

  const position = new Map();
  for (const node of nodes) {
    const range = rangeById.get(node.id);
    const left = Number(range[0]);
    const right = Number(range[1]);
    const center = (Number(range[0]) + Number(range[1])) / 2;
    position.set(node.id, {
      x: xFor(center),
      y: topPad + (depthById.get(node.id) || 0) * depthStep,
      range,
      x1: xFor(left) - cellHalfWidth,
      x2: xFor(right) + cellHalfWidth,
    });
  }

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const title = svgEl("text", { x: 22, y: 28, class: "tree-caption" });
  title.textContent = `${treeArray ? `Tree ${treeArray} - ` : ""}Step ${currentStep} / ${(timeline.steps || []).length - 1} - seq ${step?.seq ?? 0}`;
  svg.appendChild(title);

  const baseCellY = isSegmentTimeline ? height - 38 : null;
  const baseCells = [];
  if (isSegmentTimeline && baseCellY !== null) {
    const leafByIndex = new Map();
    for (const node of nodes) {
      const range = node.range || [node.index, node.index];
      const left = Number(range[0]);
      const right = Number(range[1]);
      if (Number.isFinite(left) && left === right) {
        leafByIndex.set(left, node);
      }
    }
    for (let index = minLeft; index <= maxRight; index += 1) {
      const leaf = leafByIndex.get(index);
      const state = leaf ? states[leaf.id] || {} : {};
      const baseState = baseArrayName ? baseStates[`base:${baseArrayName}:${index}`] || {} : {};
      baseCells.push({
        index,
        leaf,
        x: xFor(index),
        observed: Boolean(baseState.created || baseState.observed || (!baseArrayName && (state.created || state.observed))),
        inFrameRange: Boolean(currentFrameRange && index >= currentFrameRange.left && index <= currentFrameRange.right),
        inQueryRange: Boolean(queryFrameRange && index >= queryFrameRange.left && index <= queryFrameRange.right),
        atUpdatePos: Number.isFinite(updatePosition) && index === updatePosition,
        active: Boolean(leaf && activeNodeSet.has(leaf.id)),
        current: Boolean(leaf && step?.node_id === leaf.id),
      });
    }
  }

  const drawBaseArrayCells = () => {
    if (!baseCells.length || baseCellY === null) return;
    const label = svgEl("text", { x: 22, y: baseCellY + 5, class: "base-array-label" });
    label.textContent = baseArrayName ? `base array ${baseArrayName}` : "logical leaves";
    svg.appendChild(label);

    for (const cell of baseCells) {
      const group = svgEl("g");
      group.setAttribute(
        "class",
        `base-cell ${cell.observed ? "observed" : ""} ${cell.inFrameRange ? "in-frame-range" : ""} ${cell.inQueryRange ? "in-query-range" : ""} ${cell.atUpdatePos ? "at-update-pos" : ""} ${cell.active ? "path-active" : ""} ${cell.current ? "active" : ""}`,
      );
      if (cell.leaf) {
        group.dataset.cellId = cell.leaf.id;
        group.addEventListener("click", () => selectCell(cell.leaf.id));
      }
      group.appendChild(svgEl("rect", { x: cell.x - cellHalfWidth, y: baseCellY - 16, width: cellHalfWidth * 2, height: 32, rx: 6 }));
      const indexLabel = svgEl("text", { x: cell.x, y: baseCellY + 4, class: "base-index" });
      indexLabel.textContent = `[${cell.index}]`;
      group.appendChild(indexLabel);
      svg.appendChild(group);
    }
  };

  // Draw axis (using static minLeft / maxRight)
  const axisY = isSegmentTimeline ? height - 94 : height - 38;
  svg.appendChild(svgEl("line", { x1: leftPad, y1: axisY, x2: width - rightPad, y2: axisY, class: "tree-axis" }));
  for (let i = minLeft; i <= maxRight; i += 1) {
    const x = xFor(i);
    svg.appendChild(svgEl("line", { x1: x, y1: axisY - 5, x2: x, y2: axisY + 5, class: "tree-axis" }));
    const label = svgEl("text", { x, y: axisY + 22, class: "tree-axis-label" });
    label.textContent = i;
    svg.appendChild(label);
  }

  if (isSegmentTimeline) {
    drawTimelineRangeBand(svg, currentFrameRange, {
      y: axisY - 34,
      xFor,
      minLeft,
      maxRight,
      cellHalfWidth,
      className: "frame-range-band",
      label: "current",
    });
    drawTimelineRangeBand(svg, queryFrameRange, {
      y: axisY - 58,
      xFor,
      minLeft,
      maxRight,
      cellHalfWidth,
      className: "query-range-band",
      label: "query",
    });
    drawTimelinePositionPin(svg, updatePosition, {
      yTop: axisY - 66,
      yBottom: baseCellY ? baseCellY + 24 : axisY + 18,
      xFor,
      minLeft,
      maxRight,
      label: "pos",
    });
  }

  if (!visibleNodes.length) {
    drawBaseArrayCells();
    return;
  }
  const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));

  if (baseCells.length && baseCellY !== null) {
    for (const cell of baseCells) {
      if (!cell.leaf || !visibleNodeIds.has(cell.leaf.id)) continue;
      const leafPos = position.get(cell.leaf.id);
      if (!leafPos) continue;
      
      svg.appendChild(svgEl("line", {
        x1: leafPos.x,
        y1: leafPos.y + 23,
        x2: cell.x,
        y2: baseCellY - 22,
        class: `base-link ${cell.active ? "path-active" : ""} ${cell.current ? "active" : ""}`,
      }));
    }
    drawBaseArrayCells();
  }

  // Draw range bars for visible nodes
  for (const node of visibleNodes) {
    const pos = position.get(node.id);
    if (!pos) continue;
    const state = states[node.id] || {};
    const halfH = 23;
    const modelOnly = Boolean(node.synthesized && !state.observed && !state.created);
    svg.appendChild(svgEl("line", {
      x1: xFor(pos.range[0]),
      y1: pos.y + halfH + 6,
      x2: xFor(pos.range[1]),
      y2: pos.y + halfH + 6,
      class: `range-bar ${modelOnly ? "synthesized" : ""} ${activeNodeSet.has(node.id) ? "path-active" : ""} ${step?.node_id === node.id ? "active" : ""}`,
      "data-cell-id": node.id,
    }));
  }

  // Draw edges between visible nodes
  const visibleEdges = edges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));
  for (const edge of visibleEdges) {
    const a = position.get(edge.source);
    const b = position.get(edge.target);
    if (!a || !b) continue;
    
    const halfHA = 23;
    const halfHB = 23;

    svg.appendChild(svgEl("path", {
      d: `M ${a.x} ${a.y + halfHA} C ${a.x} ${(a.y + b.y) / 2}, ${b.x} ${(a.y + b.y) / 2}, ${b.x} ${b.y - halfHB}`,
      class: `tree-edge ${activeEdgeSet.has(`${edge.source}->${edge.target}`) ? "path-active" : ""}`,
    }));
  }

  // Draw visible nodes
  for (const node of visibleNodes.sort((a, b) => Number(a.index) - Number(b.index))) {
    const pos = position.get(node.id);
    if (!pos) continue;
    const state = states[node.id] || {};
    const created = Boolean(state.created);
    const observed = Boolean(state.observed);
    const modelOnly = Boolean(node.synthesized && !observed && !created);
    const group = svgEl("g");
    group.setAttribute(
      "class",
      `tree-node ${modelOnly ? "synthesized" : ""} ${created ? "created" : observed ? "observed-read" : "not-created"} ${activeNodeSet.has(node.id) ? "path-active" : ""} ${step?.node_id === node.id ? "active" : ""}`,
    );
    group.dataset.cellId = node.id;
    group.addEventListener("click", () => selectCell(node.id));
    group.addEventListener("mouseenter", (e) => showNodeTooltip(e, node.id, state));
    group.addEventListener("mouseleave", hideNodeTooltip);
    group.addEventListener("mousemove", moveNodeTooltip);

    const title = svgEl("title");
    title.textContent = modelOnly ? "Model-only node: not reached in trace yet" : "Trace node";
    group.appendChild(title);
    
    const cardW = Math.max(54, pos.x2 - pos.x1);
    const cardH = 46;
    const rx = 7;
    const halfH = cardH / 2;
    const cardX = pos.x - cardW / 2;
    
    // Draw card rounded rect
    group.appendChild(svgEl("rect", {
      x: cardX,
      y: pos.y - halfH,
      width: cardW,
      height: cardH,
      rx: rx,
      class: "node-box"
    }));

    const labelInset = Math.min(12, Math.max(7, cardW * 0.06));
    const indexY = pos.y - 3;
    const rangeY = pos.y + 13;
    const label = svgEl("text", { x: cardX + labelInset, y: indexY, class: "node-index" });
    label.textContent = `st[${node.index}]`;
    group.appendChild(label);
    
    const rangeLabel = svgEl("text", { x: cardX + cardW - labelInset, y: rangeY, class: "node-range" });
    rangeLabel.textContent = `[${pos.range[0]},${pos.range[1]}]`;
    group.appendChild(rangeLabel);
    
    svg.appendChild(group);
  }
}

function treeInstances(analysis = currentAnalysis) {
  const timeline = analysis?.tree_timeline || {};
  const configured = timeline.tree_instances || [];
  if (configured.length) return configured;
  const seen = new Set();
  const inferred = [];
  for (const node of timeline.nodes || []) {
    if (node.kind !== "segment_tree") continue;
    const id = node.tree_id || node.array;
    if (seen.has(id)) continue;
    seen.add(id);
    inferred.push({ tree_id: id, array: node.array, kind: "segment_tree", base_array: "" });
  }
  return inferred;
}

function defaultTreeId(analysis = currentAnalysis) {
  const first = treeInstances(analysis)[0];
  return first?.tree_id || first?.array || null;
}

function activeTreeInstance(analysis = currentAnalysis) {
  const instances = treeInstances(analysis);
  if (!instances.length) return null;
  return instances.find((item) => (item.tree_id || item.array) === selectedTreeId) || instances[0];
}

function treeIdForCell(analysis, cellId) {
  if (!cellId) return null;
  const node = (analysis?.tree_timeline?.nodes || []).find((item) => item.id === cellId);
  return node ? node.tree_id || node.array || null : null;
}

function renderTreeSelector(analysis) {
  const container = $("treeSelector");
  if (!container) return;
  const instances = treeInstances(analysis);
  if (instances.length <= 1) {
    container.innerHTML = "";
    return;
  }
  if (!selectedTreeId || !instances.some((item) => (item.tree_id || item.array) === selectedTreeId)) {
    selectedTreeId = instances[0].tree_id || instances[0].array;
  }
  container.innerHTML = instances
    .map((item) => {
      const id = item.tree_id || item.array;
      const label = item.base_array ? `${item.array} <- ${item.base_array}` : item.array;
      return `<button type="button" class="tree-tab ${id === selectedTreeId ? "active" : ""}" data-tree-id="${escapeHtml(id)}">${escapeHtml(label)}</button>`;
    })
    .join("");
  for (const button of container.querySelectorAll("[data-tree-id]")) {
    button.addEventListener("click", () => {
      selectedTreeId = button.dataset.treeId;
      renderTree(currentAnalysis);
      renderInspector();
      applySelection(false);
    });
  }
}

function displayNodeValue(state, cellId = null) {
  const fields = state?.fields || {};
  const entries = Object.entries(fields).filter(([, value]) => value !== undefined && value !== null && String(value) !== "");
  
  const rawValue = state?.value !== undefined ? state.value : (state?.read_value !== undefined ? state.read_value : "");
  if ((rawValue === "<object>" || (typeof rawValue === "string" && rawValue.startsWith("{"))) && entries.length === 0) {
    return "uncaptured";
  }
  
  const formatFieldVal = (k, v) => `${k}=${v}`;
  
  if (selectedFocusField !== "Auto") {
    if (fields[selectedFocusField] !== undefined && fields[selectedFocusField] !== null) {
      return formatFieldVal(selectedFocusField, fields[selectedFocusField]);
    }
    if (selectedFocusField === "value" && state?.value !== undefined) return `v=${state.value}`;
    if (selectedFocusField === "read_value" && state?.read_value !== undefined) return `r=${state.read_value}`;
    return "";
  }
  
  if (cellId && currentAnalysis) {
    const compFields = getNodeFieldsForComparison(cellId, state, currentStep - 1);
    const changed = compFields.filter(f => f.changed);
    if (changed.length === 1) {
      return formatFieldVal(changed[0].name, changed[0].value);
    } else if (changed.length > 1) {
      const preferred = ["sum", "value", "val", "mx", "max", "mn", "min", "cnt", "count", "best", "pref", "suff", "lazy", "tag"];
      const picked = changed.find(f => preferred.includes(f.name)) || changed[0];
      return formatFieldVal(picked.name, picked.value);
    }
  }
  
  if (state?.created && state.value !== undefined) return `v=${state.value}`;
  if (state?.observed && state.read_value !== undefined) return `r=${state.read_value}`;
  
  if (entries.length) {
    const preferred = ["sum", "value", "val", "mx", "max", "mn", "min", "cnt", "count", "best", "pref", "suff", "lazy", "tag"];
    const picked = preferred
      .map((name) => entries.find(([field]) => field === name))
      .find(Boolean) || entries.find(([field]) => !["id", "idx", "l", "r", "lo", "hi", "mid", "pos", "index", "u", "v", "ql", "qr", "n"].includes(field)) || entries[0];
    return formatFieldVal(picked[0], picked[1]);
  }
  return "";
}

function currentSegmentFrameRange(step) {
  const frames = [...(step?.call_stack || [])].reverse();
  for (const frame of frames) {
    const range = normalizeRange(frame.range);
    if (range) return range;
  }
  return normalizeRange(step?.mutation?.range);
}

function currentQueryRange(step) {
  const frames = [...(step?.call_stack || [])].reverse();
  for (const frame of frames) {
    const params = frame.params || {};
    const range = normalizeRange([params.ql, params.qr]);
    if (range) return range;
  }
  return null;
}

function currentUpdatePosition(step) {
  const frames = [...(step?.call_stack || [])].reverse();
  for (const frame of frames) {
    const params = frame.params || {};
    if (params.pos === undefined || params.pos === "") continue;
    const pos = Number(params.pos);
    if (Number.isFinite(pos)) return pos;
  }
  return null;
}

function normalizeRange(range) {
  if (!Array.isArray(range) || range.length < 2) return null;
  const left = Number(range[0]);
  const right = Number(range[1]);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return null;
  return { left: Math.min(left, right), right: Math.max(left, right) };
}

function drawTimelineRangeBand(svg, range, options) {
  if (!range) return;
  const clippedLeft = Math.max(options.minLeft, range.left);
  const clippedRight = Math.min(options.maxRight, range.right);
  if (clippedLeft > clippedRight) return;
  const x1 = options.xFor(clippedLeft) - options.cellHalfWidth;
  const x2 = options.xFor(clippedRight) + options.cellHalfWidth;
  const width = Math.max(8, x2 - x1);
  const group = svgEl("g", { class: `timeline-range ${options.className}` });
  const title = svgEl("title");
  title.textContent = `${options.label} [${range.left},${range.right}]`;
  group.appendChild(title);
  group.appendChild(svgEl("rect", { x: x1, y: options.y, width, height: 16, rx: 8 }));
  const label = svgEl("text", { x: x1 + width / 2, y: options.y + 12, class: "range-band-label" });
  label.textContent = `${options.label} [${range.left},${range.right}]`;
  group.appendChild(label);
  const leftLabel = svgEl("text", { x: x1, y: options.y - 4, class: "range-end-label" });
  leftLabel.textContent = `L=${range.left}`;
  group.appendChild(leftLabel);
  const rightLabel = svgEl("text", { x: x2, y: options.y - 4, class: "range-end-label right" });
  rightLabel.textContent = `R=${range.right}`;
  group.appendChild(rightLabel);
  svg.appendChild(group);
}

function drawTimelinePositionPin(svg, position, options) {
  if (!Number.isFinite(position) || position < options.minLeft || position > options.maxRight) return;
  const x = options.xFor(position);
  const group = svgEl("g", { class: "timeline-pos-pin" });
  const title = svgEl("title");
  title.textContent = `${options.label} ${position}`;
  group.appendChild(title);
  group.appendChild(svgEl("line", { x1: x, y1: options.yTop, x2: x, y2: options.yBottom }));
  group.appendChild(svgEl("circle", { cx: x, cy: options.yTop, r: 5 }));
  const label = svgEl("text", { x, y: options.yTop - 8 });
  label.textContent = `${options.label}=${position}`;
  group.appendChild(label);
  svg.appendChild(group);
}

function activePathEdges(activeNodes) {
  const edges = new Set();
  for (let index = 1; index < activeNodes.length; index += 1) {
    edges.add(`${activeNodes[index - 1]}->${activeNodes[index]}`);
  }
  return edges;
}

function timelineDepths(nodes, edges) {
  const children = new Map();
  const hasParent = new Set();
  for (const edge of edges) {
    if (!children.has(edge.source)) children.set(edge.source, []);
    children.get(edge.source).push(edge.target);
    hasParent.add(edge.target);
  }
  const roots = nodes.filter((node) => !hasParent.has(node.id)).sort((a, b) => Number(a.index) - Number(b.index));
  const depthById = new Map();
  const queue = roots.map((node) => ({ id: node.id, depth: 0 }));
  while (queue.length) {
    const item = queue.shift();
    if (!item || depthById.has(item.id)) continue;
    depthById.set(item.id, item.depth);
    for (const child of children.get(item.id) || []) queue.push({ id: child, depth: item.depth + 1 });
  }
  for (const node of nodes) {
    if (!depthById.has(node.id)) depthById.set(node.id, 0);
  }
  return depthById;
}

function renderTree(analysis) {
  const svg = $("treeSvg");
  svg.innerHTML = "";
  renderTreeSelector(analysis);
  if (analysis.tree_timeline?.steps?.length) {
    renderTimelineTree(analysis, svg);
    return;
  }
  const { nodes, edges } = graphParts(analysis);
  const showSynthesized = $("showSynthesized").checked;
  const allCells = nodes.filter((node) => node.label === "cell");
  const cells = allCells.filter((cell) => showSynthesized || eventEdgesForCell(analysis, cell.id).length);
  const coverByCell = new Map();
  for (const edge of edges.filter((edge) => edge.kind === "logical_cover")) {
    if (!coverByCell.has(edge.source)) {
      coverByCell.set(edge.source, edge.attributes || {});
    }
  }

  if (!cells.length) {
    svg.setAttribute("viewBox", "0 0 900 520");
    const message = svgEl("text", { x: 40, y: 70, class: "tree-empty" });
    message.textContent = "No tree cells found in this analysis.";
    svg.appendChild(message);
    return;
  }

  let treeEdges = uniqueTreeEdges(edges.filter((edge) => edge.kind === "tree_link"));
  treeEdges = treeEdges.filter((edge) => cells.some((cell) => cell.id === edge.source) && cells.some((cell) => cell.id === edge.target));
  const inferredTree = treeEdges.length === 0;
  if (inferredTree) {
    treeEdges = derivedCoverageEdges(cells, coverByCell);
  }

  const covers = cells.map((cell) => coverageForCell(cell, coverByCell, treeEdges));
  const minLeft = Math.min(...covers.map((cover) => cover.left));
  const maxRight = Math.max(...covers.map((cover) => cover.right));
  const depthById = treeDepths(cells, treeEdges);
  const maxDepth = Math.max(...depthById.values());
  const width = Math.max(900, (maxRight - minLeft + 1) * 92 + 180);
  const height = Math.max(520, maxDepth * 115 + 180);
  const leftPad = 90;
  const rightPad = 90;
  const topPad = 90;
  const depthStep = maxDepth > 0 ? Math.min(118, (height - 170) / maxDepth) : 95;
  const rangeWidth = Math.max(1, maxRight - minLeft);
  const xFor = (value) => leftPad + ((value - minLeft) / rangeWidth) * (width - leftPad - rightPad);
  const cellStep = (width - leftPad - rightPad) / Math.max(1, maxRight - minLeft);
  const cellHalfWidth = Math.min(34, Math.max(18, cellStep * 0.32));

  const position = new Map();
  for (const cell of cells) {
    const cover = coverageForCell(cell, coverByCell, treeEdges);
    const center = (cover.left + cover.right) / 2;
    const depth = depthById.get(cell.id) || 0;
    position.set(cell.id, {
      x: xFor(center),
      y: topPad + depth * depthStep,
      cover,
      x1: xFor(cover.left) - cellHalfWidth,
      x2: xFor(cover.right) + cellHalfWidth,
    });
  }

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const title = svgEl("text", { x: 22, y: 28, class: "tree-caption" });
  title.textContent = inferredTree
    ? "Fenwick coverage view: parent nodes cover wider index intervals"
    : "Segment tree view: parent nodes aggregate child intervals";
  svg.appendChild(title);

  const legend = svgEl("g", { class: "tree-legend" });
  const observedDot = svgEl("circle", { cx: 24, cy: 52, r: 7, class: "legend-observed" });
  const observedText = svgEl("text", { x: 38, y: 56 });
  observedText.textContent = "Observed";
  const synthesizedDot = svgEl("circle", { cx: 116, cy: 52, r: 7, class: "legend-synthesized" });
  const synthesizedText = svgEl("text", { x: 130, y: 56 });
  synthesizedText.textContent = "Synthesized";
  legend.appendChild(observedDot);
  legend.appendChild(observedText);
  legend.appendChild(synthesizedDot);
  legend.appendChild(synthesizedText);
  svg.appendChild(legend);

  const axisY = height - 38;
  svg.appendChild(svgEl("line", { x1: leftPad, y1: axisY, x2: width - rightPad, y2: axisY, class: "tree-axis" }));
  for (let i = minLeft; i <= maxRight; i += 1) {
    const x = xFor(i);
    svg.appendChild(svgEl("line", { x1: x, y1: axisY - 5, x2: x, y2: axisY + 5, class: "tree-axis" }));
    const label = svgEl("text", { x, y: axisY + 22, class: "tree-axis-label" });
    label.textContent = i;
    svg.appendChild(label);
  }

  for (const cell of cells) {
    const pos = position.get(cell.id);
    if (!pos) continue;
    
    svg.appendChild(svgEl("line", {
      x1: xFor(pos.cover.left),
      y1: pos.y + 29,
      x2: xFor(pos.cover.right),
      y2: pos.y + 29,
      class: "range-bar",
      "data-cell-id": cell.id,
    }));
  }

  for (const edge of treeEdges) {
    const a = position.get(edge.source);
    const b = position.get(edge.target);
    if (!a || !b) continue;
    
    const path = svgEl("path", {
      d: `M ${a.x} ${a.y + 23} C ${a.x} ${(a.y + b.y) / 2}, ${b.x} ${(a.y + b.y) / 2}, ${b.x} ${b.y - 23}`,
      class: "tree-edge",
    });
    svg.appendChild(path);
  }

  for (const cell of cells.sort((a, b) => numericIndex(a) - numericIndex(b))) {
    const pos = position.get(cell.id);
    if (!cell || !pos) continue;
    const group = svgEl("g");
    const isSynthesized = !eventEdgesForCell(analysis, cell.id).length;
    group.setAttribute("class", `tree-node ${isSynthesized ? "synthesized" : ""}`);
    group.dataset.cellId = cell.id;
    group.addEventListener("click", () => selectCell(cell.id));
    group.addEventListener("mouseenter", (e) => showNodeTooltip(e, cell.id, cell.attributes));
    group.addEventListener("mouseleave", hideNodeTooltip);
    group.addEventListener("mousemove", moveNodeTooltip);

    const cardW = Math.max(54, pos.x2 - pos.x1);
    const cardH = 46;
    const rx = 7;
    const halfH = cardH / 2;
    const cardX = pos.x - cardW / 2;

    group.appendChild(svgEl("rect", {
      x: cardX,
      y: pos.y - halfH,
      width: cardW,
      height: cardH,
      rx: rx,
      class: "node-box"
    }));

    const labelInset = Math.min(12, Math.max(7, cardW * 0.06));
    const indexY = pos.y - 3;
    const rangeY = pos.y + 13;
    const label = svgEl("text", { x: cardX + labelInset, y: indexY, class: "node-index" });
    label.textContent = `node ${cell.attributes.index ?? cell.id.split(":").pop()}`;
    group.appendChild(label);

    const rangeLabel = svgEl("text", { x: cardX + cardW - labelInset, y: rangeY, class: "node-range" });
    rangeLabel.textContent = `[${pos.cover.left},${pos.cover.right}]`;
    group.appendChild(rangeLabel);
    
    svg.appendChild(group);
  }
}

function eventEdgesForCell(analysis, cellId) {
  return (analysis.graph?.edges || []).filter((edge) => edge.kind === "accesses" && edge.target === cellId);
}

function graphNode(nodeId) {
  return (currentAnalysis?.graph?.nodes || []).find((node) => node.id === nodeId) || null;
}

function graphEdges(kind = null) {
  const edges = currentAnalysis?.graph?.edges || [];
  return kind ? edges.filter((edge) => edge.kind === kind) : edges;
}

function eventsForCell(cellId, uptoSeq = Infinity) {
  return eventEdgesForCell(currentAnalysis, cellId)
    .map((edge) => graphNode(edge.source))
    .filter(Boolean)
    .filter((node) => (node.attributes.seq || 0) <= uptoSeq)
    .sort((a, b) => (a.attributes.seq || 0) - (b.attributes.seq || 0));
}

function operationForNode(node) {
  if (!node) return null;
  const opId = node.attributes?.op_id;
  if (opId !== undefined && opId !== null) {
    return graphNode(`operation:${opId}`);
  }
  const edge = graphEdges("belongs_to").find((item) => item.source === node.id);
  return edge ? graphNode(edge.target) : null;
}

function watchesForOperation(opId) {
  return (currentAnalysis?.graph?.nodes || [])
    .filter((node) => node.label === "watch" && String(node.attributes?.op_id) === String(opId))
    .sort((a, b) => (a.attributes.seq || 0) - (b.attributes.seq || 0));
}

function nearbyWatches(seq, opId, limit = 12, uptoSeq = Infinity) {
  const watches = watchesForOperation(opId);
  if (!watches.length) return [];
  return watches
    .filter((watch) => (watch.attributes.seq || 0) <= uptoSeq)
    .map((watch) => ({ watch, distance: Math.abs((watch.attributes.seq || 0) - seq) }))
    .sort((a, b) => a.distance - b.distance || (a.watch.attributes.seq || 0) - (b.watch.attributes.seq || 0))
    .slice(0, limit)
    .map((item) => item.watch)
    .sort((a, b) => (a.attributes.seq || 0) - (b.attributes.seq || 0));
}

function sourceLineForNode(node) {
  if (!node?.attributes?.line) return "";
  return `${node.attributes.file || "source"}:${node.attributes.line}`;
}

function htmlAttrs(attrs, keys) {
  return keys
    .filter((key) => attrs[key] !== undefined && attrs[key] !== null && attrs[key] !== "")
    .map((key) => `<div class="kv"><span>${escapeHtml(key)}</span><strong>${escapeHtml(attrs[key])}</strong></div>`)
    .join("");
}

const INSPECTOR_LABELS = {
  array: "Array",
  index: "Node",
  value: "Current value",
  read_value: "Read value",
  mode: "Access",
  line: "Source line",
  kind: "Operation",
  n: "Size",
  step: "Step",
  path: "Active path",
  current: "Current node",
  previous_line: "Previous line",
  source_line: "Source line",
  range: "Covers",
  query: "Query range",
  position: "Update pos",
};

function friendlyLabel(key) {
  return INSPECTOR_LABELS[key] || key.replace(/_/g, " ");
}

function friendlyKv(entries) {
  return entries
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `<div class="kv"><span>${escapeHtml(friendlyLabel(key))}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function formatRange(range) {
  if (!Array.isArray(range) || range.length < 2) return "";
  return `[${range[0]}, ${range[1]}]`;
}

function currentStepSentence(model) {
  const step = model.step;
  if (!step) return "";
  const parts = [];
  if (model.detailTitle) parts.push(model.detailTitle);
  if (model.pathLabel) parts.push(`path ${model.pathLabel}`);
  if (step.line) parts.push(`line ${step.line}`);
  return parts.join(" - ");
}

function nodeValueSummary(attrs, fields) {
  const direct = firstValue(attrs.value, attrs.read_value);
  if (direct !== undefined) return direct;
  const preferred = ["sum", "value", "val", "mx", "max", "mn", "min", "cnt", "count", "best", "pref", "suff", "lazy", "tag"];
  for (const key of preferred) {
    if (fields?.[key] !== undefined && fields?.[key] !== null && fields?.[key] !== "") return fields[key];
  }
  return "";
}

function nodePlainExplanation(attrs, step, modelOnly) {
  const range = formatRange(attrs.range);
  const value = nodeValueSummary(attrs, attrs.fields || {});
  if (modelOnly) {
    return `This node belongs to the expected tree shape${range ? ` and covers ${range}` : ""}, but the program has not touched it at this step.`;
  }
  if (attrs.created) {
    return `The program has written this node${value !== "" ? ` with value ${value}` : ""}${range ? ` for segment ${range}` : ""}.`;
  }
  if (attrs.observed) {
    return `The program has read this node${value !== "" ? ` as ${value}` : ""}${range ? ` while considering segment ${range}` : ""}.`;
  }
  return `This node is part of the inferred tree${range ? ` for segment ${range}` : ""}, but it is not active yet.`;
}

function watchChips(watches) {
  if (!watches.length) {
    return '<div class="inspector-empty">No nearby variables were captured for this step.</div>';
  }
  return `<div class="watch-chip-list">${watches
    .map((watch) => {
      const attrs = watch.attributes || {};
      return `<button class="watch-chip" data-event-id="${watch.id}" type="button">#${escapeHtml(attrs.seq)} ${escapeHtml(attrs.name)}=${escapeHtml(attrs.value)}</button>`;
    })
    .join("")}</div>`;
}

function accessRows(events) {
  if (!events.length) {
    return '<div class="inspector-empty">This node has no read/write history up to this step.</div>';
  }
  return `<div class="mini-list">${events
    .slice(-14)
    .map((event) => {
      const attrs = event.attributes || {};
      const mode = attrs.mode === "write" ? "write" : attrs.mode === "read" ? "read" : attrs.mode || "access";
      return `<div class="mini-row">
        <span class="seq-pill">#${escapeHtml(attrs.seq)}</span>
        <span><span class="mode-pill ${escapeHtml(mode)}">${escapeHtml(mode)}</span> ${escapeHtml(attrs.array)}[${escapeHtml(attrs.index)}]${attrs.value !== undefined ? ` = <strong>${escapeHtml(attrs.value)}</strong>` : ""}${attrs.line ? ` on line ${escapeHtml(attrs.line)}` : ""}</span>
        <button type="button" data-event-id="${event.id}">Go</button>
      </div>`;
    })
    .join("")}</div>`;
}

const INSPECTOR_ICONS = {
  N: `<svg class="inspector-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`,
  E: `<svg class="inspector-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>`,
  W: `<svg class="inspector-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
  "!": `<svg class="inspector-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`
};

function inspectorHero(icon, title, subtitle) {
  const svgIcon = INSPECTOR_ICONS[icon] || `<span class="inspector-icon-char">${escapeHtml(icon)}</span>`;
  const iconClass = icon === "!" ? "finding" : icon === "N" ? "node" : icon === "E" ? "event" : "watch";
  return `<div class="inspector-hero">
    <div class="inspector-icon icon-${iconClass}">${svgIcon}</div>
    <div class="inspector-hero-content">
      <h2 class="inspector-title">${escapeHtml(title)}</h2>
      <div class="inspector-subtitle">${escapeHtml(subtitle)}</div>
    </div>
  </div>`;
}

function showNodeTooltip(event, nodeId, state) {
  const tooltip = $("nodeTooltip");
  if (!tooltip) return;
  
  const fields = state?.fields || {};
  const ignoredKeys = ["id", "idx", "l", "r", "lo", "hi", "mid", "pos", "index", "u", "v", "ql", "qr", "n"];
  const entries = Object.entries(fields).filter(([k]) => !ignoredKeys.includes(k));
  
  let headerText = `Node ${nodeId.split(":").pop()}`;
  if (state.range) {
    headerText += ` [${state.range[0]}, ${state.range[1]}]`;
  }
  
  let rowsHtml = "";
  if (entries.length > 0) {
    rowsHtml = entries.map(([key, val]) => {
      const prevVal = getLastKnownFieldValue(nodeId, key, currentStep - 1);
      const isChanged = val !== undefined && prevVal !== null && val !== prevVal;
      const dot = isChanged ? `<span class="tooltip-dot changed"></span>` : `<span class="tooltip-dot"></span>`;
      return `
        <div class="tooltip-row ${isChanged ? "row-changed" : ""}">
          ${dot}
          <span class="tooltip-key">${escapeHtml(key)}</span>
          <strong class="tooltip-val">${escapeHtml(val)}</strong>
        </div>
      `;
    }).join("");
  } else {
    const val = state?.value !== undefined ? state.value : (state?.read_value !== undefined ? state.read_value : undefined);
    if (val !== undefined) {
      let name = state?.read_value !== undefined && state?.value === undefined ? "read_value" : "value";
      const prevVal = name === "value" ? getLastKnownFieldValue(nodeId, "value", currentStep - 1) : getLastKnownFieldValue(nodeId, "read_value", currentStep - 1);
      const isChanged = val !== prevVal && prevVal !== null;
      const dot = isChanged ? `<span class="tooltip-dot changed"></span>` : `<span class="tooltip-dot"></span>`;
      rowsHtml = `
        <div class="tooltip-row ${isChanged ? "row-changed" : ""}">
          ${dot}
          <span class="tooltip-key">${name}</span>
          <strong class="tooltip-val">${escapeHtml(val)}</strong>
        </div>
      `;
    } else {
      rowsHtml = `<div class="tooltip-empty">No fields captured</div>`;
    }
  }
  
  tooltip.innerHTML = `
    <div class="tooltip-header">${escapeHtml(headerText)}</div>
    <div class="tooltip-grid">
      ${rowsHtml}
    </div>
  `;
  
  tooltip.classList.remove("hidden");
  positionTooltip(event);
}

function hideNodeTooltip() {
  const tooltip = $("nodeTooltip");
  if (tooltip) {
    tooltip.classList.add("hidden");
  }
}

function moveNodeTooltip(event) {
  positionTooltip(event);
}

function positionTooltip(event) {
  const tooltip = $("nodeTooltip");
  if (!tooltip || tooltip.classList.contains("hidden")) return;
  
  const tooltipWidth = tooltip.offsetWidth;
  const tooltipHeight = tooltip.offsetHeight;
  
  let x = event.clientX - tooltipWidth / 2;
  let y = event.clientY - tooltipHeight - 12;
  
  if (x < 10) x = 10;
  if (x + tooltipWidth > window.innerWidth - 10) {
    x = window.innerWidth - tooltipWidth - 10;
  }
  if (y < 10) {
    y = event.clientY + 20;
  }
  
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function getLastKnownFieldValue(cellId, fieldName, beforeStepIndex) {
  const steps = currentAnalysis?.tree_timeline?.steps || [];
  for (let idx = beforeStepIndex; idx >= 0; idx--) {
    const st = steps[idx];
    const val = st?.states?.[cellId]?.fields?.[fieldName];
    if (val !== undefined && val !== null) {
      return val;
    }
    if (fieldName === "value") {
      const v = st?.states?.[cellId]?.value;
      if (v !== undefined && v !== null) return v;
    }
    if (fieldName === "read_value") {
      const rv = st?.states?.[cellId]?.read_value;
      if (rv !== undefined && rv !== null) return rv;
    }
  }
  return null;
}

function getNodeFieldsForComparison(cellId, currentState, previousStepIndex) {
  const fields = [];
  const currentFields = currentState?.fields || {};
  const allFieldNames = new Set(Object.keys(currentFields));
  const ignoredKeys = ["id", "idx", "l", "r", "lo", "hi", "mid", "pos", "index", "u", "v", "ql", "qr", "n"];
  
  const steps = currentAnalysis?.tree_timeline?.steps || [];
  for (let idx = previousStepIndex; idx >= 0; idx--) {
    const pastFields = steps[idx]?.states?.[cellId]?.fields || {};
    for (const k of Object.keys(pastFields)) {
      allFieldNames.add(k);
    }
  }
  
  const filteredKeys = Array.from(allFieldNames).filter(k => !ignoredKeys.includes(k));
  
  if (filteredKeys.length > 0) {
    for (const key of filteredKeys) {
      const curVal = currentFields[key];
      const prevVal = getLastKnownFieldValue(cellId, key, previousStepIndex);
      const isChanged = curVal !== undefined && curVal !== prevVal;
      fields.push({
        name: key,
        value: curVal !== undefined ? curVal : null,
        previousValue: prevVal !== undefined ? prevVal : null,
        changed: isChanged
      });
    }
  } else {
    const curVal = currentState?.value !== undefined 
      ? currentState.value 
      : (currentState?.read_value !== undefined ? currentState.read_value : undefined);
    
    let prevVal = null;
    let name = "value";
    if (currentState?.value !== undefined) {
      prevVal = getLastKnownFieldValue(cellId, "value", previousStepIndex);
    } else if (currentState?.read_value !== undefined) {
      prevVal = getLastKnownFieldValue(cellId, "read_value", previousStepIndex);
      name = "read_value";
    }
    
    if (curVal !== undefined || prevVal !== null) {
      const isChanged = curVal !== undefined && curVal !== prevVal;
      fields.push({
        name: name,
        value: curVal !== undefined ? curVal : null,
        previousValue: prevVal,
        changed: isChanged
      });
    }
  }
  return fields;
}

function generateFriendlyExplanation(attrs, step, cellId, isCurrent, isActivePath) {
  const range = attrs.range ? `[${attrs.range[0]}, ${attrs.range[1]}]` : "";
  const name = `${attrs.array || "seg"}[${attrs.index ?? ""}]`;
  
  if (attrs.synthesized && !attrs.created && !attrs.observed) {
    return `Node <strong>${name}</strong> đại diện cho đoạn <strong>${range}</strong>. Đây là một node giả lập thuộc cấu trúc cây dự kiến nhưng chưa được truy cập thực tế trong trace.`;
  }
  
  let explanation = `Node <strong>${name}</strong> đại diện cho đoạn <strong>${range}</strong>.`;
  
  if (isCurrent && step) {
    const mutation = step.mutation || {};
    if (step.type === "access") {
      const fields = getNodeFieldsForComparison(cellId, attrs, currentStep - 1);
      const changed = fields.filter(f => f.changed);
      
      if (mutation.mode === "write") {
        if (changed.length > 0) {
          const fieldDesc = changed.map(f => `<code>${escapeHtml(f.name)}</code> thành <code>${escapeHtml(f.value)}</code> (trước đó là <code>${f.previousValue ?? "null"}</code>)`).join(", ");
          explanation += ` Ở bước này, chương trình <strong>cập nhật</strong> các trường dữ liệu: ${fieldDesc}.`;
        } else {
          explanation += ` Ở bước này, chương trình <strong>cập nhật</strong> node với giá trị mới <code>${escapeHtml(mutation.value ?? "")}</code>.`;
        }
      } else {
        explanation += ` Ở bước này, chương trình <strong>đọc dữ liệu</strong> của node.`;
      }
    } else if (step.type === "op_begin" || step.type === "op_end") {
      const action = step.type === "op_begin" ? "bắt đầu thực hiện" : "hoàn thành thực hiện và trả về ở";
      explanation += ` Tiến trình đang ${action} hàm xử lý liên quan đến node này.`;
    } else {
      explanation += ` Node đang là trọng tâm xử lý tại bước hiện tại.`;
    }
  } else if (isActivePath) {
    explanation += ` Node này nằm trên <strong>đường đi tích cực</strong> (active path) từ gốc đến node đang xử lý.`;
  } else {
    explanation += ` Hiện tại node đang ở trạng thái chờ (idle).`;
  }
  
  return explanation;
}

function renderCellInspector(cellId) {
  const cell = graphNode(cellId);
  const { steps, step } = timelineParts(currentAnalysis);
  const timelineNode = (currentAnalysis?.tree_timeline?.nodes || []).find((node) => node.id === cellId);
  if (!cell && !timelineNode) return "";
  const stepSeq = step?.seq ?? Infinity;
  const hasTimeline = Boolean(currentAnalysis?.tree_timeline?.steps?.length);
  const state = step?.states?.[cellId] || {};
  const attrs = hasTimeline
    ? { ...(timelineNode || {}), ...state }
    : { ...(timelineNode || {}), ...(cell?.attributes || {}), ...state };
  attrs.fields = state.fields || {};
  const events = eventsForCell(cellId, stepSeq);
  const lastEvent = events[events.length - 1] || null;
  const op = operationForNode(lastEvent);
  const watches = lastEvent ? nearbyWatches(lastEvent.attributes.seq || 0, lastEvent.attributes.op_id, 16, stepSeq) : [];
  const fields = state.fields || {};
  const modelOnly = Boolean(timelineNode?.synthesized && !state.created && !state.observed);
  const nodeSubtitle = state.created
    ? `Committed value at step ${currentStep}`
    : state.observed
      ? `Observed by a read before a local write at step ${currentStep}`
      : modelOnly
        ? "Model-only node, not reached in the trace at this step"
      : "Node not reached yet at this step";
  const value = nodeValueSummary(attrs, fields);
  const opAttrs = op?.attributes || {};
  const currentRange = formatRange(attrs.range);
  const queryRange = step?.query_range ? formatRange([step.query_range.left, step.query_range.right]) : "";
  const updatePos = firstValue(step?.position, step?.pos, step?.update_pos);

  const activeNodeSet = new Set(step?.active_nodes || []);
  const isCurrent = step?.node_id === cellId;
  const isActivePath = activeNodeSet.has(cellId);
  const friendlyExpl = generateFriendlyExplanation(attrs, step, cellId, isCurrent, isActivePath);
  
  const rawValue = state.value !== undefined ? state.value : (attrs.value !== undefined ? attrs.value : "");
  const isRawObjectWithoutFields = (rawValue === "<object>" || (typeof rawValue === "string" && rawValue.startsWith("{"))) && 
    (!fields || Object.keys(fields).length === 0);

  const comparisonFields = getNodeFieldsForComparison(cellId, attrs, currentStep - 1);
  
  let fieldsTableHtml = "";
  if (isRawObjectWithoutFields) {
    fieldsTableHtml = `
      <div class="fallback-warning">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="warning-icon"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
        <div class="warning-body">
          <strong>Backend compatibility note:</strong> This node stores a struct object, but its fields were not captured. 
          Write fields individually (e.g. <code>seg[v].sum = ...</code>) or enable struct-field extraction.
        </div>
      </div>
    `;
  } else if (comparisonFields.length > 0) {
    const rows = comparisonFields.map(f => {
      let deltaStr = "—";
      let deltaClass = "delta-neutral";
      if (f.value !== null && f.previousValue !== null) {
        const vNum = Number(f.value);
        const pNum = Number(f.previousValue);
        if (!isNaN(vNum) && !isNaN(pNum)) {
          const diff = vNum - pNum;
          if (diff > 0) {
            deltaStr = `+${diff}`;
            deltaClass = "delta-positive";
          } else if (diff < 0) {
            deltaStr = `${diff}`;
            deltaClass = "delta-negative";
          } else {
            deltaStr = "0";
          }
        }
      } else if (f.value !== null && f.previousValue === null) {
        deltaStr = "new";
        deltaClass = "delta-positive";
      }
      
      const statusStr = f.changed ? "changed" : "unchanged";
      const statusClass = f.changed ? "status-changed" : "status-unchanged";
      const rowClass = f.changed ? "row-changed" : "";
      
      return `
        <tr class="${rowClass}">
          <td class="field-name"><code>${escapeHtml(f.name)}</code></td>
          <td class="field-value">${f.previousValue !== null ? escapeHtml(f.previousValue) : '<span class="value-null">—</span>'}</td>
          <td class="field-value"><strong>${f.value !== null ? escapeHtml(f.value) : '<span class="value-null">—</span>'}</strong></td>
          <td class="field-delta ${deltaClass}">${escapeHtml(deltaStr)}</td>
          <td class="field-status"><span class="status-badge ${statusClass}">${statusStr}</span></td>
        </tr>
      `;
    }).join("");
    
    fieldsTableHtml = `
      <div class="table-responsive">
        <table class="delta-table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Previous</th>
              <th>Current</th>
              <th>Delta</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    `;
  } else {
    fieldsTableHtml = '<div class="inspector-empty">No fields were captured for this node at this step.</div>';
  }

  return `
    ${inspectorHero("N", `${attrs.array || "array"}[${attrs.index ?? ""}]`, nodeSubtitle)}
    
    <div class="inspector-section">
      <h3>Segment Meaning</h3>
      <div class="inspector-note friendly-explanation">${friendlyExpl}</div>
    </div>

    <div class="inspector-section">
      <h3>Field Values & Deltas</h3>
      ${fieldsTableHtml}
    </div>

    <div class="inspector-section">
      <h3>Metadata</h3>
      <div class="kv-grid">
        ${friendlyKv([
          ["array", attrs.array],
          ["index", attrs.index],
          ["range", currentRange],
          ["value", value],
          ["kind", opAttrs.kind],
          ["line", firstValue(attrs.line, opAttrs.line)],
          ["query", queryRange],
          ["position", updatePos],
        ])}
      </div>
    </div>

    <div class="inspector-section">
      <h3>Read / Write History</h3>
      ${accessRows(events)}
    </div>
    <div class="inspector-section">
      <h3>Nearby Variables</h3>
      ${watchChips(watches)}
    </div>
  `;
}

function renderEventInspector(eventId) {
  const node = graphNode(eventId);
  if (!node) return "";
  const attrs = node.attributes || {};
  const { step } = timelineParts(currentAnalysis);
  const uptoSeq = step?.seq ?? Infinity;
  const op = operationForNode(node);
  const watches = node.label === "watch"
    ? nearbyWatches(attrs.seq || 0, attrs.op_id, 16, uptoSeq)
    : nearbyWatches(attrs.seq || 0, attrs.op_id, 16, uptoSeq);
  const title = node.label === "watch"
    ? `${attrs.name || "watch"} = ${attrs.value ?? ""}`
    : `${attrs.mode || "event"} ${attrs.array || ""}[${attrs.index ?? ""}]`;
  const subtitle = `${attrs.mode === "write" ? "Writes a tree value" : attrs.mode === "read" ? "Reads a tree value" : "Runtime event"}${attrs.line ? ` on line ${attrs.line}` : ""}`;
  const eventNote = node.label === "watch"
    ? `At this point, variable ${attrs.name || "watch"} has value ${attrs.value ?? ""}.`
    : `The program ${attrs.mode === "write" ? "writes" : attrs.mode === "read" ? "reads" : "touches"} ${attrs.array || "array"}[${attrs.index ?? ""}]${attrs.value !== undefined ? ` with value ${attrs.value}` : ""}.`;

  return `
    ${inspectorHero(node.label === "watch" ? "W" : "E", title, subtitle)}
    <div class="inspector-note">${eventNote}</div>
    <div class="kv-grid">
      ${friendlyKv([
        ["Access", attrs.mode],
        ["array", attrs.array],
        ["index", attrs.index],
        ["value", attrs.value],
        ["Source line", attrs.line],
        ["kind", op?.attributes?.kind],
        ["Size", op?.attributes?.n],
      ])}
    </div>
    <div class="inspector-section">
      <h3>Nearby Variables</h3>
      ${watchChips(watches)}
    </div>
  `;
}

function renderFindingInspector(index) {
  const finding = (currentAnalysis?.findings || [])[Number(index)];
  if (!finding) return "";
  const rankedLines = finding.evidence?.slice?.ranked_lines || [];
  return `
    ${inspectorHero("!", finding.code || "Finding", finding.severity || "info")}
    <div class="inspector-section">
      <h3>Message</h3>
      <div class="finding-message">${escapeHtml(finding.message || "")}</div>
    </div>
    <div class="kv-grid">
      ${htmlAttrs(finding, ["op_id", "severity", "code"])}
    </div>
    <div class="inspector-section">
      <h3>Evidence</h3>
      <pre class="json-block">${escapeHtml(JSON.stringify(finding.evidence || {}, null, 2))}</pre>
    </div>
    <div class="inspector-section">
      <h3>Suspect Lines</h3>
      ${rankedLines.length
        ? `<div class="watch-chip-list">${rankedLines.map((line) => `<button class="watch-chip" data-line-jump="${escapeHtml(line.line)}" type="button">${escapeHtml(line.file)}:${escapeHtml(line.line)} · ${escapeHtml(line.score)}</button>`).join("")}</div>`
        : '<div class="inspector-empty">No ranked suspect lines for this finding.</div>'}
    </div>
  `;
}

function renderCurrentStepInspector() {
  if (!currentAnalysis) return "";
  const model = timelinePanelModel(currentAnalysis);
  const step = model.step;
  if (!step) return "";
  const fields = {
    step: `${currentStep} / ${Math.max(0, model.steps.length - 1)}`,
    path: model.pathLabel,
    current: model.currentNode,
    source_line: step.line || "",
  };
  return `
    <div class="inspector-section current-step-card">
      <h3>Current Step</h3>
      <div class="inspector-note compact">${currentStepSentence(model) || "Move the timeline to inspect a runtime step."}</div>
      <div class="kv-grid">
        ${Object.entries(fields)
          .filter(([, value]) => value !== "")
          .map(([key, value]) => `<div class="kv"><span>${escapeHtml(friendlyLabel(key))}</span><strong>${escapeHtml(value)}</strong></div>`)
          .join("")}
      </div>
    </div>
  `;
}

function renderInspector() {
  const container = $("inspector");
  if (!container) return;
  if (!currentAnalysis) {
    container.innerHTML = '<div class="inspector-empty">Run the program, then click a node, event, or finding.</div>';
    return;
  }

  let body = "";
  if (selected.finding !== null) {
    body = renderFindingInspector(selected.finding);
  } else if (selected.cell) {
    body = renderCellInspector(selected.cell);
  } else if (selected.event) {
    body = renderEventInspector(selected.event);
  } else {
    body = '<div class="inspector-empty">Click a tree node to see what segment it represents, what value it stores, and which reads/writes led there.</div>';
  }
  container.innerHTML = renderCurrentStepInspector() + body;

  for (const button of container.querySelectorAll("[data-event-id]")) {
    button.addEventListener("click", () => selectEvent(button.dataset.eventId));
  }
  for (const button of container.querySelectorAll("[data-line-jump]")) {
    button.addEventListener("click", () => {
      selected.line = Number(button.dataset.lineJump);
      applySelection();
    });
  }
}

function showEditMode() {
  const codeInput = $("codeInput");
  const sourceView = $("sourceView");
  const editBtn = $("editCodeBtn");
  if (codeInput) codeInput.style.display = "block";
  if (sourceView) sourceView.style.display = "none";
  if (editBtn) editBtn.style.display = "none";
}

function showViewMode() {
  const codeInput = $("codeInput");
  const sourceView = $("sourceView");
  const editBtn = $("editCodeBtn");
  if (codeInput) codeInput.style.display = "none";
  if (sourceView) sourceView.style.display = "block";
  if (editBtn) editBtn.style.display = "flex";
}

function renderSource(analysis) {
  showViewMode();
  const sourceFiles = analysis.source_files || {};
  const source = sourceFiles.original || sourceFiles.instrumented || "";
  const lines = source ? source.split(/\r?\n/) : ["Source is not embedded in this analysis.json."];
  const container = $("sourceView");
  container.innerHTML = lines
    .map((line, idx) => {
      const lineNo = idx + 1;
      return `<div class="source-line" data-line="${lineNo}"><span class="line-no">${lineNo}</span><span>${escapeHtml(line)}</span></div>`;
    })
    .join("");

  for (const lineEl of container.querySelectorAll(".source-line")) {
    lineEl.addEventListener("click", () => {
      const lineNo = Number(lineEl.dataset.line);
      if (lineNo) {
        selected.line = lineNo;
        selected.previousLine = null;
        applySelection(false);
      }
    });
  }
}

function renderTimelineLegacy(analysis) {
  const { steps, step } = timelineParts(analysis);
  if (!steps.length) {
    $("timeline").innerHTML = '<div class="inspector-empty">No timeline yet. Run the program first.</div>';
    return;
  }
  const title = timelineStepTitle(step);
  const detailTitle = timelineStepTitle(step, { includePath: false });
  const pathLabel = activeNodePathLabel(step);
  const currentNode = step?.node_id ? step.node_id.split(":").pop() : "";
  const previousLine = previousTimelineLine(analysis, currentStep, step?.line || null);
  $("timeline").innerHTML = `
    <div class="time-controls">
      <button id="prevStep" type="button" data-tooltip="Previous step (←)">Prev</button>
      <button id="playStep" type="button" data-tooltip="Play/Pause (Space)">${playTimer ? "Pause" : "Play"}</button>
      <button id="nextStep" type="button" data-tooltip="Next step (→)">Next</button>
      <div class="time-readout">
        <strong>Step ${currentStep} / ${steps.length - 1}</strong>
        <span>seq ${step?.seq ?? 0} - ${escapeHtml(title)}</span>
      </div>
    </div>
    <input id="timeSlider" class="time-slider" type="range" min="0" max="${steps.length - 1}" value="${currentStep}">
    <div class="time-detail">
      <span class="seq-pill">#${escapeHtml(step?.seq ?? 0)}</span>
      <span>${escapeHtml(detailTitle)}</span>
      ${pathLabel ? `<span class="time-path">path ${escapeHtml(pathLabel)}</span>` : ""}
      ${currentNode ? `<span class="time-current">current ${escapeHtml(currentNode)}</span>` : ""}
      ${previousLine ? `<span class="time-prev-line">prev line ${escapeHtml(previousLine)}</span>` : ""}
      <span>${step?.line ? `source line ${escapeHtml(step.line)}` : ""}</span>
    </div>
    <div class="time-watch-strip">
      ${(step?.watches || []).map((watch) => `<span class="watch-chip">#${escapeHtml(watch.seq)} ${escapeHtml(watch.name)}=${escapeHtml(watch.value)}</span>`).join("")}
    </div>
  `;
  $("timeSlider").addEventListener("input", (event) => setCurrentStep(event.target.value, true));
  $("prevStep").addEventListener("click", () => setCurrentStep(currentStep - 1, true));
  $("nextStep").addEventListener("click", () => setCurrentStep(currentStep + 1, true));
  $("playStep").addEventListener("click", togglePlayback);
}

function renderTimeline(analysis) {
  const { steps, step } = timelineParts(analysis);
  if (!steps.length) {
    $("timeline").innerHTML = '<div class="inspector-empty">No timeline yet. Run the program first.</div>';
    return;
  }
  const model = timelinePanelModel(analysis);
  $("timeline").innerHTML = `
    <div class="time-controls">
      <div class="time-nav" aria-label="Timeline controls">
        <button id="prevStep" class="time-nav-button" type="button" aria-label="Previous step" title="Previous step">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 18 9 12l6-6"></path></svg>
        </button>
        <button id="playStep" class="time-nav-button play" type="button" aria-label="Play or pause" title="Play/Pause">
          ${playTimer ? pauseIconSvg() : playIconSvg()}
        </button>
        <button id="nextStep" class="time-nav-button" type="button" aria-label="Next step" title="Next step">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"></path></svg>
        </button>
      </div>
      <div class="time-speed" aria-label="Playback speed">
        <button class="time-speed-button ${playbackDelayMs === 1500 ? "active" : ""}" type="button" data-speed-ms="1500">0.5x</button>
        <button class="time-speed-button ${playbackDelayMs === 1000 ? "active" : ""}" type="button" data-speed-ms="1000">1x</button>
        <button class="time-speed-button ${playbackDelayMs === 550 ? "active" : ""}" type="button" data-speed-ms="550">2x</button>
        <label class="time-speed-custom">
          <input id="speedInput" type="number" min="0.1" max="10" step="0.1" value="${escapeHtml(speedSecondsValue())}" aria-label="Custom seconds per step">
          <span>s</span>
        </label>
      </div>
      <div class="time-readout">
        <strong id="timeStepLabel">Step ${currentStep} / ${steps.length - 1}</strong>
      </div>
    </div>
    <div class="time-slider-row">
      <span class="time-bound">0</span>
      <input id="timeSlider" class="time-slider" type="range" min="0" max="${steps.length - 1}" value="${currentStep}" step="1">
      <span class="time-bound">${escapeHtml(steps.length - 1)}</span>
    </div>
  `;
  $("timeSlider").addEventListener("input", (event) => setCurrentStepInternal(event.target.value, true, false));
  $("prevStep").addEventListener("click", () => setCurrentStepInternal(currentStep - 1, true, false));
  $("nextStep").addEventListener("click", () => setCurrentStepInternal(currentStep + 1, true, false));
  $("playStep").addEventListener("click", togglePlayback);
  for (const button of document.querySelectorAll(".time-speed-button")) {
    button.addEventListener("click", () => setPlaybackSpeed(Number(button.dataset.speedMs || playbackDelayMs)));
  }
  $("speedInput").addEventListener("change", (event) => setPlaybackSpeedSeconds(event.target.value));
}

function timelinePanelModel(analysis) {
  const { steps, step } = timelineParts(analysis);
  return {
    steps,
    step,
    title: timelineStepTitle(step),
    detailTitle: timelineStepTitle(step, { includePath: false }),
    pathLabel: activeNodePathLabel(step),
    currentNode: step?.node_id ? step.node_id.split(":").pop() : "",
    previousLine: previousTimelineLine(analysis, currentStep, step?.line || null),
  };
}

function timelineDetailHtml(model) {
  const step = model.step;
  return `
    <span class="seq-pill">#${escapeHtml(step?.seq ?? 0)}</span>
    <span class="time-main-step">${escapeHtml(model.detailTitle)}</span>
    ${model.pathLabel ? `<span class="time-path">path ${escapeHtml(model.pathLabel)}</span>` : ""}
    ${model.currentNode ? `<span class="time-current">current ${escapeHtml(model.currentNode)}</span>` : ""}
    ${model.previousLine ? `<span class="time-prev-line">prev line ${escapeHtml(model.previousLine)}</span>` : ""}
    ${step?.line ? `<span class="time-source-line">source line ${escapeHtml(step.line)}</span>` : ""}
  `;
}

function updateTimelinePanel(analysis) {
  const model = timelinePanelModel(analysis);
  const slider = $("timeSlider");
  if (slider) slider.value = currentStep;
  const stepLabel = $("timeStepLabel");
  if (stepLabel) stepLabel.textContent = `Step ${currentStep} / ${model.steps.length - 1}`;
}

function playIconSvg() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg>';
}

function pauseIconSvg() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14"></path><path d="M16 5v14"></path></svg>';
}

function timelineStepTitle(step, options = {}) {
  const includePath = options.includePath !== false;
  const mutation = step?.mutation || {};
  if (!step || step.type === "initial") return "initial state";
  if (step.type === "op_begin" || step.type === "op_end") {
    const stack = step.call_stack || [];
    const frame = stack.length ? stack[stack.length - 1] : {};
    const action = mutation.action === "end" ? "return" : "enter";
    const node = frame.node !== undefined ? ` node ${frame.node}` : "";
    const range = frame.range ? ` [${frame.range[0]},${frame.range[1]}]` : "";
    const path = activeNodePathLabel(step);
    return `${action} ${frame.kind || mutation.kind || "operation"}${node}${range}${includePath && path ? ` - path ${path}` : ""}`;
  }
  if (step.type === "access") {
    const phase = step.phase ? `${step.phase}: ` : "";
    const path = activeNodePathLabel(step);
    return `${phase}${mutation.mode || "access"} ${mutation.array || ""}[${mutation.index ?? ""}] = ${mutation.value ?? ""}${includePath && path ? ` - path ${path}` : ""}`;
  }
  if (step.type === "watch") {
    return `${mutation.name || "watch"} = ${mutation.value ?? ""}`;
  }
  if (step.type === "line") {
    if (mutation.kind === "condition") {
      const value = mutation.value ? ` = ${mutation.value}` : "";
      return `check source line ${step.line || mutation.line || ""}${value}`.trim();
    }
    if (mutation.kind === "else") {
      return `enter else line ${step.line || mutation.line || ""}`.trim();
    }
    return `execute source line ${step.line || mutation.line || ""}`.trim();
  }
  return String(step.type || "step");
}

function activeNodePathLabel(step) {
  const nodes = step?.active_nodes || [];
  if (!nodes.length) return "";
  return nodes.map((nodeId) => nodeId.split(":").pop()).join(" -> ");
}

function renderFindings(analysis) {
  const findings = analysis.findings || [];
  $("findings").innerHTML = findings.length
    ? findings
        .map((finding, idx) => {
          return `<div class="finding ${finding.severity || "info"}" data-finding="${idx}" data-op="${finding.op_id || ""}">
            <div class="finding-code">${escapeHtml(finding.severity)} · ${escapeHtml(finding.code)}</div>
            <div class="finding-message">${escapeHtml(finding.message)}</div>
          </div>`;
        })
        .join("")
    : '<div class="finding info"><div class="finding-code">OK</div><div class="finding-message">Không có cảnh báo.</div></div>';
  for (const findingEl of document.querySelectorAll(".finding[data-finding]")) {
    findingEl.addEventListener("click", () => selectFinding(findingEl.dataset.finding));
  }
}

function isActionableFinding(finding) {
  const severity = finding?.severity || "info";
  return ["error", "warning"].includes(severity) && finding?.code !== "UNSCOPED_ACCESSES";
}

function findingGroupKey(finding) {
  const firstLine = finding.suspect_lines?.[0] || "";
  return [finding.severity || "info", finding.code || "", finding.message || "", firstLine].join("||");
}

function groupedActionableFindings(findings) {
  const groups = [];
  const byKey = new Map();
  findings
    .map((finding, idx) => ({ finding, idx }))
    .filter((item) => isActionableFinding(item.finding))
    .forEach((item) => {
      const key = findingGroupKey(item.finding);
      let group = byKey.get(key);
      if (!group) {
        group = { ...item, count: 0, opIds: [] };
        byKey.set(key, group);
        groups.push(group);
      }
      group.count += 1;
      if (item.finding.op_id !== undefined && item.finding.op_id !== null) {
        group.opIds.push(item.finding.op_id);
      }
    });
  return groups;
}

function severityIcon(severity) {
  if (severity === "error") return "✕";
  if (severity === "warning") return "⚠";
  return "ℹ";
}

function renderFindingsClean(analysis) {
  const findings = analysis.findings || [];
  const actionableCount = findings.filter(isActionableFinding).length;
  const diagnosticCount = findings.length - actionableCount;
  const groups = groupedActionableFindings(findings);
  const cards = groups.length
    ? groups
        .map(({ finding, idx, count, opIds }) => {
          const firstLine = finding.suspect_lines?.[0] || "";
          const ops = [...new Set(opIds)].slice(0, 8).join(", ");
          const severity = finding.severity || "info";
          return `<button class="finding ${severity}" data-finding="${idx}" data-op="${finding.op_id || ""}" type="button">
            <span class="finding-icon">${severityIcon(severity)}</span>
            <div class="finding-body">
              <div class="finding-code">${escapeHtml(severity.toUpperCase())} - ${escapeHtml(finding.code || "")}</div>
              <div class="finding-message">${escapeHtml(finding.message || "")}</div>
              ${firstLine ? `<div class="finding-message" style="opacity: 0.8; font-size: 11px;">Top suspect: ${escapeHtml(firstLine)}</div>` : ""}
              ${count > 1 ? `<div class="finding-message" style="opacity: 0.8; font-size: 11px;">${count} occurrences${ops ? ` across ops ${escapeHtml(ops)}` : ""}</div>` : ""}
            </div>
            ${count > 1 ? `<span class="finding-count">×${count}</span>` : ""}
          </button>`;
        })
        .join("")
    : '<div class="finding info"><span class="finding-icon">✓</span><div class="finding-body"><div class="finding-code">OK</div><div class="finding-message">No actionable findings.</div></div></div>';
  const note = diagnosticCount > 0
    ? `<div class="finding info diagnostic-note"><span class="finding-icon">ℹ</span><div class="finding-body"><div class="finding-code">${diagnosticCount} diagnostic note${diagnosticCount > 1 ? "s" : ""}</div><div class="finding-message">Kept in the analysis graph, hidden from the main finding list.</div></div></div>`
    : "";
  $("findings").innerHTML = cards + note;
  for (const findingEl of document.querySelectorAll(".finding[data-finding]")) {
    findingEl.addEventListener("click", () => selectFinding(findingEl.dataset.finding));
  }
}

function selectCell(cellId) {
  selected.cell = cellId;
  selected.finding = null;
  const { step } = timelineParts(currentAnalysis);
  const events = eventsForCell(cellId, step?.seq ?? Infinity);
  selected.event = events[events.length - 1]?.id || null;
  const eventNode = selected.event ? graphNode(selected.event) : null;
  selected.line = eventNode?.attributes?.line || null;
  selected.previousLine = previousTimelineLine(currentAnalysis, currentStep, selected.line);
  applySelection();
}

function selectEvent(eventId) {
  selected.event = eventId;
  selected.finding = null;
  const eventNode = (currentAnalysis.graph?.nodes || []).find((node) => node.id === eventId);
  const { steps } = timelineParts(currentAnalysis);
  const seq = eventNode?.attributes?.seq;
  const stepIndex = steps.findIndex((step) => String(step.seq) === String(seq));
  if (stepIndex >= 0) currentStep = stepIndex;
  selected.line = eventNode?.attributes?.line || null;
  selected.previousLine = previousTimelineLine(currentAnalysis, currentStep, selected.line);
  const edge = (currentAnalysis.graph?.edges || []).find((item) => item.kind === "accesses" && item.source === eventId);
  selected.cell = edge?.target || null;
  applySelection();
}

function selectFinding(index) {
  selected.finding = String(index);
  const finding = (currentAnalysis.findings || [])[Number(index)];
  const seedEvent = finding?.evidence?.slice?.seed_events?.[0];
  const topLine = finding?.evidence?.slice?.ranked_lines?.[0]?.line;
  if (seedEvent && graphNode(seedEvent)) {
    selected.event = seedEvent;
    const accessEdge = graphEdges("accesses").find((edge) => edge.source === seedEvent);
    selected.cell = accessEdge?.target || null;
  }
  if (topLine) {
    selected.line = Number(topLine);
    selected.previousLine = null;
  }
  if (finding?.op_id) {
    const eventEdge = (currentAnalysis.graph?.edges || []).find(
      (edge) => edge.kind === "belongs_to" && edge.target === `operation:${finding.op_id}`,
    );
    if (eventEdge && !selected.event) {
      selected.event = eventEdge.source;
      const eventNode = graphNode(eventEdge.source);
      selected.line = eventNode?.attributes?.line || null;
      selected.previousLine = previousTimelineLine(currentAnalysis, currentStep, selected.line);
      const accessEdge = graphEdges("accesses").find((edge) => edge.source === eventEdge.source);
      selected.cell = accessEdge?.target || null;
    }
  }
  applySelection();
}

function applySelection(allowScroll = true) {
  document.querySelectorAll(".selected").forEach((el) => el.classList.remove("selected"));
  document.querySelectorAll(".previous-selected").forEach((el) => el.classList.remove("previous-selected"));
  if (selected.cell) {
    document.querySelectorAll(`[data-cell-id="${CSS.escape(selected.cell)}"]`).forEach((el) => el.classList.add("selected"));
  }
  if (selected.event) {
    document.querySelectorAll(`[data-event-id="${CSS.escape(selected.event)}"]`).forEach((el) => el.classList.add("selected"));
  }
  if (selected.previousLine && Number(selected.previousLine) !== Number(selected.line || 0)) {
    document.querySelectorAll(`[data-line="${selected.previousLine}"]`).forEach((el) => el.classList.add("previous-selected"));
  }
  if (selected.line) {
    document.querySelectorAll(`[data-line="${selected.line}"]`).forEach((el) => el.classList.add("selected"));
  }
  if (selected.finding !== null) {
    document.querySelectorAll(`[data-finding="${selected.finding}"]`).forEach((el) => el.classList.add("selected"));
  }
  if (allowScroll) {
    const selectedSource = selected.line ? document.querySelector(`[data-line="${selected.line}"]`) : null;
    if (selectedSource) {
      selectedSource.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    const selectedEvent = selected.event ? document.querySelector(`[data-event-id="${CSS.escape(selected.event)}"]`) : null;
    if (selectedEvent) {
      selectedEvent.scrollIntoView({ block: "center", behavior: "smooth", inline: "nearest" });
    }
  }
  renderInspector();
}

function setRunStatus(message, kind = "") {
  const status = $("runStatus");
  status.textContent = message;
  status.className = `run-status ${kind}`.trim();
}

function operationLine(operation) {
  const params = (operation.params || []).join(",");
  return [
    operation.function_name || "",
    operation.operation_type || "",
    params,
    operation.logical_size || "",
  ].join(":");
}

function defaultWatchExpressions(structure) {
  if (structure === "fenwick") return "i\npos";
  if (structure === "segment_tree") return "v\npos";
  return "i";
}

function populateForm(example) {
  $("codeInput").value = example.source || "";
  $("stdinInput").value = example.input || "";
  const config = example.config || {};
  const array = (config.target_arrays || [])[0] || {};
  $("structureType").value = array.structure_type || "segment_tree";
  $("arrayName").value = array.name || "seg";
  $("sizeVariable").value = array.size_variable || "n";
  $("indexBase").value = array.index_base ?? 0;
  $("operationsText").value = (config.operations || []).map(operationLine).join("\n");
  $("watchText").value = (config.watch_expressions || []).join("\n") || defaultWatchExpressions(array.structure_type);
  applyTreeModelDefaults(array.structure_type || "segment_tree", true);
  const model = config.tree_model?.[array.name] || {};
  if (model.node_variable) $("nodeVariable").value = model.node_variable;
  if (Array.isArray(model.child_expressions)) $("childExpressions").value = model.child_expressions.join(",");
  if (model.parent_expression !== undefined) $("parentExpression").value = model.parent_expression;
}

function applyStructureDefaults() {
  const structure = $("structureType").value;
  if (structure === "fenwick") {
    $("arrayName").value = "bit";
    $("indexBase").value = 1;
    $("operationsText").value = "add:update:pos:n\nsum:query:pos:pos";
    $("watchText").value = defaultWatchExpressions(structure);
    applyTreeModelDefaults(structure);
    return;
  }
  if (structure === "segment_tree") {
    $("arrayName").value = "seg";
    $("indexBase").value = 0;
    $("operationsText").value = "update:update:pos:n\nmerge_node:merge:v:n";
    $("watchText").value = defaultWatchExpressions(structure);
    applyTreeModelDefaults(structure);
    return;
  }
  $("arrayName").value = "arr";
  $("indexBase").value = 0;
  $("operationsText").value = "scan:scan::n";
  $("watchText").value = defaultWatchExpressions(structure);
  applyTreeModelDefaults(structure);
}

function applyTreeModelDefaults(structure, overwrite = true) {
  const values = structure === "segment_tree"
    ? { node: "v", children: "2*v,2*v+1", parent: "v//2" }
    : structure === "fenwick"
      ? { node: "i", children: "", parent: "" }
      : { node: "i", children: "", parent: "" };
  if (overwrite || !$("nodeVariable").value) $("nodeVariable").value = values.node;
  if (overwrite || !$("childExpressions").value) $("childExpressions").value = values.children;
  if (overwrite || !$("parentExpression").value) $("parentExpression").value = values.parent;
}

function buildConfigFromForm() {
  const autoDetect = $("autoDetect")?.checked;
  const advancedOpen = $("advancedConfig")?.open;
  const watchExpressions = $("watchText").value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (autoDetect) {
    const config = {
      auto_detect: true,
      auto_watch_scalars: true,
      limits: { timeout_seconds: 5 },
    };
    if (advancedOpen && watchExpressions.length) {
      config.watch_expressions = watchExpressions;
    }
    return config;
  }

  const targetArray = $("arrayName").value.trim();
  const sizeVariable = $("sizeVariable").value.trim() || "n";
  const operations = $("operationsText").value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(":").map((part) => part.trim());
      const params = parts[2] ? parts[2].split(",").map((param) => param.trim()).filter(Boolean) : [];
      return {
        function_name: parts[0],
        operation_type: parts[1] || "update",
        target_array: targetArray,
        params,
        logical_size: parts[3] || sizeVariable,
      };
    });

  return {
    target_arrays: [
      {
        name: targetArray,
        structure_type: $("structureType").value,
        index_base: Number($("indexBase").value || 0),
        size_variable: sizeVariable,
      },
    ],
    operations,
    tree_model: {
      [targetArray]: {
        array: targetArray,
        kind: $("structureType").value,
        node_variable: $("nodeVariable").value.trim() || "v",
        child_expressions: $("childExpressions").value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        parent_expression: $("parentExpression").value.trim(),
      },
    },
    watch_expressions: watchExpressions,
    auto_watch_scalars: true,
    limits: { timeout_seconds: 5 },
  };
}

async function loadExample() {
  const sampleName = $("sampleSelect")?.value || "segment_ok_01";
  setRunStatus("Loading example...");
  const response = await fetch(`api/example?name=${encodeURIComponent(sampleName)}`);
  if (!response.ok) {
    throw new Error("Cannot load example.");
  }
  const example = await response.json();
  populateForm(example);
  setRunStatus("Example loaded.", "ok");
  showEditMode();
  return example;
}

function setPipelineStep(stepName, state) {
  const el = document.querySelector(`.pipeline-step[data-step="${stepName}"]`);
  if (!el) return;
  el.className = `pipeline-step ${state}`;
}

async function runAnalysisFromForm() {
  const button = $("runAnalysis");
  button.disabled = true;
  setRunStatus("Running...");
  
  setPipelineStep("code", "done");
  setPipelineStep("instrument", "active");
  setPipelineStep("run", "pending");
  setPipelineStep("analyze", "pending");
  setPipelineStep("visualize", "pending");
  
  try {
    const response = await fetch("api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: $("codeInput").value,
        input: $("stdinInput").value,
        config: buildConfigFromForm(),
      }),
    });
    
    setPipelineStep("instrument", "done");
    setPipelineStep("run", "active");
    
    const result = await response.json();
    if (result.status === "success") {
      setPipelineStep("run", "done");
      setPipelineStep("analyze", "active");
      
      loadAnalysis(result.analysis);
      
      setPipelineStep("analyze", "done");
      setPipelineStep("visualize", "active");
      
      const stdout = result.run?.stdout ? `\nstdout: ${result.run.stdout.trim()}` : "";
      const detected = result.instrumentation?.effective_config?.detected;
      const detectedText = detected
        ? `\ndetected: ${detected.structure_type} / ${detected.array}`
        : "";
      setRunStatus(`Run OK. run_id: ${result.run_id}${detectedText}${stdout}`, "ok");
      
      setTimeout(() => {
        const runPanel = $("runPanel");
        if (runPanel) runPanel.classList.add("collapsed");
      }, 600);
      return;
    }
    
    setPipelineStep("run", "error");
    setPipelineStep("analyze", "error");
    const detail = result.errors?.[0] || result.run?.stderr || result.error || "Analysis failed.";
    setRunStatus(`${result.status || "error"}\n${detail}`.trim(), "error");
  } catch (error) {
    setPipelineStep("instrument", "error");
    setPipelineStep("run", "error");
    setPipelineStep("analyze", "error");
    setRunStatus(String(error), "error");
  } finally {
    button.disabled = false;
  }
}

$("fileInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const analysis = JSON.parse(await file.text());
  loadAnalysis(analysis);
});

$("showSynthesized").addEventListener("change", () => {
  if (currentAnalysis) renderTree(currentAnalysis);
});

$("loadSample").addEventListener("click", async () => {
  await loadExample();
});

$("runAnalysis").addEventListener("click", runAnalysisFromForm);

$("structureType").addEventListener("change", applyStructureDefaults);

async function loadSampleAnalysis() {
  const sampleName = $("sampleSelect")?.value || "segment_ok_01";
  showMessage("Loading sample analysis...");
  try {
    const response = await fetch(`api/sample?name=${encodeURIComponent(sampleName)}`);
    if (response.ok) {
      loadAnalysis(await response.json());
      return true;
    }
  } catch (_) {
    // Standalone mode falls back to analysis.json below.
  }
  return tryLoadDefault();
}

async function tryLoadDefault() {
  showMessage("Loading analysis...");
  try {
    const response = await fetch("analysis.json");
    if (response.ok) {
      loadAnalysis(await response.json());
      return true;
    }
  } catch (_) {
    // Standalone mode: the file picker is the primary input.
  }
  showMessage("No analysis loaded. Use Load analysis.json or run the local API.");
  return false;
}

function clearSelection() {
  selected = { cell: null, event: null, line: null, previousLine: null, finding: null };
  applySelection();
}

async function init() {
  const editBtn = $("editCodeBtn");
  if (editBtn) {
    editBtn.addEventListener("click", () => {
      showEditMode();
    });
  }

  const findingsHeader = $("findingsPanelHeader");
  const toggleFindingsBtn = $("toggleFindingsPanel");
  if (findingsHeader) {
    findingsHeader.addEventListener("click", () => {
      $("findingsPanel").classList.toggle("collapsed");
    });
  }
  if (toggleFindingsBtn) {
    toggleFindingsBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      $("findingsPanel").classList.toggle("collapsed");
    });
  }
  const badgeFindings = $("badgeFindings");
  if (badgeFindings) {
    badgeFindings.addEventListener("click", () => {
      const panel = $("findingsPanel");
      if (panel) {
        panel.classList.toggle("collapsed");
        if (!panel.classList.contains("collapsed")) {
          panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
    });
    badgeFindings.style.cursor = "pointer";
  }

  const toggleLeftBtn = $("toggleLeftSidebar");
  if (toggleLeftBtn) {
    toggleLeftBtn.addEventListener("click", () => {
      const mainLayout = document.querySelector(".main-layout");
      if (mainLayout) {
        mainLayout.classList.toggle("collapsed-left");
        toggleLeftBtn.classList.toggle("active", mainLayout.classList.contains("collapsed-left"));
      }
    });
  }

  const toggleRightBtn = $("toggleRightSidebar");
  if (toggleRightBtn) {
    toggleRightBtn.addEventListener("click", () => {
      const mainLayout = document.querySelector(".main-layout");
      if (mainLayout) {
        mainLayout.classList.toggle("collapsed-right");
        toggleRightBtn.classList.toggle("active", mainLayout.classList.contains("collapsed-right"));
      }
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select")) return;

    switch (e.key) {
      case "ArrowLeft":
        setCurrentStep(currentStep - 1, true);
        e.preventDefault();
        break;
      case "ArrowRight":
        setCurrentStep(currentStep + 1, true);
        e.preventDefault();
        break;
      case " ":
        togglePlayback();
        e.preventDefault();
        break;
      case "Escape":
        clearSelection();
        e.preventDefault();
        break;
      case "e":
        // removed runPanel toggle
        break;

    }
  });

  try {
    await loadExample();
  } catch (error) {
    setRunStatus(String(error), "error");
  }
  const fieldFocusSelect = $("fieldFocusSelector");
  if (fieldFocusSelect) {
    fieldFocusSelect.addEventListener("change", (e) => {
      selectedFocusField = e.target.value;
      if (currentAnalysis) {
        renderTree(currentAnalysis);
        renderInspector();
      }
    });
  }

  await loadSampleAnalysis();
}

init();

