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
    const dotElement = document.getElementById("graph-dot");
    if (!graphElement || !dotElement || !window.d3) return;

    const dot = dotElement.textContent;
    const width = graphElement.clientWidth || 960;
    const height = graphElement.clientHeight || 720;
    window.d3.select("#graph")
      .graphviz({ useWorker: true })
      .width(width)
      .height(height)
      .fit(true)
      .renderDot(dot)
      .on("end", bindGraphInteractions);
  });
})();
