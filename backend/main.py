import time
import collections
from fastapi import FastAPI, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from backend.config import ALPHA
import backend.database as db
from backend.cache_ring import cache_manager
from backend.batch_writer import batch_writer
from backend.decay_worker import decay_worker

# Latency tracking queue (thread-safe deque)
latency_history = collections.deque(maxlen=1000)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown lifecycles of background workers and database verifications."""
    # Startup: Auto-seed database if the file or tables are missing
    import os
    import sqlite3
    from backend.config import DB_PATH
    
    # Ensure parent data directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    table_exists = False
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_queries';")
            if cursor.fetchone():
                table_exists = True
            conn.close()
        except Exception:
            pass
            
    if not table_exists:
        print("SQLite table 'search_queries' not found. Starting automatic seeder...")
        try:
            from backend.seed import generate_queries, apply_zipf_distribution, save_to_csv, seed_database
            raw_queries = generate_queries(120000)
            zipf_data = apply_zipf_distribution(raw_queries)
            save_to_csv(zipf_data)
            seed_database()
            print("Automatic database seeding completed successfully.")
        except Exception as e:
            print(f"CRITICAL: Failed to auto-seed database on server boot: {e}")

    batch_writer.start()
    decay_worker.start()
    yield
    # Shutdown
    batch_writer.stop()
    decay_worker.stop()

app = FastAPI(
    title="Search Typeahead API",
    description="Backend data system for high-throughput, low-latency search typeahead suggestions.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware config to allow React frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development ease, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global API states
ranking_mode = "enhanced"  # Options: "basic", "enhanced"

class SearchRequest(BaseModel):
    query: str

class SuggestionResponse(BaseModel):
    query: str
    total_count: int
    recent_count: int
    score: Optional[float] = None

@app.get("/")
def read_root():
    return {
        "status": "online",
        "ranking_mode": ranking_mode,
        "api_docs": "/docs"
    }

@app.get("/suggest", response_model=List[Dict[str, Any]])
def get_suggestions(q: str = Query(default="", description="The query prefix typing input")):
    """Fetches top 10 prefix-matching suggestions. Serves from cache or falls back to DB."""
    start_time = time.perf_counter()
    prefix = q.strip().lower()
    
    if not prefix:
        return []
        
    try:
        # 1. Try reading from the distributed consistent hashing cache ring
        cached_result = cache_manager.get(prefix)
        if cached_result is not None:
            # Record latency for cache hit
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            latency_history.append(elapsed_ms)
            # Add hit flag in header or response metadata if needed, but return list directly for API contract
            return cached_result
            
        # 2. Cache Miss: Query the SQLite Database
        if ranking_mode == "enhanced":
            # Recency-aware sorted suggestions
            suggestions = db.get_enhanced_suggestions(prefix, ALPHA, limit=10)
        else:
            # Standard historical popularity suggestions
            suggestions = db.get_basic_suggestions(prefix, limit=10)
            
        # 3. Populate Cache Node
        cache_manager.set(prefix, suggestions)
        
        # Record latency for cache miss
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        latency_history.append(elapsed_ms)
        
        return suggestions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database or cache error: {str(e)}"
        )

@app.post("/search")
def submit_search(request: SearchRequest):
    """Submits a query, pushing it to the thread-safe buffer for batch writing."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    # Put query in write buffer (doesn't block client)
    batch_writer.add_search(query)
    return {"message": "Searched"}

@app.get("/cache/debug")
def debug_cache(prefix: str = Query(..., description="Query prefix to trace")):
    """Traces which cache node owns the key on the ring, and if it's currently a hit or miss."""
    clean_prefix = prefix.strip().lower()
    if not clean_prefix:
        raise HTTPException(status_code=400, detail="Prefix query parameter is required.")
        
    debug_info = cache_manager.get_debug_info(clean_prefix)
    return debug_info

@app.get("/trending")
def get_trending():
    """Fetches top 10 overall trending searches."""
    if ranking_mode == "enhanced":
        return db.get_trending_queries(ALPHA, limit=10)
    else:
        # Under basic mode, trending is just overall top searches
        conn = db.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT query_text, total_count, recent_count
                FROM search_queries
                ORDER BY total_count DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()
            return [{"query": row["query_text"], "total_count": row["total_count"], "recent_count": row["recent_count"]} for row in rows]
        finally:
            conn.close()

@app.get("/metrics")
def get_telemetry():
    """Returns real-time telemetry: cache hits/misses, batch writes reduction, and p95/p99 latency."""
    cache_stats = cache_manager.get_global_metrics()
    batch_stats = batch_writer.get_metrics()
    decay_stats = decay_worker.get_metrics()
    
    # Latency calculation
    latencies = list(latency_history)
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    
    sorted_latencies = sorted(latencies)
    p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)] if sorted_latencies else 0.0
    p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)] if sorted_latencies else 0.0
    
    return {
        "system_status": "active",
        "ranking_mode": ranking_mode,
        "latency_metrics_ms": {
            "avg": round(avg_lat, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "samples_count": len(latencies)
        },
        "cache_metrics": cache_stats,
        "batch_writer_metrics": batch_stats,
        "decay_metrics": decay_stats
    }

@app.post("/ranking/toggle")
def toggle_ranking_mode():
    """Toggles between Basic and Recency-Aware suggestion ranking. Flushes caches to prevent pollution."""
    global ranking_mode
    ranking_mode = "basic" if ranking_mode == "enhanced" else "enhanced"
    cache_manager.clear_all()  # Clear cache to immediately apply new scoring rules
    return {"message": "Ranking mode updated", "current_mode": ranking_mode}

@app.post("/search/flush")
def trigger_manual_flush():
    """Forces the batch writer buffer to flush to the SQLite database immediately (for testing)."""
    rows_affected = batch_writer.flush()
    return {"message": "Buffer manually flushed", "rows_affected": rows_affected}

@app.post("/decay/trigger")
def trigger_manual_decay():
    """Forces a decay epoch cycle immediately (for testing)."""
    rows_decayed = decay_worker.trigger_decay()
    return {"message": "Manual decay triggered", "rows_decayed": rows_decayed}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    # Bind to 0.0.0.0 when hosted in cloud environments (Render) to allow external routing,
    # and default to 127.0.0.1 when running locally.
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    reload = False if os.environ.get("PORT") else True
    uvicorn.run("backend.main:app", host=host, port=port, reload=reload)
