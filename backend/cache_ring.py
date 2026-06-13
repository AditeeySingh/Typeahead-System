import hashlib
import bisect
import time
from collections import OrderedDict
from threading import Lock
from typing import List, Dict, Optional, Tuple, Any
from backend.config import CACHE_NODES, VIRTUAL_NODES_COUNT, CACHE_TTL, CACHE_MAX_SIZE

class ConsistentHashRing:
    """Consistent Hash Ring mapping keys to cache nodes using virtual nodes."""
    def __init__(self, nodes: List[str] = None, replicas: int = 50):
        self.replicas = replicas
        self.ring: Dict[int, str] = {}
        self.sorted_keys: List[int] = []
        self._lock = Lock()
        
        if nodes:
            for node in nodes:
                self.add_node(node)
                
    def _hash(self, key: str) -> int:
        """Returns the MD5 hash of the key as an integer."""
        return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)

    def add_node(self, node: str):
        """Adds a physical node and its virtual replicas to the ring."""
        with self._lock:
            for i in range(self.replicas):
                vnode_key = f"{node}#vnode_{i}"
                vnode_hash = self._hash(vnode_key)
                self.ring[vnode_hash] = node
                bisect.insort(self.sorted_keys, vnode_hash)

    def remove_node(self, node: str):
        """Removes a physical node and its virtual replicas from the ring."""
        with self._lock:
            for i in range(self.replicas):
                vnode_key = f"{node}#vnode_{i}"
                vnode_hash = self._hash(vnode_key)
                if vnode_hash in self.ring:
                    del self.ring[vnode_hash]
                    self.sorted_keys.remove(vnode_hash)

    def get_node(self, key: str) -> str:
        """Looks up which physical node is responsible for the given key."""
        if not self.ring:
            raise ValueError("Hash ring is empty.")
            
        key_hash = self._hash(key)
        # Binary search for the first virtual node hash >= key_hash
        idx = bisect.bisect_right(self.sorted_keys, key_hash)
        
        # If it reaches the end of the ring, wrap around to index 0
        if idx == len(self.sorted_keys):
            idx = 0
            
        return self.ring[self.sorted_keys[idx]]

class CacheNode:
    """An individual in-memory cache node with LRU eviction and TTL support."""
    def __init__(self, node_name: str, max_size: int = 1000, ttl: int = 60):
        self.node_name = node_name
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()  # key -> (value, insertion_time)
        self.hits = 0
        self.misses = 0
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        """Fetches a key value, handling TTL expiration and LRU promotion."""
        with self._lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            value, timestamp = self.cache[key]
            
            # Check for TTL expiry
            if time.time() - timestamp > self.ttl:
                del self.cache[key]
                self.misses += 1
                return None
                
            # Promote to end (LRU)
            self.cache.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any):
        """Inserts or updates a key value, performing LRU eviction if full."""
        with self._lock:
            # If key exists, delete it first to update position
            if key in self.cache:
                del self.cache[key]
                
            # Evict oldest if capacity exceeded
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)
                
            self.cache[key] = (value, time.time())

    def delete(self, key: str):
        """Deletes a key from the cache if it exists."""
        with self._lock:
            if key in self.cache:
                del self.cache[key]

    def clear(self):
        """Clears all entries in the cache."""
        with self._lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0

class DistributedCacheManager:
    """Manages multiple CacheNode instances on a ConsistentHashRing."""
    def __init__(self):
        self.ring = ConsistentHashRing(nodes=CACHE_NODES, replicas=VIRTUAL_NODES_COUNT)
        self.nodes: Dict[str, CacheNode] = {
            node_name: CacheNode(node_name, max_size=CACHE_MAX_SIZE, ttl=CACHE_TTL)
            for node_name in CACHE_NODES
        }

    def get(self, prefix: str) -> Optional[List[Dict[str, Any]]]:
        """Routes suggestion request to the correct node and returns cached results."""
        node_name = self.ring.get_node(prefix)
        node = self.nodes[node_name]
        return node.get(prefix)

    def set(self, prefix: str, suggestions: List[Dict[str, Any]]):
        """Caches suggestions list in the node responsible for the prefix."""
        node_name = self.ring.get_node(prefix)
        node = self.nodes[node_name]
        node.set(prefix, suggestions)

    def invalidate_prefix(self, prefix: str):
        """Invalidates a single prefix cache entry."""
        node_name = self.ring.get_node(prefix)
        self.nodes[node_name].delete(prefix)

    def invalidate_query(self, query: str):
        """
        Invalidates all potential prefix cache keys for a given query.
        For example: if 'iphone' is updated, we invalidate cache entries for
        'i', 'ip', 'iph', 'ipho', 'iphon', 'iphone'.
        This maintains cache freshness when counts update.
        """
        for i in range(1, len(query) + 1):
            prefix = query[:i].lower()
            self.invalidate_prefix(prefix)

    def get_debug_info(self, prefix: str) -> Dict[str, Any]:
        """Returns diagnostic info about which cache node is responsible and hit status."""
        node_name = self.ring.get_node(prefix)
        node = self.nodes[node_name]
        
        # We check without incrementing hits/misses statistics
        with node._lock:
            in_cache = prefix in node.cache
            hit = False
            if in_cache:
                _, timestamp = node.cache[prefix]
                hit = (time.time() - timestamp) <= node.ttl
                
        return {
            "prefix": prefix,
            "cache_node": node_name,
            "in_cache": in_cache,
            "hit": hit,
            "timestamp": time.time()
        }

    def get_global_metrics(self) -> Dict[str, Any]:
        """Aggregates performance telemetry across all nodes."""
        total_hits = 0
        total_misses = 0
        nodes_info = {}
        
        for name, node in self.nodes.items():
            with node._lock:
                total_hits += node.hits
                total_misses += node.misses
                nodes_info[name] = {
                    "hits": node.hits,
                    "misses": node.misses,
                    "size": len(node.cache)
                }
                
        total_requests = total_hits + total_misses
        hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0.0
        
        return {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate_pct": round(hit_rate, 2),
            "nodes": nodes_info
        }

    def clear_all(self):
        """Clears all caches on all nodes."""
        for node in self.nodes.values():
            node.clear()

# Global distributed cache singleton
cache_manager = DistributedCacheManager()
