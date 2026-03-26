#!/usr/bin/env python3
"""
Data ingestion script for GBDM Query System.
Reads all JSONL files from the sap-o2c-data directory and loads them into SQLite.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "sap-o2c-data"
DB_PATH = SCRIPT_DIR / "o2c_data.db"

# All entity folders in ingestion order
ENTITY_FOLDERS = [
    "business_partners",
    "business_partner_addresses",
    "customer_company_assignments",
    "customer_sales_area_assignments",
    "products",
    "product_descriptions",
    "plants",
    "product_plants",
    "product_storage_locations",
    "sales_order_headers",
    "sales_order_items",
    "sales_order_schedule_lines",
    "outbound_delivery_headers",
    "outbound_delivery_items",
    "billing_document_headers",
    "billing_document_items",
    "billing_document_cancellations",
    "journal_entry_items_accounts_receivable",
    "payments_accounts_receivable",
]

# Type mapping for known fields
BOOLEAN_FIELDS = {
    "businessPartnerIsBlocked",
    "isMarkedForArchiving",
    "isMarkedForDeletion",
    "billingDocumentIsCancelled",
    "completeDeliveryIsDefined",
    "poBoxIsWithoutNumber",
    "slsUnlmtdOvrdelivIsAllwd",
    "deletionIndicator",
}

# Fields that contain nested objects (like time) - flatten them
TIME_FIELDS = {"creationTime", "actualGoodsMovementTime"}


def flatten_record(record: dict) -> dict:
    """Flatten nested objects (like time fields) into simple values."""
    flat = {}
    for key, value in record.items():
        if key in TIME_FIELDS and isinstance(value, dict):
            # Convert {hours, minutes, seconds} to "HH:MM:SS" string
            if value:
                h = value.get("hours", 0)
                m = value.get("minutes", 0)
                s = value.get("seconds", 0)
                flat[key] = f"{h:02d}:{m:02d}:{s:02d}"
            else:
                flat[key] = None
        elif isinstance(value, dict):
            # Skip any other nested objects
            flat[key] = json.dumps(value)
        elif isinstance(value, bool):
            flat[key] = 1 if value else 0
        elif key in BOOLEAN_FIELDS and isinstance(value, (str, int)):
            flat[key] = 1 if value in (True, 1, "true", "True") else 0
        else:
            flat[key] = value
    return flat


def infer_sql_type(value) -> str:
    """Infer SQLite column type from a Python value."""
    if isinstance(value, bool):
        return "INTEGER"
    elif isinstance(value, int):
        return "INTEGER"
    elif isinstance(value, float):
        return "REAL"
    else:
        return "TEXT"


def load_jsonl_folder(folder_path: Path) -> list[dict]:
    """Load and flatten all JSONL records from a folder."""
    records = []
    for f in sorted(folder_path.iterdir()):
        if f.suffix == ".jsonl":
            with open(f, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        raw = json.loads(line)
                        records.append(flatten_record(raw))
    return records


def create_table(conn: sqlite3.Connection, table_name: str, records: list[dict]):
    """Create a table based on the schema of the first record."""
    if not records:
        print(f"  ⚠️  No records found for {table_name}, skipping.")
        return

    # Infer schema from first record
    first = records[0]
    columns = []
    for col_name, value in first.items():
        col_type = infer_sql_type(value)
        if col_name in BOOLEAN_FIELDS:
            col_type = "INTEGER"
        columns.append(f'"{col_name}" {col_type}')

    # Create table
    col_defs = ", ".join(columns)
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute(f"CREATE TABLE {table_name} ({col_defs})")

    # Batch insert
    col_names = list(first.keys())
    placeholders = ", ".join(["?"] * len(col_names))
    quoted_cols = ", ".join([f'"{c}"' for c in col_names])
    insert_sql = f"INSERT INTO {table_name} ({quoted_cols}) VALUES ({placeholders})"

    batch = []
    for record in records:
        row = tuple(record.get(c) for c in col_names)
        batch.append(row)

    conn.executemany(insert_sql, batch)
    print(f"  ✅ {table_name}: {len(batch)} rows inserted")


def merge_cancellations(
    headers: list[dict], cancellations: list[dict]
) -> list[dict]:
    """
    Merge billing_document_cancellations into billing_document_headers.
    Cancellations have the same schema — they are headers with isCancelled=true.
    We deduplicate by billingDocument ID.
    """
    header_ids = {r["billingDocument"] for r in headers}
    # Only add cancellations not already in headers
    new = [c for c in cancellations if c["billingDocument"] not in header_ids]
    if new:
        print(f"  📎 Added {len(new)} cancellation-only records to billing_document_headers")
    else:
        print(f"  📎 All {len(cancellations)} cancellations already in headers (deduplicated)")
    return headers + new


def create_indexes(conn: sqlite3.Connection):
    """Create indexes on all foreign key columns for fast graph queries."""
    indexes = [
        ("idx_so_headers_soldToParty", "sales_order_headers", "soldToParty"),
        ("idx_so_items_salesOrder", "sales_order_items", "salesOrder"),
        ("idx_so_items_material", "sales_order_items", "material"),
        ("idx_so_schedule_salesOrder", "sales_order_schedule_lines", "salesOrder"),
        ("idx_del_items_refDoc", "outbound_delivery_items", "referenceSdDocument"),
        ("idx_del_items_plant", "outbound_delivery_items", "plant"),
        ("idx_del_items_delDoc", "outbound_delivery_items", "deliveryDocument"),
        ("idx_bill_headers_soldTo", "billing_document_headers", "soldToParty"),
        ("idx_bill_headers_acctDoc", "billing_document_headers", "accountingDocument"),
        ("idx_bill_items_billDoc", "billing_document_items", "billingDocument"),
        ("idx_bill_items_refDoc", "billing_document_items", "referenceSdDocument"),
        ("idx_bill_items_material", "billing_document_items", "material"),
        ("idx_journal_acctDoc", "journal_entry_items_accounts_receivable", "accountingDocument"),
        ("idx_journal_refDoc", "journal_entry_items_accounts_receivable", "referenceDocument"),
        ("idx_journal_clearing", "journal_entry_items_accounts_receivable", "clearingAccountingDocument"),
        ("idx_journal_customer", "journal_entry_items_accounts_receivable", "customer"),
        ("idx_payments_clearing", "payments_accounts_receivable", "clearingAccountingDocument"),
        ("idx_payments_customer", "payments_accounts_receivable", "customer"),
        ("idx_bp_customer", "business_partners", "customer"),
        ("idx_bp_addr_bp", "business_partner_addresses", "businessPartner"),
        ("idx_prod_desc_product", "product_descriptions", "product"),
        ("idx_prod_plants_product", "product_plants", "product"),
        ("idx_prod_plants_plant", "product_plants", "plant"),
        ("idx_prod_storage_product", "product_storage_locations", "product"),
        ("idx_cust_company_customer", "customer_company_assignments", "customer"),
        ("idx_cust_sales_customer", "customer_sales_area_assignments", "customer"),
    ]

    for idx_name, table, column in indexes:
        try:
            conn.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table}("{column}")')
        except sqlite3.OperationalError as e:
            print(f"  ⚠️  Index {idx_name} failed: {e}")

    print(f"  ✅ Created {len(indexes)} indexes")


def main():
    print("=" * 60)
    print("GBDM Query System — Data Ingestion")
    print("=" * 60)

    if not DATA_DIR.exists():
        print(f"❌ Data directory not found: {DATA_DIR}")
        sys.exit(1)

    # Delete existing DB
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"🗑️  Removed existing database")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    print(f"\n📂 Reading from: {DATA_DIR}")
    print(f"💾 Writing to: {DB_PATH}\n")

    # Load and process billing cancellations specially
    bill_headers = None
    bill_cancels = None

    for folder_name in ENTITY_FOLDERS:
        folder_path = DATA_DIR / folder_name
        if not folder_path.exists():
            print(f"  ⚠️  Folder not found: {folder_name}")
            continue

        records = load_jsonl_folder(folder_path)

        if folder_name == "billing_document_headers":
            bill_headers = records
            continue  # Wait for cancellations
        elif folder_name == "billing_document_cancellations":
            bill_cancels = records
            # Now merge and insert
            merged = merge_cancellations(bill_headers, bill_cancels)
            create_table(conn, "billing_document_headers", merged)
            continue
        else:
            create_table(conn, folder_name, records)

    conn.commit()

    # Create indexes
    print(f"\n📑 Creating indexes...")
    create_indexes(conn)
    conn.commit()

    # Verify
    print(f"\n📊 Verification:")
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    total_rows = 0
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        total_rows += count
        print(f"  {table}: {count} rows")

    print(f"\n✅ Ingestion complete!")
    print(f"   Tables: {len(tables)}")
    print(f"   Total rows: {total_rows}")
    print(f"   Database: {DB_PATH} ({DB_PATH.stat().st_size / 1024:.0f} KB)")

    conn.close()


if __name__ == "__main__":
    main()
