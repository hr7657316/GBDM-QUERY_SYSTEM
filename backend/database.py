#!/usr/bin/env python3
"""
Database module for GBDM Query System.
Handles SQLite connection management and schema introspection.
"""
import sqlite3
import os
from contextlib import contextmanager
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "o2c_data.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get a new SQLite connection with row factory."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(db_path: Optional[str] = None):
    """Context manager for database connections."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_schema_info(db_path: Optional[str] = None) -> dict:
    """
    Return full schema information for all tables.
    Used to provide context to the LLM.
    """
    schema = {}
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in cursor.fetchall()]

        for table in tables:
            # Get column info
            col_cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [
                {"name": row["name"], "type": row["type"], "notnull": row["notnull"]}
                for row in col_cursor.fetchall()
            ]

            # Get row count
            count_cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            row_count = count_cursor.fetchone()["cnt"]

            # Get sample rows (first 3)
            sample_cursor = conn.execute(f"SELECT * FROM {table} LIMIT 3")
            samples = [dict(row) for row in sample_cursor.fetchall()]

            schema[table] = {
                "columns": columns,
                "row_count": row_count,
                "sample_rows": samples,
            }

    return schema


def get_schema_description(db_path: Optional[str] = None) -> str:
    """
    Generate a natural language description of the schema for LLM context.
    """
    schema = get_schema_info(db_path)
    lines = [
        "DATABASE SCHEMA — SAP Order-to-Cash (O2C) System",
        "=" * 50,
        "",
        "This database contains SAP Order-to-Cash business data with the following tables:",
        "",
    ]

    table_descriptions = {
        "sales_order_headers": "Sales orders placed by customers. Key fields: salesOrder (PK), soldToParty (FK→business_partners.customer), totalNetAmount, overallDeliveryStatus, transactionCurrency.",
        "sales_order_items": "Line items within sales orders. Key fields: salesOrder+salesOrderItem (PK), material (FK→products.product), requestedQuantity, netAmount.",
        "sales_order_schedule_lines": "Delivery schedule for order items. Key fields: salesOrder+salesOrderItem+scheduleLine (PK), confirmedDeliveryDate.",
        "outbound_delivery_headers": "Deliveries shipped to customers. Key fields: deliveryDocument (PK), shippingPoint, overallGoodsMovementStatus.",
        "outbound_delivery_items": "Items in deliveries. Key fields: deliveryDocument+deliveryDocumentItem (PK), referenceSdDocument (FK→sales_order_headers.salesOrder), plant (FK→plants.plant).",
        "billing_document_headers": "Invoices/bills. Key fields: billingDocument (PK), soldToParty (FK→business_partners.customer), accountingDocument (FK→journal entries), totalNetAmount, billingDocumentIsCancelled.",
        "billing_document_items": "Line items in invoices. Key fields: billingDocument+billingDocumentItem (PK), material, referenceSdDocument (FK→outbound_delivery_headers.deliveryDocument), netAmount.",
        "journal_entry_items_accounts_receivable": "Accounting journal entries. Key fields: companyCode+fiscalYear+accountingDocument+accountingDocumentItem (PK), referenceDocument (FK→billing_document_headers.billingDocument), customer, amountInTransactionCurrency, clearingAccountingDocument.",
        "payments_accounts_receivable": "Customer payments. Key fields: companyCode+fiscalYear+accountingDocument+accountingDocumentItem (PK), clearingAccountingDocument, customer, amountInTransactionCurrency.",
        "business_partners": "Customers/business partners. Key fields: businessPartner (PK), customer, businessPartnerName.",
        "business_partner_addresses": "Addresses for business partners. Key fields: businessPartner+addressId (PK), cityName, country, streetName, postalCode.",
        "products": "Products/materials. Key fields: product (PK), productType, grossWeight, netWeight, baseUnit.",
        "product_descriptions": "Product names/descriptions. Key fields: product+language (PK), productDescription.",
        "plants": "Manufacturing/warehouse plants. Key fields: plant (PK), plantName, salesOrganization.",
        "product_plants": "Product-plant assignments. Key fields: product+plant (PK), profitCenter.",
        "product_storage_locations": "Storage locations for products. Key fields: product+plant+storageLocation (PK).",
        "customer_company_assignments": "Customer-company code mappings. Key fields: customer+companyCode (PK), reconciliationAccount.",
        "customer_sales_area_assignments": "Customer sales area config. Key fields: customer+salesOrganization+distributionChannel+division (PK), currency, customerPaymentTerms.",
    }

    for table, info in schema.items():
        desc = table_descriptions.get(table, "")
        col_names = [c["name"] for c in info["columns"]]
        lines.append(f"TABLE: {table} ({info['row_count']} rows)")
        if desc:
            lines.append(f"  Description: {desc}")
        lines.append(f"  Columns: {', '.join(col_names)}")
        lines.append("")

    lines.extend(
        [
            "",
            "KEY RELATIONSHIPS (Order-to-Cash Flow):",
            "  Customer (business_partners.customer) → Sales Order (sales_order_headers.soldToParty)",
            "  Sales Order → Sales Order Items (salesOrder FK)",
            "  Sales Order Item → Product (material = product)",
            "  Sales Order → Delivery (outbound_delivery_items.referenceSdDocument = salesOrder)",
            "  Delivery → Delivery Items (deliveryDocument FK)",
            "  Delivery Item → Plant (plant FK)",
            "  Delivery → Billing Document (billing_document_items.referenceSdDocument = deliveryDocument)",
            "  Billing Document → Billing Items (billingDocument FK)",
            "  Billing Document → Journal Entry (accountingDocument = accountingDocument)",
            "  Journal Entry → Payment (clearingAccountingDocument = clearingAccountingDocument)",
            "",
            "IMPORTANT NOTES:",
            "  - 14 sales orders have no delivery yet (pending)",
            "  - 3 delivered orders have no billing yet (incomplete flow)",
            "  - 40 billing docs have no matching journal entry (not yet posted)",
            "  - 80 billing documents are cancelled (billingDocumentIsCancelled=true)",
            "  - Journal entry amounts can be negative (credit entries)",
            "  - All monetary amounts are in INR (Indian Rupees)",
        ]
    )

    return "\n".join(lines)


def execute_query(sql: str, db_path: Optional[str] = None) -> list[dict]:
    """Execute a read-only SQL query and return results as list of dicts."""
    # Safety check - only allow SELECT
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        raise ValueError("Only SELECT queries are allowed")

    forbidden = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "ATTACH"]
    for word in forbidden:
        if word in sql_upper:
            raise ValueError(f"Forbidden SQL operation: {word}")

    with get_db(db_path) as conn:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
