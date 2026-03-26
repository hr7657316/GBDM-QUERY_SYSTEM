#!/usr/bin/env python3
"""
Guardrails for GBDM Query System.
Validates and restricts queries to the O2C dataset domain.
"""
import re

# Allowed tables
ALLOWED_TABLES = {
    "sales_order_headers",
    "sales_order_items",
    "sales_order_schedule_lines",
    "outbound_delivery_headers",
    "outbound_delivery_items",
    "billing_document_headers",
    "billing_document_items",
    "journal_entry_items_accounts_receivable",
    "payments_accounts_receivable",
    "business_partners",
    "business_partner_addresses",
    "products",
    "product_descriptions",
    "plants",
    "product_plants",
    "product_storage_locations",
    "customer_company_assignments",
    "customer_sales_area_assignments",
}

# Forbidden SQL keywords
FORBIDDEN_SQL = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE",
    "ATTACH", "DETACH", "VACUUM", "REINDEX", "REPLACE",
    "GRANT", "REVOKE", "EXEC", "EXECUTE",
]

# O2C domain keywords
DOMAIN_KEYWORDS = [
    "order", "sales", "delivery", "billing", "invoice", "payment",
    "customer", "product", "material", "plant", "journal", "entry",
    "document", "amount", "quantity", "ship", "deliver", "bill",
    "flow", "trace", "track", "status", "cancel", "incomplete",
    "broken", "pending", "o2c", "order to cash", "order-to-cash",
    "net amount", "currency", "inr", "account", "receivable",
    "partner", "business", "storage", "warehouse", "schedule",
    "which", "how many", "list", "show", "find", "get", "count",
    "total", "average", "maximum", "minimum", "top", "highest",
    "lowest", "most", "least", "between", "during", "date",
]


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    Validate a generated SQL query for safety.
    Returns (is_valid, error_message).
    """
    if not sql or not sql.strip():
        return False, "Empty SQL query"

    sql_upper = sql.strip().upper()

    # Must start with SELECT or WITH
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        return False, "Only SELECT queries are allowed"

    # Check for forbidden operations
    for word in FORBIDDEN_SQL:
        # Match as whole word to avoid false positives
        pattern = r'\b' + word + r'\b'
        if re.search(pattern, sql_upper):
            return False, f"Forbidden SQL operation: {word}"

    # Check for system tables
    if "SQLITE_MASTER" in sql_upper or "SQLITE_SCHEMA" in sql_upper:
        return False, "Access to system tables is not allowed"

    # Check for comments that might hide injections
    if "--" in sql or "/*" in sql:
        return False, "SQL comments are not allowed"

    return True, ""


def is_domain_relevant(query: str) -> tuple[bool, str]:
    """
    Check if a natural language query is relevant to the O2C domain.
    Returns (is_relevant, rejection_message).
    """
    query_lower = query.lower().strip()

    # Very short queries - probably not meaningful
    if len(query_lower) < 3:
        return False, "Please ask a more specific question about the Order-to-Cash data."

    # Check for explicit off-topic patterns
    off_topic_patterns = [
        r"(what is|define|explain)\s+(the\s+)?(meaning|definition|concept)\s+of",
        r"(who|what)\s+(is|are|was|were)\s+(the\s+)?(president|capital|population|weather|news)",
        r"\b(recipe|cook|weather|sports|movie|song|lyrics|poem|joke|riddle)\b",
        r"\b(write|compose|create)\s+(a\s+)?(story|poem|essay|letter|email|code|script)\b",
        r"\b(translate|convert)\s+.+\s+(to|into)\s+(french|spanish|german|hindi|chinese)",
        r"\b(ignore|forget|disregard)\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|context)",
        r"you\s+are\s+(now|a)\s+",
        r"(pretend|act|roleplay|imagine)\s+(you|that|as)",
        r"\b(hack|exploit|bypass|jailbreak)\b",
    ]

    for pattern in off_topic_patterns:
        if re.search(pattern, query_lower):
            return False, (
                "I can only answer questions about the SAP Order-to-Cash dataset. "
                "This includes sales orders, deliveries, billing documents, payments, "
                "customers, products, and plants. Please ask a relevant question."
            )

    # Check if query contains any domain keywords
    has_domain_keyword = any(kw in query_lower for kw in DOMAIN_KEYWORDS)

    # Check for data-oriented question patterns
    data_patterns = [
        r"\b(how many|count|total|sum|average|avg|max|min|list|show|find|get|fetch)\b",
        r"\b(which|what|where|when|who)\b.*\b(order|deliver|bill|pay|product|customer|plant)\b",
        r"\b(trace|track|follow|flow)\b",
        r"\b(incomplete|broken|missing|pending|cancelled)\b",
        r"\b(highest|lowest|most|least|top|bottom)\b",
        r"\b(between|from|to|during|before|after)\b.*\b(date|time|period)\b",
        r"\d{6,}",  # Document number patterns (6+ digits)
    ]

    has_data_pattern = any(re.search(p, query_lower) for p in data_patterns)

    if has_domain_keyword or has_data_pattern:
        return True, ""

    # If no domain keywords found but query seems like a question, give benefit of doubt
    if query_lower.startswith(("what", "which", "how", "where", "when", "who", "list", "show", "find", "get", "can")):
        return True, ""  # Let the LLM decide

    return False, (
        "I'm not sure this question is about the Order-to-Cash dataset. "
        "I can help with questions about sales orders, deliveries, billing documents, "
        "payments, customers, products, and plants. Could you rephrase your question?"
    )


def sanitize_for_prompt(text: str) -> str:
    """Sanitize user input to prevent prompt injection."""
    # Remove potential instruction-overriding patterns
    patterns_to_remove = [
        r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|context)",
        r"you\s+are\s+now\s+",
        r"system\s*:\s*",
        r"assistant\s*:\s*",
        r"```\s*(system|prompt)",
    ]
    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, "[REMOVED]", cleaned, flags=re.IGNORECASE)
    return cleaned
