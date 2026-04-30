"""Louvain community detection for entity grouping."""

import networkx as nx
try:
    import community as community_louvain  # python-louvain package
    _LOUVAIN_AVAILABLE = True
except ImportError:
    _LOUVAIN_AVAILABLE = False


def assign_communities(entities: list[dict]) -> dict[str, int]:
    """Assign community IDs to entities based on their relations.

    Args:
        entities: List of entity dicts with 'id' and 'relations' keys.
                  Each relation dict has 'target_id' key.

    Returns:
        Mapping of entity_id -> community_id.
    """
    if not entities:
        return {}

    # Build graph from entity relations
    G = nx.Graph()
    entity_ids = set()

    for entity in entities:
        eid = entity["id"]
        entity_ids.add(eid)
        G.add_node(eid)

        for rel in entity.get("relations", []):
            target = rel.get("target_id", "")
            if target and target != eid:
                weight = rel.get("confidence", 0.5)
                G.add_edge(eid, target, weight=weight)

    if G.number_of_edges() == 0:
        # No relations, each entity is its own community
        return {eid: i for i, eid in enumerate(sorted(entity_ids))}

    # Run Louvain community detection
    if _LOUVAIN_AVAILABLE:
        partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    else:
        # Fallback: simple connected components
        components = list(nx.connected_components(G))
        partition = {}
        for i, comp in enumerate(components):
            for node in comp:
                partition[node] = i
        # Add isolated nodes
        for node in G.nodes():
            if node not in partition:
                partition[node] = len(components) + list(G.nodes()).index(node)

    return partition
