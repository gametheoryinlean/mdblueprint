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

  const graphState = {
    config: null,
    topicOverview: null,
    topicCache: new Map(),
    expandedTopic: null,
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

  function topicSubgraphToDot(data) {
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
    (data.nodes || []).forEach((node) => {
      lines.push(`\t${dotQuote(node.id)} [${dotAttributes({
        color: statusColor(node.status),
        label: node.title,
        shape: shapeForKind(node.kind),
        style: node.kind === "proof-plan" ? "dashed" : null,
        URL: `#${node.id}`,
      })}];`);
    });
    (data.edges || []).forEach((edge) => {
      lines.push(`\t${dotQuote(edge.from)} -> ${dotQuote(edge.to)} [style=${dotQuote("dashed")}];`);
    });
    (data.boundary_edges || []).forEach((edge) => {
      const label = edge.count > 1 ? renderCountLabel(edge.count) : "";
      lines.push(`\t${dotQuote(edge.from)} -> ${dotQuote(edge.to)} [${dotAttributes({
        color: "#777777",
        label,
        style: "dashed",
      })}];`);
    });
    (data.proof_plan_attachments || []).forEach((edge) => {
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
    graphElement.replaceChildren();
    graphRenderer = null;
    graphvizRenderer(graphElement)
      .on("end", bindGraphInteractions)
      .renderDot(dot);
  }

  function readGraphConfig() {
    const configElement = document.getElementById("graph-config");
    if (!configElement) return null;
    try {
      return JSON.parse(configElement.textContent || "{}");
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
    graphState.topicOverview = data;
    graphState.expandedTopic = null;
    graphElement.dataset.graphMode = "topic-overview";
    delete graphElement.dataset.expandedTopic;
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
    graphState.topicCache.set(topicId, data);
    return data;
  }

  async function handleTopicActivation(topicId) {
    const graphElement = document.getElementById("graph");
    if (!graphElement) return;
    try {
      if (graphState.expandedTopic === topicId) {
        graphState.expandedTopic = null;
        graphElement.dataset.graphMode = "topic-overview";
        delete graphElement.dataset.expandedTopic;
        renderDot(topicOverviewToDot(graphState.topicOverview));
        return;
      }
      const subgraph = await fetchTopicSubgraph(topicId);
      graphState.expandedTopic = topicId;
      graphElement.dataset.graphMode = "topic-expanded";
      graphElement.dataset.expandedTopic = topicId;
      renderDot(topicSubgraphToDot(subgraph));
    } catch (error) {
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
