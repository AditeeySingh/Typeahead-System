import os

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "../data/typeahead.db")

# Distributed Cache settings
CACHE_NODES = ["CacheNode-A", "CacheNode-B", "CacheNode-C"]
VIRTUAL_NODES_COUNT = 50  # Virtual nodes per physical node for balanced hashing distribution
CACHE_TTL = 60            # Seconds before cache item expires
CACHE_MAX_SIZE = 1000     # Maximum cache keys per node (LRU capacity)

# Batch Writer settings
BATCH_FLUSH_INTERVAL = 5.0  # Flush buffer to database every 5 seconds
BATCH_MAX_SIZE = 100        # Flush immediately if buffer exceeds this size

# Trending searches ranking settings
ALPHA = 0.7                 # Recency scoring weight: Score = ALPHA * recent_count + (1 - ALPHA) * total_count
DECAY_INTERVAL = 60.0       # Time in seconds between decay epochs (accelerated to 60s for demo visibility)
DECAY_FACTOR = 0.75         # Decay factor per epoch: recent_count = recent_count * DECAY_FACTOR
