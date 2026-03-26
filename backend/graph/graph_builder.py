#!/usr/bin/env python3
"""
Graph builder for GBDM Query System.
Constructs a graph representation from the SQLite database.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db, DB_PATH


# Node type configuration
NODE_TYPES = {
    "Customer": {
        "table": "business_partners",
        "id_field": "businessPartner",
        "label_field": "businessPartnerName",
        "color": "#ef4444",  # red
        "size": 8,
    },
    "SalesOrder": {
        "table": "sales_order_headers",
        "id_field": "salesOrder",
        "label_field": "salesOrder",
        "color": "#3b82f6",  # blue
        "size": 5,
    },
    "SalesOrderItem": {
        "table": "sales_order_items",
        "id_field": "salesOrder || '-' || salesOrderItem",
        "label_field": "salesOrder || '/' || salesOrderItem",
        "color": "#60a5fa",  # light blue
        "size": 3,
    },
    "Delivery": {
        "table": "outbound_delivery_headers",
        "id_field": "deliveryDocument",
        "label_field": "deliveryDocument",
        "color": "#10b981",  # green
        "size": 5,
    },
    "DeliveryItem": {
        "table": "outbound_delivery_items",
        "id_field": "deliveryDocument || '-' || deliveryDocumentItem",
        "label_field": "deliveryDocument || '/' || deliveryDocumentItem",
        "color": "#34d399",  # light green
        "size": 3,
    },
    "BillingDocument": {
        "table": "billing_document_headers",
        "id_field": "billingDocument",
        "label_field": "billingDocument",
        "color": "#f59e0b",  # amber
        "size": 5,
    },
    "BillingDocumentItem": {
        "table": "billing_document_items",
        "id_field": "billingDocument || '-' || billingDocumentItem",
        "label_field": "billingDocument || '/' || billingDocumentItem",
        "color": "#fbbf24",  # yellow
        "size": 3,
    },
    "JournalEntry": {
        "table": "journal_entry_items_accounts_receivable",
        "id_field": "accountingDocument",
        "label_field": "accountingDocument",
        "color": "#8b5cf6",  # purple
        "size": 5,
    },
    "Payment": {
        "table": "payments_accounts_receivable",
        "id_field": "accountingDocument",
        "label_field": "accountingDocument",
        "color": "#ec4899",  # pink
        "size": 5,
    },
    "Product": {
        "table": "products",
        "id_field": "product",
        "label_field": "product",
        "color": "#f97316",  # orange
        "size": 4,
    },
    "Plant": {
        "table": "plants",
        "id_field": "plant",
        "label_field": "plantName",
        "color": "#6b7280",  # gray
        "size": 4,
    },
}

# Edge definitions with SQL queries
EDGE_DEFINITIONS = [
    {
        "name": "PLACED_ORDER",
        "source_type": "Customer",
        "target_type": "SalesOrder",
        "query": """
            SELECT DISTINCT bp.businessPartner as source_id, so.salesOrder as target_id
            FROM business_partners bp
            JOIN sales_order_headers so ON bp.customer = so.soldToParty
        """,
    },
    {
        "name": "HAS_ITEM",
        "source_type": "SalesOrder",
        "target_type": "SalesOrderItem",
        "query": """
            SELECT salesOrder as source_id,
                   salesOrder || '-' || salesOrderItem as target_id
            FROM sales_order_items
        """,
    },
    {
        "name": "CONTAINS_PRODUCT",
        "source_type": "SalesOrderItem",
        "target_type": "Product",
        "query": """
            SELECT salesOrder || '-' || salesOrderItem as source_id,
                   material as target_id
            FROM sales_order_items
            WHERE material IN (SELECT product FROM products)
        """,
    },
    {
        "name": "FULFILLED_BY",
        "source_type": "SalesOrder",
        "target_type": "Delivery",
        "query": """
            SELECT DISTINCT di.referenceSdDocument as source_id,
                   di.deliveryDocument as target_id
            FROM outbound_delivery_items di
            WHERE di.referenceSdDocument IN (SELECT salesOrder FROM sales_order_headers)
        """,
    },
    {
        "name": "DELIVERY_HAS_ITEM",
        "source_type": "Delivery",
        "target_type": "DeliveryItem",
        "query": """
            SELECT deliveryDocument as source_id,
                   deliveryDocument || '-' || deliveryDocumentItem as target_id
            FROM outbound_delivery_items
        """,
    },
    {
        "name": "SHIPPED_FROM",
        "source_type": "DeliveryItem",
        "target_type": "Plant",
        "query": """
            SELECT deliveryDocument || '-' || deliveryDocumentItem as source_id,
                   plant as target_id
            FROM outbound_delivery_items
            WHERE plant IN (SELECT plant FROM plants)
        """,
    },
    {
        "name": "BILLED_FOR",
        "source_type": "Delivery",
        "target_type": "BillingDocument",
        "query": """
            SELECT DISTINCT bi.referenceSdDocument as source_id,
                   bi.billingDocument as target_id
            FROM billing_document_items bi
            WHERE bi.referenceSdDocument IN (SELECT deliveryDocument FROM outbound_delivery_headers)
        """,
    },
    {
        "name": "BILLING_HAS_ITEM",
        "source_type": "BillingDocument",
        "target_type": "BillingDocumentItem",
        "query": """
            SELECT billingDocument as source_id,
                   billingDocument || '-' || billingDocumentItem as target_id
            FROM billing_document_items
        """,
    },
    {
        "name": "POSTED_TO",
        "source_type": "BillingDocument",
        "target_type": "JournalEntry",
        "query": """
            SELECT DISTINCT bh.billingDocument as source_id,
                   je.accountingDocument as target_id
            FROM billing_document_headers bh
            JOIN journal_entry_items_accounts_receivable je
              ON bh.accountingDocument = je.accountingDocument
        """,
    },
    {
        "name": "CLEARED_BY",
        "source_type": "JournalEntry",
        "target_type": "Payment",
        "query": """
            SELECT DISTINCT je.accountingDocument as source_id,
                   p.accountingDocument as target_id
            FROM journal_entry_items_accounts_receivable je
            JOIN payments_accounts_receivable p
              ON je.clearingAccountingDocument = p.clearingAccountingDocument
            WHERE je.clearingAccountingDocument IS NOT NULL
              AND je.clearingAccountingDocument != ''
        """,
    },
    {
        "name": "BILLED_TO",
        "source_type": "Customer",
        "target_type": "BillingDocument",
        "query": """
            SELECT DISTINCT bp.businessPartner as source_id,
                   bh.billingDocument as target_id
            FROM business_partners bp
            JOIN billing_document_headers bh ON bp.customer = bh.soldToParty
        """,
    },
    {
        "name": "PRODUCED_AT",
        "source_type": "Product",
        "target_type": "Plant",
        "query": """
            SELECT DISTINCT product as source_id, plant as target_id
            FROM product_plants
            WHERE product IN (SELECT product FROM products)
              AND plant IN (SELECT plant FROM plants)
        """,
    },
]


def build_full_graph(db_path=None) -> dict:
    """
    Build the complete graph with all nodes and edges.
    Returns {nodes: [...], links: [...]} for react-force-graph.
    """
    nodes = []
    links = []
    node_set = set()

    with get_db(db_path) as conn:
        # Build nodes
        for node_type, config in NODE_TYPES.items():
            table = config["table"]
            id_field = config["id_field"]
            label_field = config["label_field"]

            query = f"SELECT DISTINCT {id_field} as node_id, {label_field} as label FROM {table}"
            try:
                cursor = conn.execute(query)
                for row in cursor.fetchall():
                    nid = f"{node_type}:{row['node_id']}"
                    if nid not in node_set:
                        node_set.add(nid)
                        nodes.append({
                            "id": nid,
                            "label": str(row["label"]),
                            "type": node_type,
                            "color": config["color"],
                            "size": config["size"],
                        })
            except Exception as e:
                print(f"Error building {node_type} nodes: {e}")

        # Build edges
        for edge_def in EDGE_DEFINITIONS:
            try:
                cursor = conn.execute(edge_def["query"])
                for row in cursor.fetchall():
                    source = f"{edge_def['source_type']}:{row['source_id']}"
                    target = f"{edge_def['target_type']}:{row['target_id']}"
                    if source in node_set and target in node_set:
                        links.append({
                            "source": source,
                            "target": target,
                            "type": edge_def["name"],
                        })
            except Exception as e:
                print(f"Error building {edge_def['name']} edges: {e}")

    return {"nodes": nodes, "links": links}


def get_node_metadata(node_type: str, node_id: str, db_path=None) -> dict:
    """Get full metadata for a specific node."""
    config = NODE_TYPES.get(node_type)
    if not config:
        return {"error": f"Unknown node type: {node_type}"}

    table = config["table"]
    id_field = config["id_field"]

    with get_db(db_path) as conn:
        # For composite IDs, need to handle differently
        if "||" in id_field:
            # Composite key - query all records from the table and filter
            cursor = conn.execute(f"SELECT *, {id_field} as _computed_id FROM {table}")
            rows = [dict(row) for row in cursor.fetchall() if str(row["_computed_id"]) == node_id]
            for r in rows:
                r.pop("_computed_id", None)
        else:
            cursor = conn.execute(f'SELECT * FROM {table} WHERE "{id_field}" = ?', (node_id,))
            rows = [dict(row) for row in cursor.fetchall()]

        if not rows:
            return {"error": f"Node not found: {node_type}:{node_id}"}

        # Count connections
        full_id = f"{node_type}:{node_id}"
        connection_count = 0
        for edge_def in EDGE_DEFINITIONS:
            if edge_def["source_type"] == node_type:
                try:
                    cursor = conn.execute(edge_def["query"])
                    connection_count += sum(
                        1 for row in cursor.fetchall()
                        if str(row["source_id"]) == node_id
                    )
                except:
                    pass
            if edge_def["target_type"] == node_type:
                try:
                    cursor = conn.execute(edge_def["query"])
                    connection_count += sum(
                        1 for row in cursor.fetchall()
                        if str(row["target_id"]) == node_id
                    )
                except:
                    pass

        return {
            "type": node_type,
            "id": node_id,
            "data": rows[0] if len(rows) == 1 else rows,
            "connections": connection_count,
        }


def get_node_neighbors(node_type: str, node_id: str, db_path=None) -> dict:
    """Get all neighboring nodes for a given node."""
    neighbors = {"nodes": [], "links": []}
    node_set = set()
    full_id = f"{node_type}:{node_id}"

    with get_db(db_path) as conn:
        for edge_def in EDGE_DEFINITIONS:
            try:
                cursor = conn.execute(edge_def["query"])
                for row in cursor.fetchall():
                    source = f"{edge_def['source_type']}:{row['source_id']}"
                    target = f"{edge_def['target_type']}:{row['target_id']}"

                    if source == full_id:
                        # This node is a source, target is a neighbor
                        neighbor_type = edge_def["target_type"]
                        neighbor_id = str(row["target_id"])
                        neighbor_full = target
                    elif target == full_id:
                        # This node is a target, source is a neighbor
                        neighbor_type = edge_def["source_type"]
                        neighbor_id = str(row["source_id"])
                        neighbor_full = source
                    else:
                        continue

                    if neighbor_full not in node_set:
                        node_set.add(neighbor_full)
                        config = NODE_TYPES[neighbor_type]
                        neighbors["nodes"].append({
                            "id": neighbor_full,
                            "label": neighbor_id,
                            "type": neighbor_type,
                            "color": config["color"],
                            "size": config["size"],
                        })
                    neighbors["links"].append({
                        "source": source,
                        "target": target,
                        "type": edge_def["name"],
                    })
            except Exception as e:
                pass

    return neighbors


def get_graph_stats(db_path=None) -> dict:
    """Get summary statistics of the graph."""
    graph = build_full_graph(db_path)
    type_counts = {}
    for node in graph["nodes"]:
        t = node["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    edge_type_counts = {}
    for link in graph["links"]:
        t = link["type"]
        edge_type_counts[t] = edge_type_counts.get(t, 0) + 1

    return {
        "total_nodes": len(graph["nodes"]),
        "total_edges": len(graph["links"]),
        "node_types": type_counts,
        "edge_types": edge_type_counts,
    }


if __name__ == "__main__":
    stats = get_graph_stats()
    print(f"Graph Statistics:")
    print(f"  Total nodes: {stats['total_nodes']}")
    print(f"  Total edges: {stats['total_edges']}")
    print(f"\n  Node types:")
    for t, c in sorted(stats["node_types"].items()):
        print(f"    {t}: {c}")
    print(f"\n  Edge types:")
    for t, c in sorted(stats["edge_types"].items()):
        print(f"    {t}: {c}")
