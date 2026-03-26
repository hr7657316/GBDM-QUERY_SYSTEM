#!/usr/bin/env python3
"""
FastAPI main application for GBDM Query System.
"""
import os
import sys
from typing import Optional
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from database import get_schema_info, execute_query
from graph.graph_builder import (
    build_full_graph,
    get_node_metadata,
    get_node_neighbors,
    get_graph_stats,
    NODE_TYPES,
)
from llm.query_engine import generate_sql

app = FastAPI(
    title="GBDM Query System",
    description="Graph-Based Data Modeling and Query System for SAP O2C Data",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache the graph to avoid rebuilding on every request
_graph_cache = None


def get_cached_graph():
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = build_full_graph()
    return _graph_cache


# ─── Models ───────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    conversation_history: Optional[list] = None


class ChatResponse(BaseModel):
    answer: str
    sql: Optional[str] = None
    explanation: Optional[str] = None
    raw_results: list = []
    referenced_nodes: list = []
    referenced_edges: list = []


# ─── Graph Endpoints ──────────────────────────────────────────────────────

@app.get("/api/graph/overview")
async def graph_overview():
    """Return the full graph data for visualization."""
    graph = get_cached_graph()
    return graph


@app.get("/api/graph/stats")
async def graph_stats():
    """Return graph statistics."""
    return get_graph_stats()


@app.get("/api/graph/node/{node_type}/{node_id}")
async def node_detail(node_type: str, node_id: str):
    """Get full metadata for a specific node."""
    if node_type not in NODE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown node type: {node_type}")
    result = get_node_metadata(node_type, node_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/graph/neighbors/{node_type}/{node_id}")
async def node_neighbors(node_type: str, node_id: str):
    """Get all neighboring nodes for expansion."""
    if node_type not in NODE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown node type: {node_type}")
    return get_node_neighbors(node_type, node_id)


@app.get("/api/graph/types")
async def node_types():
    """Return all node type configurations."""
    return {
        name: {"color": config["color"], "size": config["size"]}
        for name, config in NODE_TYPES.items()
    }


# ─── Chat Endpoint ────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a natural language query against the O2C data."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    result = generate_sql(
        request.query,
        conversation_history=request.conversation_history,
    )

    return ChatResponse(**result)


# ─── Schema Endpoint ──────────────────────────────────────────────────────

@app.get("/api/schema")
async def schema():
    """Return database schema information."""
    return get_schema_info()


# ─── Health Check ─────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "graph_loaded": _graph_cache is not None}


# ─── Serve Frontend ───────────────────────────────────────────────────────

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the frontend SPA."""
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
