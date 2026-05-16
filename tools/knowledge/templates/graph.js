(function () {
  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  function closeGraphModals() {
    document.querySelectorAll(".dep-modal-container").forEach((modal) => {
      modal.hidden = true;
    });
  }

  function showGraphModalElement(modal) {
    closeGraphModals();
    if (modal) {
      modal.hidden = false;
      modal.querySelector(".dep-closebtn")?.focus();
    }
  }

  function graphNodeVisibleLabel(node) {
    const labels = Array.from(node.querySelectorAll("text"))
      .map((text) => text.textContent.trim())
      .filter(Boolean);
    return labels.join(" ").trim();
  }

  function dotQuote(value) {
    return `"${String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")}"`;
  }

  function topicGraphId(topicId) {
    return `topic:${topicId}`;
  }

  const GRAPH_DEFAULT_CONFIG = {
    maxVisibleNodes: 120,
    maxExpandNodes: 80,
    proofPlans: "selected-only",
  };
  const GRAPH_PROOF_PLAN_POLICIES = new Set(["hidden", "selected-only", "all"]);

  const graphState = {
    config: null,
    topicOverview: null,
    topicCache: new Map(),
    nodePayloadUrls: new Map(),
    nodePayloadCache: new Map(),
    expandedTopic: null,
    currentTopicSubgraph: null,
    proofPlanMode: null,
  };
  let graphRenderer = null;

  function renderCountLabel(count) {
    return count === 1 ? "1 edge" : `${count} edges`;
  }

  function topicOverviewToDot(data) {
    const lines = [
      'strict digraph "" {',
      "\tgraph [bgcolor=transparent];",
      '\tnode [label="\\N", penwidth=1.8, shape=box];',
      "\tedge [arrowhead=vee];",
    ];
    (data.topics || []).forEach((topic) => {
      const label = `${topic.title}\\n${topic.node_count} ${topic.node_count === 1 ? "node" : "nodes"}`;
      const attrs = [
        ["label", label],
        ["shape", "box"],
        ["URL", `#${topicGraphId(topic.id)}`],
      ];
      lines.push(`\t${dotQuote(topicGraphId(topic.id))} [${attrs.map(([key, value]) => `${key}=${dotQuote(value)}`).join(", ")}];`);
    });
    (data.edges || []).forEach((edge) => {
      const attrs = edge.count > 1 ? ` [label=${dotQuote(renderCountLabel(edge.count))}, style=dashed]` : " [style=dashed]";
      lines.push(`\t${dotQuote(topicGraphId(edge.from))} -> ${dotQuote(topicGraphId(edge.to))}${attrs};`);
    });
    lines.push("}");
    return lines.join("\n");
  }

  function shapeForKind(kind) {
    if (kind === "definition" || kind === "concept") return "box";
    if (["lemma", "proposition", "theorem", "external-theorem"].includes(kind)) return "ellipse";
    if (kind === "example" || kind === "proof-plan") return "note";
    if (kind === "task") return "component";
    return "box";
  }

  function statusColor(status) {
    if (status === "formalized" || status === "proved") return "green";
    if (status === "admitted") return "blue";
    if (["staged", "needs_statement_review", "needs_definition_review", "needs_proof_review", "blocked"].includes(status)) return "#FFAA33";
    return null;
  }

  function dotAttributes(attrs) {
    return Object.entries(attrs)
      .filter(([, value]) => value !== null && value !== undefined && value !== "")
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, value]) => `${key}=${dotQuote(value)}`)
      .join(", ");
  }

  function currentProofPlanMode() {
    return GRAPH_PROOF_PLAN_POLICIES.has(graphState.proofPlanMode)
      ? graphState.proofPlanMode
      : GRAPH_DEFAULT_CONFIG.proofPlans;
  }

  function isVisibleProofPlan(node, mode) {
    if (node.kind !== "proof-plan") return true;
    if (mode === "all") return true;
    if (mode === "selected-only") return node.plan_status === "selected";
    return false;
  }

  function visibleSubgraphNodes(data) {
    const mode = currentProofPlanMode();
    return (data.nodes || []).filter((node) => isVisibleProofPlan(node, mode));
  }

  function topicSubgraphToDot(data) {
    const visibleNodes = visibleSubgraphNodes(data);
    const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
    const endpointVisible = (nodeId) => nodeId.startsWith("topic:") || visibleNodeIds.has(nodeId);
    const lines = [
      'strict digraph "" {',
      "\tgraph [bgcolor=transparent];",
      '\tnode [label="\\N", penwidth=1.8];',
      "\tedge [arrowhead=vee];",
    ];
    if (data.topic) {
      lines.push(`\t${dotQuote(topicGraphId(data.topic.id))} [${dotAttributes({
        color: "blue",
        label: `${data.topic.title}\\nexpanded`,
        penwidth: "2.4",
        shape: "box",
        URL: `#${topicGraphId(data.topic.id)}`,
      })}];`);
    }
    (data.boundary_topics || []).forEach((topic) => {
      const label = `${topic.title}\\n${topic.role.replace(/_/g, " ")}`;
      lines.push(`\t${dotQuote(topicGraphId(topic.id))} [${dotAttributes({
        color: "#777777",
        label,
        shape: "box",
        style: "dashed",
        URL: `#${topicGraphId(topic.id)}`,
      })}];`);
    });
    visibleNodes.forEach((node) => {
      lines.push(`\t${dotQuote(node.id)} [${dotAttributes({
        color: statusColor(node.status),
        label: node.title,
        shape: shapeForKind(node.kind),
        style: node.kind === "proof-plan" ? "dashed" : null,
        URL: `#${node.id}`,
      })}];`);
    });
    (data.edges || []).filter((edge) => endpointVisible(edge.from) && endpointVisible(edge.to)).forEach((edge) => {
      lines.push(`\t${dotQuote(edge.from)} -> ${dotQuote(edge.to)} [style=${dotQuote("dashed")}];`);
    });
    (data.boundary_edges || []).filter((edge) => endpointVisible(edge.from) && endpointVisible(edge.to)).forEach((edge) => {
      const label = edge.count > 1 ? renderCountLabel(edge.count) : "";
      lines.push(`\t${dotQuote(edge.from)} -> ${dotQuote(edge.to)} [${dotAttributes({
        color: "#777777",
        label,
        style: "dashed",
      })}];`);
    });
    (data.proof_plan_attachments || []).filter((edge) => endpointVisible(edge.from) && endpointVisible(edge.to)).forEach((edge) => {
      lines.push(`\t${dotQuote(edge.from)} -> ${dotQuote(edge.to)} [${dotAttributes({
        label: "has plan",
        style: "dotted",
      })}];`);
    });
    lines.push("}");
    return lines.join("\n");
  }

  function bindGraphInteractions() {
    document.querySelectorAll("#graph .node").forEach((node) => {
      const graphNodeId = node.querySelector("title")?.textContent?.trim();
      const visibleLabel = graphNodeVisibleLabel(node) || graphNodeId || "Node";
      const titleElement = node.querySelector("title");
      if (graphNodeId) node.dataset.graphNodeId = graphNodeId;
      if (titleElement) titleElement.textContent = visibleLabel;
      node.setAttribute("aria-label", visibleLabel);
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "button");
      node.addEventListener("click", () => {
        const nodeId = node.dataset.graphNodeId;
        if (nodeId?.startsWith("topic:")) {
          handleTopicActivation(nodeId.slice("topic:".length));
          return;
        }
        if (nodeId) {
          showNodeDetail(nodeId);
          return;
        }
        const mapped = nodeId ? document.querySelector(`[data-graph-node="${cssEscape(nodeId)}"]`) : null;
        if (mapped) showGraphModalElement(mapped);
      });
      node.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        }
      });
    });
  }

  function openNodeModal(target) {
    if (target) document.getElementById(target)?.removeAttribute("hidden");
  }

  function closeNodeModal(button) {
    button.closest(".modal-container")?.setAttribute("hidden", "");
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderLinkList(title, items) {
    if (!items || !items.length) return "";
    return `<h2>${escapeHtml(title)}</h2><ul class="uses">${items.map((item) => (
      `<li><a href="${escapeHtml(item.href)}">${escapeHtml(item.title)}</a></li>`
    )).join("")}</ul>`;
  }

  function renderLeanRefs(refs) {
    if (!refs || !refs.length) return "";
    const items = refs.map((ref) => {
      const declaration = ref.source_url
        ? `<a href="${escapeHtml(ref.source_url)}"><code>${escapeHtml(ref.display_name)}</code></a>`
        : `<code>${escapeHtml(ref.display_name)}</code>`;
      const unresolved = ref.status === "unresolved"
        ? ` <span class="badge status-staged">Unresolved</span>${ref.reason ? ` <span class="lean-source-meta">${escapeHtml(ref.reason)}</span>` : ""}`
        : "";
      const metadata = ref.status !== "unresolved" && ref.repository_title
        ? ` <span class="lean-source-meta">${escapeHtml(ref.repository_title)}${ref.short_revision ? ` @ ${escapeHtml(ref.short_revision)}` : ""}${ref.module ? `, ${escapeHtml(ref.module)}` : ""}</span>`
        : "";
      const sorry = ref.has_sorry ? ' <span class="badge status-needs_proof_review">sorry/admit</span>' : "";
      return `<li>${declaration}${unresolved}${metadata}${sorry}</li>`;
    }).join("");
    return `<h2>Lean declarations</h2><ul class="uses">${items}</ul>`;
  }

  function graphLimit(name) {
    const value = graphState.config?.[name];
    return Number.isInteger(value) && value > 0 ? value : GRAPH_DEFAULT_CONFIG[name];
  }

  function visibleSubgraphNodeCount(data) {
    return 1 + (data.boundary_topics || []).length + visibleSubgraphNodes(data).length;
  }

  function exceedsTopicExpansionLimits(data) {
    const internalNodes = data.counts?.internal_nodes ?? (data.nodes || []).length;
    return internalNodes > graphLimit("maxExpandNodes")
      || visibleSubgraphNodeCount(data) > graphLimit("maxVisibleNodes");
  }

  function hideGraphFallback() {
    const fallback = document.getElementById("graph-fallback");
    const graphElement = document.getElementById("graph");
    if (fallback) {
      fallback.hidden = true;
      fallback.replaceChildren();
    }
    if (graphElement) graphElement.hidden = false;
  }

  function showOversizedTopicFallback(data) {
    const graphElement = document.getElementById("graph");
    const fallback = document.getElementById("graph-fallback");
    if (!graphElement || !fallback) return;

    graphElement.hidden = true;
    graphElement.replaceChildren();
    graphRenderer = null;

    const topic = data.topic || {};
    const title = topic.title || topic.id || "Topic";
    const nodeCount = data.counts?.internal_nodes ?? (data.nodes || []).length;
    const keywordPages = (data.keywords || []).map((keyword) => (
      `<li><a href="${escapeHtml(keyword.href)}">${escapeHtml(keyword.title)}</a> <span class="graph-fallback-count">${escapeHtml(keyword.count)}</span></li>`
    )).join("");
    const keywordSection = keywordPages
      ? `<h3>Keyword pages</h3><ul class="graph-fallback-links">${keywordPages}</ul>`
      : "";

    fallback.innerHTML = `
      <h2>${escapeHtml(title)}</h2>
      <p>This topic has ${escapeHtml(nodeCount)} nodes. Direct graph expansion is capped at ${escapeHtml(graphLimit("maxExpandNodes"))} topic nodes and ${escapeHtml(graphLimit("maxVisibleNodes"))} visible nodes.</p>
      <p><a href="${escapeHtml(topic.href || "#")}">Open topic page</a></p>
      ${keywordSection}
      <button class="graph-fallback-back" type="button" data-action="topic-overview">Topic overview</button>
    `;
    fallback.hidden = false;
    fallback.querySelector("[data-action='topic-overview']")?.addEventListener("click", () => {
      renderTopicOverview(graphState.config).catch((error) => {
        fallback.innerHTML = `<p class="graph-error">${escapeHtml(error.message)}</p>`;
      });
    });
  }

  function updateProofPlanControls(visible) {
    const controls = document.getElementById("proof-plan-controls");
    if (!controls) return;
    controls.hidden = !visible;
    controls.querySelectorAll('input[name="proof-plan-mode"]').forEach((input) => {
      input.checked = input.value === currentProofPlanMode();
    });
  }

  function renderExpandedTopic(subgraph) {
    const graphElement = document.getElementById("graph");
    if (!graphElement || !subgraph?.topic) return;
    graphState.currentTopicSubgraph = subgraph;
    graphState.expandedTopic = subgraph.topic.id;
    graphElement.dataset.expandedTopic = subgraph.topic.id;
    if (exceedsTopicExpansionLimits(subgraph)) {
      graphElement.dataset.graphMode = "topic-fallback";
      updateProofPlanControls(false);
      showOversizedTopicFallback(subgraph);
      return;
    }
    graphElement.dataset.graphMode = "topic-expanded";
    updateProofPlanControls(true);
    renderDot(topicSubgraphToDot(subgraph));
  }

  function setProofPlanMode(mode) {
    if (!GRAPH_PROOF_PLAN_POLICIES.has(mode)) return;
    graphState.proofPlanMode = mode;
    updateProofPlanControls(Boolean(graphState.currentTopicSubgraph));
    if (graphState.currentTopicSubgraph) renderExpandedTopic(graphState.currentTopicSubgraph);
  }

  function renderNodePayload(payload) {
    const proof = payload.proof_html
      ? `<details class="proof-details"><summary>Proof</summary><div class="proof-body">${payload.proof_html}</div></details>`
      : "";
    return `
      <article class="thm ${escapeHtml(payload.kind)}_thmwrapper theorem-style-${escapeHtml(payload.kind)}">
        <header class="${escapeHtml(payload.kind)}_thmheading thm-heading">
          <span class="${escapeHtml(payload.kind)}_thmcaption thm-caption">${escapeHtml(payload.kind.replace(/-/g, " "))}</span>
          <span class="${escapeHtml(payload.kind)}_thmtitle thm-title">${escapeHtml(payload.title)}</span>
          <span class="thm-status thm-status-${escapeHtml(payload.status)}">${escapeHtml(payload.status)}</span>
        </header>
        <div class="${escapeHtml(payload.kind)}_thmcontent thm-content">
          <div class="body graph-modal-body">${payload.body_html}${proof}</div>
          <p><a href="${escapeHtml(payload.href)}">Open node page</a></p>
          ${renderLinkList("Uses", payload.deps)}
          ${renderLinkList("Used by", payload.dependents)}
          ${renderLeanRefs(payload.lean_refs)}
        </div>
      </article>
    `;
  }

  function rerenderMath(element) {
    if (typeof window.renderMathInElement === "function") {
      window.renderMathInElement(element, window.MDBLUEPRINT_MATH_OPTIONS || {});
    }
  }

  function nodePayloadUrl(nodeId) {
    return graphState.nodePayloadUrls.get(nodeId) || `node_payloads/${nodeId.replace(/\./g, "_")}.json`;
  }

  async function fetchNodePayload(nodeId) {
    if (graphState.nodePayloadCache.has(nodeId)) {
      return graphState.nodePayloadCache.get(nodeId);
    }
    const response = await fetch(nodePayloadUrl(nodeId));
    if (!response.ok) throw new Error(`Unable to load node details for ${nodeId}`);
    const payload = await response.json();
    graphState.nodePayloadCache.set(nodeId, payload);
    return payload;
  }

  async function showNodeDetail(nodeId) {
    const modal = document.getElementById("node-detail-modal");
    const content = document.getElementById("node-detail-content");
    if (!modal || !content) return;
    content.textContent = "Loading...";
    showGraphModalElement(modal);
    try {
      const payload = await fetchNodePayload(nodeId);
      content.innerHTML = renderNodePayload(payload);
      rerenderMath(content);
    } catch (error) {
      content.innerHTML = `<p class="graph-error">${escapeHtml(error.message)}</p>`;
    }
  }

  function graphvizRenderer(graphElement) {
    if (graphRenderer) return graphRenderer;
    const width = graphElement.clientWidth || 960;
    const height = graphElement.clientHeight || 720;
    graphRenderer = window.d3.select("#graph")
      .graphviz({ useWorker: true })
      .width(width)
      .height(height)
      .fit(true);
    return graphRenderer;
  }

  function renderDot(dot) {
    const graphElement = document.getElementById("graph");
    if (!graphElement || !window.d3) return;
    hideGraphFallback();
    graphElement.replaceChildren();
    graphRenderer = null;
    graphvizRenderer(graphElement)
      .on("end", bindGraphInteractions)
      .renderDot(dot);
  }

  function normalizeGraphConfig(config) {
    const raw = config || {};
    const proofPlans = GRAPH_PROOF_PLAN_POLICIES.has(raw.proofPlans)
      ? raw.proofPlans
      : GRAPH_DEFAULT_CONFIG.proofPlans;
    const positiveInteger = (value, fallback) => (
      Number.isInteger(value) && value > 0 ? value : fallback
    );
    return {
      ...raw,
      maxVisibleNodes: positiveInteger(raw.maxVisibleNodes, GRAPH_DEFAULT_CONFIG.maxVisibleNodes),
      maxExpandNodes: positiveInteger(raw.maxExpandNodes, GRAPH_DEFAULT_CONFIG.maxExpandNodes),
      proofPlans,
    };
  }

  function readGraphConfig() {
    const configElement = document.getElementById("graph-config");
    if (!configElement) return null;
    try {
      return normalizeGraphConfig(JSON.parse(configElement.textContent || "{}"));
    } catch (error) {
      return null;
    }
  }

  async function renderTopicOverview(config) {
    const graphElement = document.getElementById("graph");
    if (!graphElement || !config?.topicOverviewUrl) return;
    const response = await fetch(config.topicOverviewUrl);
    if (!response.ok) throw new Error(`Unable to load ${config.topicOverviewUrl}`);
    const data = await response.json();
    graphState.config = config;
    if (!GRAPH_PROOF_PLAN_POLICIES.has(graphState.proofPlanMode)) {
      graphState.proofPlanMode = config.proofPlans;
    }
    graphState.topicOverview = data;
    graphState.expandedTopic = null;
    graphState.currentTopicSubgraph = null;
    graphElement.dataset.graphMode = "topic-overview";
    delete graphElement.dataset.expandedTopic;
    updateProofPlanControls(false);
    renderDot(topicOverviewToDot(data));
  }

  async function fetchTopicSubgraph(topicId) {
    if (graphState.topicCache.has(topicId)) {
      return graphState.topicCache.get(topicId);
    }
    const baseUrl = graphState.config?.topicSubgraphBaseUrl || "subgraphs/topics";
    const response = await fetch(`${baseUrl}/${encodeURIComponent(topicId)}.json`);
    if (!response.ok) throw new Error(`Unable to load topic ${topicId}`);
    const data = await response.json();
    (data.nodes || []).forEach((node) => {
      if (node.payload) graphState.nodePayloadUrls.set(node.id, node.payload);
    });
    graphState.topicCache.set(topicId, data);
    return data;
  }

  async function handleTopicActivation(topicId) {
    const graphElement = document.getElementById("graph");
    if (!graphElement) return;
    try {
      if (graphState.expandedTopic === topicId) {
        graphState.expandedTopic = null;
        graphState.currentTopicSubgraph = null;
        graphElement.dataset.graphMode = "topic-overview";
        delete graphElement.dataset.expandedTopic;
        updateProofPlanControls(false);
        renderDot(topicOverviewToDot(graphState.topicOverview));
        return;
      }
      const subgraph = await fetchTopicSubgraph(topicId);
      renderExpandedTopic(subgraph);
    } catch (error) {
      hideGraphFallback();
      graphElement.textContent = error.message;
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    document.querySelector("#legend-title")?.addEventListener("click", () => {
      document.querySelector("#legend-list")?.toggleAttribute("hidden");
    });
    document.querySelectorAll(".dep-closebtn").forEach((button) => {
      button.addEventListener("click", closeGraphModals);
    });
    document.querySelectorAll(".modal-trigger").forEach((button) => {
      button.addEventListener("click", () => openNodeModal(button.getAttribute("data-modal-target")));
    });
    document.querySelectorAll(".closebtn").forEach((button) => {
      button.addEventListener("click", () => closeNodeModal(button));
    });
    document.getElementById("proof-plan-controls")?.addEventListener("change", (event) => {
      const target = event.target;
      if (target?.matches?.('input[name="proof-plan-mode"]')) {
        setProofPlanMode(target.value);
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeGraphModals();
        document.querySelectorAll(".modal-container").forEach((modal) => {
          modal.hidden = true;
        });
      }
    });

    const graphElement = document.getElementById("graph");
    const config = readGraphConfig();
    if (!graphElement || !config || !window.d3) return;
    renderTopicOverview(config).catch((error) => {
      graphElement.textContent = error.message;
    });
  });
})();
