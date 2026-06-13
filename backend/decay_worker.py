import time
import threading
from typing import Dict, Any
from backend.config import DECAY_INTERVAL, DECAY_FACTOR
from backend.database import decay_recent_counts
from backend.cache_ring import cache_manager

class RecencyDecayWorker:
    """Periodically decays recent counts in the database and invalidates the cache ring to update trending ranks."""
    def __init__(self):
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.total_decays_executed = 0
        self.last_decay_time = 0.0

    def trigger_decay(self) -> int:
        """Manually triggers a decay cycle (useful for tests and APIs)."""
        rows_decayed = decay_recent_counts(DECAY_FACTOR)
        self.total_decays_executed += 1
        self.last_decay_time = time.time()
        
        # Clear cache nodes since scoring order of prefix queries has changed
        cache_manager.clear_all()
        return rows_decayed

    def _loop(self):
        """Background thread loop that runs decay epochs periodically."""
        # Wait a bit after startup before running first decay
        time.sleep(DECAY_INTERVAL)
        while self.is_running:
            try:
                self.trigger_decay()
            except Exception as e:
                print(f"Error in decay worker: {e}")
            time.sleep(DECAY_INTERVAL)

    def start(self):
        """Starts the background worker thread."""
        if self.is_running:
            return
        self.is_running = True
        self.last_decay_time = time.time()
        self.worker_thread = threading.Thread(target=self._loop, daemon=True)
        self.worker_thread.start()
        print("Recency Decay background worker started.")

    def stop(self):
        """Stops the background worker thread."""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
        print("Recency Decay background worker stopped.")

    def get_metrics(self) -> Dict[str, Any]:
        """Returns stats on the decay cycles."""
        time_since_last = time.time() - self.last_decay_time if self.last_decay_time > 0 else 0.0
        return {
            "total_decays_executed": self.total_decays_executed,
            "seconds_since_last_decay": round(time_since_last, 1),
            "decay_interval": DECAY_INTERVAL,
            "decay_factor": DECAY_FACTOR
        }

# Global decay worker singleton
decay_worker = RecencyDecayWorker()
