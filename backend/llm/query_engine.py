#!/usr/bin/env python3
"""
LLM Query Engine for GBDM Query System.
Translates natural language queries to SQL using Groq API.
"""
import os
import re
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from groq import Groq
from database import get_schema_description, execute_query
from llm.guardrails import validate_sql, is_domain_relevant, sanitize_for_prompt

# Initialize Groq client
client = None


def get_client():
    global client
    if client is None:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        client = Groq(api_key=api_key)
    return client


SYSTEM_PROMPT_TEMPLATE = """You are a data analyst assistant for an SAP Order-to-Cash (O2C) system. 
You help users query business data by translating their natural language questions into SQL queries.

{schema}

CRITICAL JOIN RULES:
- billing_document_items.referenceSdDocument references outbound_delivery_headers.deliveryDocument (NOT sales orders!)
- outbound_delivery_items.referenceSdDocument references sales_order_headers.salesOrder
- billing_document_headers.accountingDocument references journal_entry_items_accounts_receivable.accountingDocument
- journal_entry_items_accounts_receivable.referenceDocument references billing_document_headers.billingDocument
- sales_order_items.material references products.product
- billing_document_items.material references products.product
- To link products to billing, use: billing_document_items.material = products.product (DIRECT join, no intermediary needed)
- To link sales orders to deliveries: outbound_delivery_items.referenceSdDocument = sales_order_headers.salesOrder
- To link deliveries to billing: billing_document_items.referenceSdDocument = outbound_delivery_headers.deliveryDocument

EXAMPLE SQL QUERIES:

Example 1: Products with most billing documents
SELECT p.product, pd.productDescription, COUNT(DISTINCT bi.billingDocument) AS billing_count
FROM products p
JOIN product_descriptions pd ON p.product = pd.product
JOIN billing_document_items bi ON bi.material = p.product
GROUP BY p.product, pd.productDescription
ORDER BY billing_count DESC
LIMIT 10

Example 2: Trace full flow of a sales order
SELECT so.salesOrder, dh.deliveryDocument, bh.billingDocument, 
       bh.accountingDocument AS journal_doc, bh.totalNetAmount
FROM sales_order_headers so
LEFT JOIN outbound_delivery_items odi ON odi.referenceSdDocument = so.salesOrder
LEFT JOIN outbound_delivery_headers dh ON dh.deliveryDocument = odi.deliveryDocument
LEFT JOIN billing_document_items bi ON bi.referenceSdDocument = dh.deliveryDocument
LEFT JOIN billing_document_headers bh ON bh.billingDocument = bi.billingDocument
WHERE so.salesOrder = '740506'

Example 3: Sales orders with incomplete flows (delivered but not billed)
SELECT so.salesOrder, so.totalNetAmount, so.overallDeliveryStatus,
       odi.deliveryDocument
FROM sales_order_headers so
JOIN outbound_delivery_items odi ON odi.referenceSdDocument = so.salesOrder
LEFT JOIN billing_document_items bi ON bi.referenceSdDocument = odi.deliveryDocument
WHERE bi.billingDocument IS NULL

Example 4: Total billing per customer
SELECT bp.businessPartnerName, bp.customer,
       COUNT(DISTINCT bh.billingDocument) AS doc_count,
       SUM(CAST(bh.totalNetAmount AS REAL)) AS total_amount
FROM business_partners bp
JOIN billing_document_headers bh ON bp.customer = bh.soldToParty
WHERE bh.billingDocumentIsCancelled = 0
GROUP BY bp.businessPartnerName, bp.customer
ORDER BY total_amount DESC

Example 5: Plants with most deliveries
SELECT pl.plant, pl.plantName, COUNT(DISTINCT odi.deliveryDocument) AS delivery_count
FROM plants pl
JOIN outbound_delivery_items odi ON odi.plant = pl.plant
GROUP BY pl.plant, pl.plantName
ORDER BY delivery_count DESC
LIMIT 10

RULES:
1. ONLY generate SELECT queries. Never generate INSERT, UPDATE, DELETE, DROP, or any data-modifying SQL.
2. Always use the exact table and column names from the schema above.
3. When joining tables, use the CRITICAL JOIN RULES above. Follow the exact FK paths.
4. For monetary amounts, they are in INR (Indian Rupees). Cast to REAL for arithmetic: CAST(totalNetAmount AS REAL).
5. The billingDocumentIsCancelled field is 0 (false) or 1 (true).
6. When asked about "broken" or "incomplete" flows, use LEFT JOINs and check for NULL.
7. Keep queries efficient — use appropriate JOINs and WHERE clauses.
8. Limit results to 50 rows max unless the user asks for all.
9. ALWAYS respond in the exact JSON format specified below.

RESPONSE FORMAT:
You MUST respond with valid JSON in this exact format:
{{
  "sql": "SELECT ... FROM ... WHERE ...",
  "explanation": "Brief explanation of what the query does",
  "answer_template": "A template for the natural language answer using {{results}} placeholder"
}}

If the question cannot be answered with SQL, respond with:
{{
  "sql": null,
  "explanation": "Why this cannot be answered",
  "answer_template": "I cannot answer this question because..."
}}
"""


def generate_sql(user_query: str, conversation_history: list = None) -> dict:
    """
    Generate SQL from a natural language query using Groq.
    Returns dict with sql, explanation, raw_results, answer, referenced_nodes.
    """
    # Check domain relevance
    is_relevant, rejection_msg = is_domain_relevant(user_query)
    if not is_relevant:
        return {
            "sql": None,
            "explanation": "Query rejected by guardrails",
            "raw_results": [],
            "answer": rejection_msg,
            "referenced_nodes": [],
        }

    # Sanitize input
    sanitized_query = sanitize_for_prompt(user_query)

    # Build schema context
    schema_desc = get_schema_description()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema=schema_desc)

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history if available
    if conversation_history:
        for msg in conversation_history[-6:]:  # Last 3 exchanges
            messages.append(msg)

    messages.append({"role": "user", "content": sanitized_query})

    try:
        # Call Groq API
        groq_client = get_client()
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )

        response_text = response.choices[0].message.content

        # Parse LLM response
        try:
            llm_result = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                llm_result = json.loads(json_match.group())
            else:
                return {
                    "sql": None,
                    "explanation": "Failed to parse LLM response",
                    "raw_results": [],
                    "answer": "I had trouble understanding the response. Please try rephrasing your question.",
                    "referenced_nodes": [],
                }

        sql = llm_result.get("sql")
        explanation = llm_result.get("explanation", "")

        if not sql:
            return {
                "sql": None,
                "explanation": explanation,
                "raw_results": [],
                "answer": llm_result.get("answer_template", "I couldn't generate a query for this question."),
                "referenced_nodes": [],
            }

        # Validate SQL
        is_valid, error = validate_sql(sql)
        if not is_valid:
            return {
                "sql": sql,
                "explanation": f"SQL validation failed: {error}",
                "raw_results": [],
                "answer": f"The generated query was not safe to execute: {error}",
                "referenced_nodes": [],
            }

        # Execute SQL with one retry
        try:
            results = execute_query(sql)
        except Exception as e:
            # Retry: send the error back to the LLM for correction
            try:
                retry_msg = f"The SQL query failed with error: {str(e)}\nPlease fix the SQL and respond with the corrected JSON."
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": retry_msg})
                retry_response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.1,
                    max_tokens=2048,
                    response_format={"type": "json_object"},
                )
                retry_result = json.loads(retry_response.choices[0].message.content)
                retry_sql = retry_result.get("sql")
                if retry_sql:
                    is_valid2, error2 = validate_sql(retry_sql)
                    if is_valid2:
                        results = execute_query(retry_sql)
                        sql = retry_sql
                        explanation = retry_result.get("explanation", explanation)
                    else:
                        raise Exception(f"Retry SQL also invalid: {error2}")
                else:
                    raise Exception("Retry produced no SQL")
            except Exception as e2:
                return {
                    "sql": sql,
                    "explanation": explanation,
                    "raw_results": [],
                    "answer": f"Query execution failed: {str(e)}. The question might need to be rephrased.",
                    "referenced_nodes": [],
                }

        # Generate natural language answer
        answer = generate_nl_answer(sanitized_query, sql, results, explanation)

        # Extract referenced node IDs and edges
        referenced_nodes = extract_referenced_nodes(results)
        referenced_edges = extract_referenced_edges(referenced_nodes)

        return {
            "sql": sql,
            "explanation": explanation,
            "raw_results": results[:50],  # Cap at 50
            "answer": answer,
            "referenced_nodes": referenced_nodes,
            "referenced_edges": referenced_edges,
        }

    except Exception as e:
        return {
            "sql": None,
            "explanation": f"LLM API error: {str(e)}",
            "raw_results": [],
            "answer": f"I encountered an error while processing your question: {str(e)}",
            "referenced_nodes": [],
        }


def generate_nl_answer(query: str, sql: str, results: list, explanation: str) -> str:
    """Generate a natural language answer from SQL results using Groq."""
    if not results:
        return "No results found for your query. The data might not contain matching records."

    # For simple results, format directly
    if len(results) <= 5 and len(results[0]) <= 3:
        return format_simple_results(query, results)

    # For complex results, use LLM
    try:
        groq_client = get_client()
        results_preview = results[:20]  # Limit for token efficiency

        answer_prompt = f"""Given this user question: "{query}"
And these SQL query results (showing {len(results)} rows total):
{json.dumps(results_preview, indent=2, default=str)}

Provide a clear, concise natural language answer. Key rules:
- Be specific with numbers and document IDs
- If there are many results, summarize the key findings
- Bold important values using **value** syntax
- Keep it under 200 words
- Do NOT include any SQL in your response
- Do NOT say "based on the query results" — just give the answer directly"""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a concise data analyst. Give direct answers."},
                {"role": "user", "content": answer_prompt},
            ],
            temperature=0.2,
            max_tokens=512,
        )
        return response.choices[0].message.content
    except Exception:
        return format_simple_results(query, results)


def format_simple_results(query: str, results: list) -> str:
    """Format simple query results as text."""
    if not results:
        return "No results found."

    if len(results) == 1 and len(results[0]) == 1:
        key = list(results[0].keys())[0]
        return f"The answer is **{results[0][key]}**."

    lines = []
    for i, row in enumerate(results[:10]):
        parts = [f"**{v}**" if isinstance(v, (int, float)) else str(v) for v in row.values()]
        lines.append(f"{i+1}. {' — '.join(parts)}")

    if len(results) > 10:
        lines.append(f"... and {len(results) - 10} more results.")

    return "\n".join(lines)


def extract_referenced_nodes(results: list) -> list:
    """Extract node references from query results for graph highlighting."""
    nodes = []
    id_fields = {
        "salesOrder": "SalesOrder",
        "deliveryDocument": "Delivery",
        "billingDocument": "BillingDocument",
        "accountingDocument": "JournalEntry",
        "businessPartner": "Customer",
        "customer": "Customer",
        "soldToParty": "Customer",
        "product": "Product",
        "material": "Product",
        "plant": "Plant",
    }

    seen = set()
    for row in results[:20]:  # Limit to first 20 rows
        for field, node_type in id_fields.items():
            if field in row and row[field]:
                node_id = f"{node_type}:{row[field]}"
                if node_id not in seen:
                    seen.add(node_id)
                    nodes.append({"id": node_id, "type": node_type})

    return nodes


def extract_referenced_edges(referenced_nodes: list) -> list:
    """Given referenced node IDs, find all graph edges connecting them."""
    if not referenced_nodes:
        return []

    node_ids = {n["id"] for n in referenced_nodes}
    edges = []
    seen = set()

    try:
        from graph.graph_builder import build_full_graph
        graph = build_full_graph()
        for link in graph["links"]:
            src = link["source"] if isinstance(link["source"], str) else link["source"]["id"]
            tgt = link["target"] if isinstance(link["target"], str) else link["target"]["id"]
            if src in node_ids and tgt in node_ids:
                edge_key = f"{src}->{tgt}"
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append({
                        "source": src,
                        "target": tgt,
                        "type": link["type"],
                    })
    except Exception as e:
        print(f"Error extracting referenced edges: {e}")

    return edges
