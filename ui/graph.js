let isGraphVisible = false;
let activeGraphSimulation = null;
let graphRequestController = null;

async function toggleKnowledgeGraph() {
    const overlay = document.getElementById("knowledge-graph-overlay");
    if (!overlay) return;

    isGraphVisible = !isGraphVisible;
    overlay.classList.toggle("hidden", !isGraphVisible);
    if (isGraphVisible) {
        await loadAndRenderGraph();
    } else {
        activeGraphSimulation?.stop();
        graphRequestController?.abort();
    }
}

function setGraphFilter(filter) {
    currentGraphFilter = filter;
    document.querySelectorAll(".graph-filter-btn").forEach((button) => {
        const active = button.getAttribute("data-graph-filter") === filter;
        button.className = active
            ? "graph-filter-btn border border-primary text-primary px-2 py-1 font-label-mono text-[10px]"
            : "graph-filter-btn border border-outline text-on-surface px-2 py-1 font-label-mono text-[10px]";
    });
    if (lastGraphData) {
        const container = document.getElementById("graph-svg-container");
        if (container) {
            renderGraph(getFilteredGraphData(lastGraphData), container);
        }
    }
}

function graphEndpointId(endpoint) {
    return typeof endpoint === "object" ? endpoint.id : endpoint;
}

function getFilteredGraphData(data) {
    const nodes = (data.nodes || []).filter((node) => {
        if (currentGraphFilter === "orphan") return Boolean(node.orphan);
        if (currentGraphFilter === "project") return node.type === "project";
        if (currentGraphFilter === "inbox") return node.type === "inbox";
        return true;
    }).map((node) => ({ ...node }));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const links = (data.links || []).map((link) => ({
        source: graphEndpointId(link.source),
        target: graphEndpointId(link.target),
        value: link.value || 1,
    })).filter((link) => nodeIds.has(link.source) && nodeIds.has(link.target));
    return { nodes, links };
}

async function loadAndRenderGraph() {
    const container = document.getElementById("graph-svg-container");
    if (!container) return;
    container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-primary font-label-mono">LOADING_GRAPH_DATA...</div>';

    graphRequestController?.abort();
    graphRequestController = new AbortController();
    const timeout = setTimeout(() => graphRequestController.abort(), 20_000);
    try {
        const baseUrl = await getHttpBaseUrl();
        const response = await fetch(`${baseUrl}/api/graph`, {
            signal: graphRequestController.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || "Graph load failed");
        lastGraphData = data;
        renderGraph(getFilteredGraphData(data), container);
    } catch (error) {
        const message = error?.name === "AbortError"
            ? "Graph request timed out"
            : error.toString();
        container.innerHTML = `<div class="absolute inset-0 flex items-center justify-center text-error font-label-mono">ERROR_LOADING_GRAPH: ${escapeHTML(message)}</div>`;
    } finally {
        clearTimeout(timeout);
    }
}

function renderGraph(data, container) {
    activeGraphSimulation?.stop();
    container.innerHTML = "";
    if (!window.d3) {
        container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-error font-label-mono">NOT_CONFIGURED: D3_FAILED_TO_LOAD</div>';
        return;
    }
    if (!data.nodes.length) {
        container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-on-surface-variant font-label-mono">NO_GRAPH_NODES_FOR_FILTER</div>';
        return;
    }

    const width = Math.max(container.clientWidth, 320);
    const height = Math.max(container.clientHeight, 320);
    const svg = window.d3.create("svg")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", [0, 0, width, height])
        .attr("style", "max-width: 100%; height: 100%;");
    const graphLayer = svg.append("g");
    svg.call(window.d3.zoom().on("zoom", (event) => {
        graphLayer.attr("transform", event.transform);
    }));

    const simulation = window.d3.forceSimulation(data.nodes)
        .force("link", window.d3.forceLink(data.links).id((node) => node.id).distance(80))
        .force("charge", window.d3.forceManyBody().strength(-120))
        .force("center", window.d3.forceCenter(width / 2, height / 2));
    activeGraphSimulation = simulation;

    const links = graphLayer.append("g")
        .attr("stroke", "#5a4136")
        .attr("stroke-opacity", 0.7)
        .selectAll("line")
        .data(data.links)
        .join("line")
        .attr("stroke-width", 1.5);
    const colorScale = window.d3.scaleOrdinal()
        .domain([1, 2, 3])
        .range(["#ff6600", "#00c853", "#00b0ff"]);
    const nodes = graphLayer.append("g")
        .attr("stroke", "#121212")
        .attr("stroke-width", 1.5)
        .selectAll("circle")
        .data(data.nodes)
        .join("circle")
        .attr("r", (node) => node.group === 2 ? 8 : (node.group === 3 ? 6 : (node.orphan ? 4 : 5)))
        .attr("fill", (node) => colorScale(node.group))
        .attr("opacity", (node) => node.orphan ? 0.72 : 1)
        .style("cursor", "pointer")
        .on("click", (event, node) => {
            event.stopPropagation();
            showGraphNotePreview(node);
        })
        .call(window.d3.drag()
            .on("start", (event, node) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                node.fx = node.x;
                node.fy = node.y;
            })
            .on("drag", (event, node) => {
                node.fx = event.x;
                node.fy = event.y;
            })
            .on("end", (event, node) => {
                if (!event.active) simulation.alphaTarget(0);
                node.fx = null;
                node.fy = null;
            }));
    const labels = graphLayer.append("g")
        .selectAll("text")
        .data(data.nodes)
        .join("text")
        .attr("dx", 10)
        .attr("dy", ".35em")
        .attr("font-family", "JetBrains Mono, monospace")
        .attr("font-size", "9px")
        .attr("fill", "#e2e2e2")
        .text((node) => node.label || node.id);
    nodes.append("title").text((node) => node.path || node.id);

    simulation.on("tick", () => {
        links
            .attr("x1", (link) => link.source.x)
            .attr("y1", (link) => link.source.y)
            .attr("x2", (link) => link.target.x)
            .attr("y2", (link) => link.target.y);
        nodes.attr("cx", (node) => node.x).attr("cy", (node) => node.y);
        labels.attr("x", (node) => node.x).attr("y", (node) => node.y);
    });
    container.appendChild(svg.node());
}

async function showGraphNotePreview(nodeData) {
    const preview = document.getElementById("graph-note-preview");
    const content = document.getElementById("graph-note-preview-content");
    if (!preview || !content) return;
    preview.classList.remove("hidden");
    content.innerHTML = '<div class="text-primary">LOADING_NOTE...</div>';
    try {
        const baseUrl = await getHttpBaseUrl();
        const response = await fetch(
            `${baseUrl}/api/note?path=${encodeURIComponent(nodeData.path || "")}`,
        );
        const note = await response.json();
        if (!response.ok) throw new Error(note.message || "Note load failed");
        const suggestions = (note.suggested_links || []).map((link) =>
            `<span class="border border-primary text-primary px-2 py-0.5">${escapeHTML(`[[${link}]]`)}</span>`
        ).join(" ");
        content.innerHTML = `
            <div class="space-y-1 border-b border-outline pb-3">
                <div class="text-primary font-label-caps text-label-caps break-words">${escapeHTML(note.title || nodeData.label || nodeData.id)}</div>
                <div class="text-on-surface-variant break-words">${escapeHTML(note.path || nodeData.path || "")}</div>
                <div class="text-on-surface-variant">DEGREE: ${escapeHTML(note.degree || 0)} / TYPE: ${escapeHTML(note.type || "note")}</div>
            </div>
            <div>
                <div class="text-primary font-label-mono text-[10px] mb-2">SUGGESTED_WIKILINKS</div>
                <div class="flex flex-wrap gap-1">${suggestions || '<span class="text-on-surface-variant">NONE</span>'}</div>
            </div>
            <pre class="whitespace-pre-wrap break-words text-[11px] leading-relaxed border border-outline p-3 max-h-[420px] overflow-y-auto">${escapeHTML(note.content || "")}</pre>
        `;
    } catch (error) {
        content.innerHTML = `<div class="text-error break-words">${escapeHTML(error.toString())}</div>`;
    }
}

window.toggleKnowledgeGraph = toggleKnowledgeGraph;
window.setGraphFilter = setGraphFilter;
window.showGraphNotePreview = showGraphNotePreview;
