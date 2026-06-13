import sqlite3
import os
import datetime
from backend.config import DB_PATH

def get_db_connection():
    """Returns a sqlite3 connection configured with performance parameters and WAL mode."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    return conn

def get_basic_suggestions(prefix: str, limit: int = 10):
    """Fetches top 10 prefix-matching suggestions sorted by total historical count."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # SQLite's LIKE is case-insensitive by default for ASCII characters.
        # We query with index support on query_text COLLATE NOCASE
        cursor.execute("""
            SELECT query_text, total_count, recent_count
            FROM search_queries 
            WHERE query_text LIKE ? 
            ORDER BY total_count DESC 
            LIMIT ?
        """, (f"{prefix}%", limit))
        rows = cursor.fetchall()
        return [{"query": row["query_text"], "total_count": row["total_count"], "recent_count": row["recent_count"]} for row in rows]
    finally:
        conn.close()

def get_enhanced_suggestions(prefix: str, alpha: float, limit: int = 10):
    """Fetches suggestions sorted by combining recency and historical popularity."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Calculate dynamic score: alpha * recent_count + (1 - alpha) * total_count
        cursor.execute("""
            SELECT query_text, total_count, recent_count,
                   (? * recent_count + ? * total_count) AS score
            FROM search_queries 
            WHERE query_text LIKE ? 
            ORDER BY score DESC 
            LIMIT ?
        """, (alpha, 1.0 - alpha, f"{prefix}%", limit))
        rows = cursor.fetchall()
        return [{"query": row["query_text"], "total_count": row["total_count"], "recent_count": row["recent_count"]} for row in rows]
    finally:
        conn.close()

def get_trending_queries(alpha: float, limit: int = 10):
    """Fetches top trending queries overall, weighted towards recent counts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Top scoring overall
        cursor.execute("""
            SELECT query_text, total_count, recent_count,
                   (? * recent_count + ? * total_count) AS score
            FROM search_queries 
            ORDER BY score DESC 
            LIMIT ?
        """, (alpha, 1.0 - alpha, limit))
        rows = cursor.fetchall()
        return [{"query": row["query_text"], "total_count": row["total_count"], "recent_count": row["recent_count"]} for row in rows]
    finally:
        conn.close()

def bulk_upsert_queries(queries_dict: dict):
    """Performs bulk upsert of search queries to reduce write pressure."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        data = []
        for query, count in queries_dict.items():
            # insert new queries or update existing ones
            data.append((query, count, count))
            
        cursor.executemany("""
            INSERT INTO search_queries (query_text, total_count, recent_count, last_searched_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(query_text) DO UPDATE SET
                total_count = total_count + excluded.total_count,
                recent_count = recent_count + excluded.recent_count,
                last_searched_at = datetime('now');
        """, data)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def decay_recent_counts(factor: float):
    """Decays the recent counts in database by multiplying with factor."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Optimization: only decay rows where recent_count > 0.
        # This keeps database write pressure low during decay worker ticks.
        cursor.execute("""
            UPDATE search_queries
            SET recent_count = CAST(recent_count * ? AS INTEGER)
            WHERE recent_count > 0
        """, (factor,))
        # Delete queries that have count = 0 and last_searched_at is very old,
        # but for safety, we keep them all. We also zero out items that decayed below 1.
        cursor.execute("""
            UPDATE search_queries
            SET recent_count = 0
            WHERE recent_count < 1 AND recent_count > 0
        """)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
