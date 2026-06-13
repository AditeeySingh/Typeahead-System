import time
import threading
from typing import Dict, Any
from backend.config import BATCH_FLUSH_INTERVAL, BATCH_MAX_SIZE
from backend.database import bulk_upsert_queries
from backend.cache_ring import cache_manager

class BatchQueryWriter:
    """Aggregates and flushes query-count updates to the database in batches to reduce write pressure."""
    def __init__(self):
        self.buffer: Dict[str, int] = {}
        self.lock = threading.Lock()
        
        # Telemetry metrics
        self.total_searches_received = 0
        self.total_db_writes = 0
        
        # Thread controller
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None

    def add_search(self, query: str):
        """Adds a query submission to the buffer. Performs local aggregation."""
        query = query.strip().lower()
        if not query:
            return
            
        with self.lock:
            self.total_searches_received += 1
            self.buffer[query] = self.buffer.get(query, 0) + 1
            buffer_size = len(self.buffer)
            
        # Trigger an immediate flush if the buffer exceeds BATCH_MAX_SIZE
        if buffer_size >= BATCH_MAX_SIZE:
            threading.Thread(target=self.flush).start()

    def flush(self) -> int:
        """Flushes buffered queries to the database using a single bulk transaction."""
        with self.lock:
            if not self.buffer:
                return 0
            # Swap buffer to prevent blocking incoming searches
            current_batch = self.buffer
            self.buffer = {}
            
        try:
            # Upsert queries to SQLite in a single transaction
            rows_affected = bulk_upsert_queries(current_batch)
            self.total_db_writes += 1
            
            # Invalidate caches for all prefixes of the updated queries
            for query in current_batch.keys():
                cache_manager.invalidate_query(query)
                
            return rows_affected
        except Exception as e:
            # In a production environment, we'd write to a fallback dead-letter log.
            # Here we restore queries back to the buffer to prevent data loss.
            print(f"Error flushing batch: {e}")
            with self.lock:
                for q, count in current_batch.items():
                    self.buffer[q] = self.buffer.get(q, 0) + count
            return 0

    def _loop(self):
        """Background thread loop that runs periodic flushes."""
        while self.is_running:
            time.sleep(BATCH_FLUSH_INTERVAL)
            if self.is_running:
                self.flush()

    def start(self):
        """Starts the background worker thread."""
        if self.is_running:
            return
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._loop, daemon=True)
        self.worker_thread.start()
        print("Batch Query Writer background worker started.")

    def stop(self):
        """Stops the background worker thread and flushes remaining items."""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
        # Final flush
        self.flush()
        print("Batch Query Writer background worker stopped.")

    def get_metrics(self) -> Dict[str, Any]:
        """Returns stats on search submissions, db writes, and write reduction."""
        searches = self.total_searches_received
        db_writes = self.total_db_writes
        
        # Reduction ratio calculation
        # If we got 1000 searches and wrote to DB 5 times, we saved 995 writes (99.5% reduction)
        writes_saved = searches - db_writes
        reduction_pct = (writes_saved / searches * 100) if searches > 0 else 0.0
        
        with self.lock:
            pending_items = sum(self.buffer.values())
            buffer_size = len(self.buffer)
            
        return {
            "total_searches_received": searches,
            "total_db_writes": db_writes,
            "write_reduction_pct": round(reduction_pct, 2),
            "pending_buffered_searches": pending_items,
            "buffer_unique_keys": buffer_size
        }

# Global batch writer singleton
batch_writer = BatchQueryWriter()
