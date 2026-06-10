"""
RDF Topology Extractor
======================
1. Load an RDF file (any rdflib-supported format)
2. Explore predicates to build a whitelist / blacklist
3. Extract structural topology into a NetworkX graph
4. Compute graph statistics
5. Visualize with matplotlib or export for Gephi / Cytoscape

Dependencies:
    pip install rdflib networkx matplotlib
    pip install pyvis          # optional – interactive HTML viz
    pip install pandas         # optional – stats as DataFrame
"""

from __future__ import annotations

import collections
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import rdflib
from rdflib import BNode, Literal, URIRef

# ─────────────────────────────────────────────
# 1.  LOAD
# ─────────────────────────────────────────────

def load_graph(path: str | Path, fmt: str | None = None) -> rdflib.Graph:
    """
    Load an RDF file.  fmt is auto-detected if omitted.
    Common values: 'turtle', 'xml', 'n3', 'nt', 'json-ld'
    """
    g = rdflib.Graph()
    g.parse(str(path), format=fmt)
    print(f"Loaded {len(g):,} triples from {path}")
    return g


# ─────────────────────────────────────────────
# 2.  EXPLORE PREDICATES
# ─────────────────────────────────────────────

def predicate_inventory(
    g: rdflib.Graph,
    top_n: int = 50,
) -> dict[str, int]:
    """
    Count how often each predicate is used and whether it points to
    a URI (structural candidate) or a Literal (descriptive).
    Returns a dict  {predicate_uri: count}  sorted by frequency.
    """
    counts: dict[str, dict] = {}

    for s, p, o in g:
        key = str(p)
        if key not in counts:
            counts[key] = {"total": 0, "to_uri": 0, "to_literal": 0, "to_bnode": 0}
        counts[key]["total"] += 1
        if isinstance(o, Literal):
            counts[key]["to_literal"] += 1
        elif isinstance(o, BNode):
            counts[key]["to_bnode"] += 1
        else:
            counts[key]["to_uri"] += 1

    sorted_preds = sorted(counts.items(), key=lambda x: -x[1]["total"])

    print(f"\n{'PREDICATE':<70} {'TOTAL':>8}  {'→URI':>7}  {'→LIT':>7}  {'→BN':>5}")
    print("─" * 100)
    for pred, c in sorted_preds[:top_n]:
        short = pred.split("/")[-1].split("#")[-1]
        print(f"  {pred:<68} {c['total']:>8,}  {c['to_uri']:>7,}  {c['to_literal']:>7,}  {c['to_bnode']:>5,}")

    return {p: c["total"] for p, c in sorted_preds}


# ─────────────────────────────────────────────
# 3.  BUILD NetworkX GRAPH
# ─────────────────────────────────────────────

def _label(node, g: rdflib.Graph) -> str:
    """Return a short human-readable label for a node."""
    if isinstance(node, BNode):
        return f"_:{str(node)[:8]}"
    uri = str(node)
    # try rdfs:label
    label_uri = URIRef("http://www.w3.org/2000/01/rdf-schema#label")
    for _, _, lbl in g.triples((node, label_uri, None)):
        return str(lbl)
    # fall back to local name
    return uri.split("/")[-1].split("#")[-1] or uri


def build_topology(
    g: rdflib.Graph,
    *,
    whitelist: list[str] | None = None,
    blacklist: list[str] | None = None,
    include_literals: bool = False,
    include_bnodes: bool = False,
    directed: bool = True,
) -> nx.DiGraph | nx.Graph:
    """
    Convert the RDF graph into a NetworkX graph.

    Filtering priority (most restrictive wins):
        whitelist – keep ONLY these predicates
        blacklist – drop these predicates  (applied after whitelist)

    Parameters
    ----------
    whitelist      : list of full predicate URIs to keep (None = keep all)
    blacklist      : list of full predicate URIs to drop (None = drop none)
    include_literals : if True, literal values become leaf nodes
    include_bnodes   : if True, blank nodes are kept as pass-through nodes
    directed         : True → DiGraph, False → Graph
    """
    nxg: nx.DiGraph | nx.Graph = nx.DiGraph() if directed else nx.Graph()

    wl = set(whitelist) if whitelist else None
    bl = set(blacklist) if blacklist else set()

    kept = skipped = 0

    for s, p, o in g:
        pred = str(p)

        # ── predicate filter ──────────────────────────────────────
        if wl is not None and pred not in wl:
            skipped += 1
            continue
        if pred in bl:
            skipped += 1
            continue

        # ── object type filter ────────────────────────────────────
        if isinstance(o, Literal) and not include_literals:
            skipped += 1
            continue
        if isinstance(o, BNode) and not include_bnodes:
            skipped += 1
            continue

        # ── add nodes & edge ──────────────────────────────────────
        s_id = str(s)
        o_id = str(o)

        if not nxg.has_node(s_id):
            nxg.add_node(s_id, label=_label(s, g), uri=s_id)
        if not nxg.has_node(o_id):
            nxg.add_node(o_id, label=_label(o, g), uri=o_id)

        # Multi-edges: aggregate predicate labels
        if nxg.has_edge(s_id, o_id):
            nxg[s_id][o_id]["predicates"].add(pred)
        else:
            nxg.add_edge(s_id, o_id, predicates={pred}, weight=1)
            nxg[s_id][o_id]["weight"] += 1

        kept += 1

    print(f"\nEdges kept: {kept:,}  |  skipped: {skipped:,}")
    print(f"Nodes: {nxg.number_of_nodes():,}  |  Edges: {nxg.number_of_edges():,}")
    return nxg


# ─────────────────────────────────────────────
# 4.  STATISTICS
# ─────────────────────────────────────────────

def graph_stats(nxg: nx.DiGraph | nx.Graph) -> dict:
    """
    Compute and print common graph topology statistics.
    Returns a dict with all metrics so you can process them further.
    """
    is_directed = nxg.is_directed()
    n = nxg.number_of_nodes()
    m = nxg.number_of_edges()

    stats: dict = {
        "nodes": n,
        "edges": m,
        "density": nx.density(nxg),
        "is_directed": is_directed,
    }

    # Degree
    if is_directed:
        in_deg  = dict(nxg.in_degree())
        out_deg = dict(nxg.out_degree())
        stats["avg_in_degree"]  = sum(in_deg.values())  / n if n else 0
        stats["avg_out_degree"] = sum(out_deg.values()) / n if n else 0
        stats["max_in_degree"]  = max(in_deg.values(),  default=0)
        stats["max_out_degree"] = max(out_deg.values(), default=0)
        # top hubs
        stats["top_in_hubs"]  = sorted(in_deg.items(),  key=lambda x: -x[1])[:10]
        stats["top_out_hubs"] = sorted(out_deg.items(), key=lambda x: -x[1])[:10]
    else:
        deg = dict(nxg.degree())
        stats["avg_degree"] = sum(deg.values()) / n if n else 0
        stats["max_degree"] = max(deg.values(), default=0)
        stats["top_hubs"]   = sorted(deg.items(), key=lambda x: -x[1])[:10]

    # Connected components (on undirected view)
    ug = nxg.to_undirected() if is_directed else nxg
    comps = list(nx.connected_components(ug))
    stats["num_components"]        = len(comps)
    stats["largest_component_size"] = max(len(c) for c in comps) if comps else 0

    # Only compute expensive metrics on the largest component if graph is manageable
    lcc = nxg.subgraph(max(comps, key=len)).copy() if comps else nxg
    if lcc.number_of_nodes() < 5_000:
        stats["avg_clustering"] = nx.average_clustering(ug)
        try:
            stats["diameter"] = nx.diameter(lcc.to_undirected() if is_directed else lcc)
        except nx.NetworkXError:
            stats["diameter"] = "N/A (disconnected)"
    else:
        stats["avg_clustering"] = "skipped (graph too large)"
        stats["diameter"]       = "skipped (graph too large)"

    # Print summary
    print("\n── Graph Statistics ─────────────────────────────────────")
    for k, v in stats.items():
        if k.startswith("top_"):
            continue   # printed separately below
        print(f"  {k:<30} {v}")

    if is_directed:
        print("\n  Top in-degree hubs:")
        for node, d in stats["top_in_hubs"]:
            print(f"    {d:>6}  {node}")
        print("\n  Top out-degree hubs:")
        for node, d in stats["top_out_hubs"]:
            print(f"    {d:>6}  {node}")
    else:
        print("\n  Top hubs:")
        for node, d in stats["top_hubs"]:
            print(f"    {d:>6}  {node}")

    return stats


# ─────────────────────────────────────────────
# 5.  VISUALISATION
# ─────────────────────────────────────────────

def visualize_matplotlib(
    nxg: nx.DiGraph | nx.Graph,
    max_nodes: int = 300,
    layout: str = "spring",   # spring | kamada_kawai | spectral
    figsize: tuple = (16, 12),
    output_path: str | None = None,
) -> None:
    """
    Quick static matplotlib plot.  Scales node size by degree.
    Only draws up to max_nodes (largest connected component).
    """
    ug = nxg.to_undirected() if nxg.is_directed() else nxg
    lcc_nodes = max(nx.connected_components(ug), key=len)
    sub = nxg.subgraph(lcc_nodes).copy()

    if sub.number_of_nodes() > max_nodes:
        # sample highest-degree nodes
        deg = sorted(dict(sub.degree()).items(), key=lambda x: -x[1])
        top_nodes = [n for n, _ in deg[:max_nodes]]
        sub = nxg.subgraph(top_nodes).copy()
        print(f"  Showing top {max_nodes} nodes by degree")

    layouts = {
        "spring":       nx.spring_layout,
        "kamada_kawai": nx.kamada_kawai_layout,
        "spectral":     nx.spectral_layout,
    }
    pos = layouts.get(layout, nx.spring_layout)(sub, seed=42)

    degrees = dict(sub.degree())
    node_sizes  = [20 + 5 * degrees.get(n, 1) for n in sub.nodes()]
    node_colors = [degrees.get(n, 1) for n in sub.nodes()]

    fig, ax = plt.subplots(figsize=figsize)
    nx.draw_networkx(
        sub, pos, ax=ax,
        node_size=node_sizes,
        node_color=node_colors,
        cmap=plt.cm.viridis,
        edge_color="#aaaaaa",
        width=0.5,
        alpha=0.85,
        with_labels=True,
        labels={n: sub.nodes[n].get("label", n)[:20] for n in sub.nodes()},
        font_size=6,
        arrows=nxg.is_directed(),
        arrowsize=8,
    )
    ax.set_title("RDF Topology (largest component)", fontsize=14)
    ax.axis("off")
    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"  Saved to {output_path}")
    else:
        plt.show()


def export_pyvis(
    nxg: nx.DiGraph | nx.Graph,
    output_html: str = "rdf_topology.html",
    max_nodes: int = 1_000,
) -> None:
    """
    Interactive HTML visualization via pyvis.
    pip install pyvis
    """
    try:
        from pyvis.network import Network
    except ImportError:
        print("pyvis not installed. Run: pip install pyvis")
        return

    ug = nxg.to_undirected() if nxg.is_directed() else nxg
    lcc_nodes = max(nx.connected_components(ug), key=len)
    sub = nxg.subgraph(lcc_nodes).copy()

    if sub.number_of_nodes() > max_nodes:
        deg = sorted(dict(sub.degree()).items(), key=lambda x: -x[1])
        top_nodes = [n for n, _ in deg[:max_nodes]]
        sub = nxg.subgraph(top_nodes).copy()

    net = Network(
        height="900px", width="100%",
        directed=nxg.is_directed(),
        bgcolor="#1a1a2e", font_color="white",
    )
    net.from_nx(sub)
    net.set_options("""
    {
      "physics": { "stabilization": { "iterations": 200 } },
      "nodes": { "font": { "size": 10 } }
    }
    """)
    net.show(output_html, notebook=False)
    print(f"  Saved interactive viz to {output_html}")


def export_gephi(nxg: nx.DiGraph | nx.Graph, path: str = "topology.gexf") -> None:
    """Export to GEXF for Gephi."""
    # pyvis and gephi need string-serialisable edge attrs
    export = nxg.copy()
    for u, v, d in export.edges(data=True):
        d["predicates"] = "|".join(d.get("predicates", set()))
    nx.write_gexf(export, path)
    print(f"  Saved GEXF to {path}")


# ─────────────────────────────────────────────
# EXAMPLE USAGE
# ─────────────────────────────────────────────

if __name__ == "__main__":

    # ── Step 1: load ──────────────────────────────────────────────
    rdf_g = load_graph("your_graph.ttl")   # change path / format

    # ── Step 2: explore predicates ───────────────────────────────
    inventory = predicate_inventory(rdf_g, top_n=60)

    # ── Step 3: decide your filter ───────────────────────────────
    #
    # OPTION A – blacklist (drop known descriptive predicates)
    BLACKLIST = [
        "http://schema.org/name",
        "http://schema.org/description",
        "http://schema.org/identifier",
        "http://schema.org/alternateName",
        "http://www.w3.org/2000/01/rdf-schema#label",
        "http://www.w3.org/2000/01/rdf-schema#comment",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
        # add more from the inventory output above…
    ]

    # OPTION B – whitelist (keep only known structural predicates)
    # WHITELIST = [
    #     "http://schema.org/memberOf",
    #     "http://schema.org/knows",
    #     "http://schema.org/worksFor",
    #     # add more…
    # ]

    # ── Step 4: build topology graph ─────────────────────────────
    topo = build_topology(
        rdf_g,
        blacklist=BLACKLIST,
        # whitelist=WHITELIST,      # swap in if using Option B
        include_literals=False,     # set True to keep literal leaf nodes
        include_bnodes=False,
        directed=True,
    )

    # ── Step 5: statistics ───────────────────────────────────────
    stats = graph_stats(topo)

    # ── Step 6: visualise ────────────────────────────────────────
    # Static matplotlib plot (good for quick checks)
    visualize_matplotlib(topo, max_nodes=300, layout="spring",
                         output_path="topology.png")

    # Interactive HTML (best for exploration)
    export_pyvis(topo, output_html="topology.html", max_nodes=1_000)

    # Export to Gephi for deeper analysis
    export_gephi(topo, path="topology.gexf")