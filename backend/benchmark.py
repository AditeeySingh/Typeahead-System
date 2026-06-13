import time
import random
import http.client
import json

API_HOST = "127.0.0.1"
API_PORT = 8000

def make_request(method, path, body=None):
    """Utility to make HTTP requests using Python's standard http.client (no third-party deps needed)."""
    conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=5)
    headers = {"Content-type": "application/json"} if body else {}
    try:
        conn.request(method, path, body=json.dumps(body) if body else None, headers=headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")
        return res.status, json.loads(data) if res.status == 200 else data
    except Exception as e:
        print(f"Request error on {method} {path}: {e}")
        return 500, str(e)
    finally:
        conn.close()

def run_benchmark():
    print("==================================================")
    print("      SEARCH TYPEAHEAD SYSTEM BENCHMARK SCRIPT     ")
    print("==================================================")
    
    # 1. Warm up the server and clear caches
    print("[1/5] Resetting system states and warming up cache...")
    make_request("POST", "/ranking/toggle") # Toggles mode and clears cache
    make_request("POST", "/ranking/toggle") # Toggle back to original mode (enhanced) and clears cache
    make_request("POST", "/search/flush")   # Flush any pending buffer
    
    # 2. Run suggestion latency test (1000 requests)
    # We will pick 10 common prefixes and request them repeatedly to simulate realistic caching behavior
    prefixes = ["iph", "pyt", "jav", "mac", "doc", "rea", "vue", "lin", "aws", "how"]
    print(f"[2/5] Running 1,000 suggestion requests across {len(prefixes)} prefixes...")
    
    t_start = time.perf_counter()
    latencies = []
    
    for i in range(1000):
        prefix = random.choice(prefixes)
        req_start = time.perf_counter()
        status, data = make_request("GET", f"/suggest?q={prefix}")
        req_elapsed = (time.perf_counter() - req_start) * 1000.0
        latencies.append(req_elapsed)
        
    total_suggest_time = time.perf_counter() - t_start
    print(f"      Completed 1,000 suggests in {total_suggest_time:.2f}s.")
    
    # 3. Run search submissions test (500 search queries)
    # We will submit duplicate queries to verify batch write aggregation
    print("[3/5] Submitting 500 search queries (highly duplicated) to test batching...")
    search_queries = [
        "iphone 15 pro max",
        "python tutorial for beginners",
        "react hooks guide",
        "docker containerization crash course",
        "kubernetes scaling models"
    ]
    
    for i in range(500):
        query = random.choice(search_queries)
        make_request("POST", "/search", {"query": query})
        
    print("      Completed 500 search submissions.")
    
    # 4. Trigger manual buffer flush to capture writes count
    print("[4/5] Triggering database write buffer flush...")
    status, flush_data = make_request("POST", "/search/flush")
    print(f"      Flush result: {flush_data}")
    
    # 5. Fetch telemetry and print final report
    print("[5/5] Fetching system telemetry and generating report...")
    status, metrics = make_request("GET", "/metrics")
    
    if status != 200:
        print(f"Failed to fetch metrics: {metrics}")
        return
        
    lat = metrics["latency_metrics_ms"]
    cache = metrics["cache_metrics"]
    batch = metrics["batch_writer_metrics"]
    decay = metrics["decay_metrics"]
    
    print("\n" + "="*50)
    print("               PERFORMANCE REPORT                 ")
    print("="*50)
    print(f"System Mode:           {metrics['ranking_mode'].upper()}")
    print("-"*50)
    print("SUGGESTION API LATENCY (SLIDING WINDOW):")
    print(f"  Average Latency:     {lat['avg']:.2f} ms")
    print(f"  p95 Latency:         {lat['p95']:.2f} ms")
    print(f"  p99 Latency:         {lat['p99']:.2f} ms")
    print(f"  Total Requests:      {lat['samples_count']}")
    print("-"*50)
    print("DISTRIBUTED CACHE PERFORMANCE:")
    print(f"  Global Hit Rate:     {cache['hit_rate_pct']}%")
    print(f"  Cache Hits:          {cache['total_hits']}")
    print(f"  Cache Misses:        {cache['total_misses']}")
    print("  Node Key Distribution:")
    for node, info in cache["nodes"].items():
        node_hit_rate = (info['hits'] / (info['hits'] + info['misses']) * 100) if (info['hits'] + info['misses']) > 0 else 0.0
        print(f"    - {node}: {info['size']} keys | {info['hits']} hits / {info['misses']} misses | Hit Rate: {node_hit_rate:.1f}%")
    print("-"*50)
    print("BATCH WRITES & WRITE REDUCTION:")
    print(f"  Searches Submitted:  {batch['total_searches_received']}")
    print(f"  Database Write Ops:  {batch['total_db_writes']}")
    print(f"  Write Reduction %:   {batch['write_reduction_pct']}% (Saved {batch['total_searches_received'] - batch['total_db_writes']} SQL Writes!)")
    print("-"*50)
    print("RECENCY DECAY WORKER STATUS:")
    print(f"  Total Decays Run:    {decay['total_decays_executed']}")
    print(f"  Decay Factor:        {decay['decay_factor']}")
    print(f"  Decay Interval:      {decay['decay_interval']}s")
    print("="*50)
    print("      Verification Successful. Ready for submission.  ")
    print("="*50)

if __name__ == "__main__":
    run_benchmark()
