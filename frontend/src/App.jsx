import React, { useState, useEffect, useRef } from "react";
import { 
  Search, 
  Flame, 
  Server, 
  Cpu, 
  Database, 
  TrendingUp, 
  Zap, 
  CheckCircle, 
  RefreshCw,
  Clock,
  Layers,
  HelpCircle,
  Activity
} from "lucide-react";

const API_BASE = "http://127.0.0.1:8000";

export default function App() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [trending, setTrending] = useState([]);
  const [metrics, setMetrics] = useState({
    ranking_mode: "enhanced",
    latency_metrics_ms: { avg: 0, p95: 0, p99: 0, samples_count: 0 },
    cache_metrics: { total_hits: 0, total_misses: 0, hit_rate_pct: 0, nodes: {} },
    batch_writer_metrics: { total_searches_received: 0, total_db_writes: 0, write_reduction_pct: 0, pending_buffered_searches: 0, buffer_unique_keys: 0 },
    decay_metrics: { total_decays_executed: 0, seconds_since_last_decay: 0, decay_interval: 60, decay_factor: 0.75 }
  });
  
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [showDropdown, setShowDropdown] = useState(false);
  const [searchSuccess, setSearchSuccess] = useState(null);
  
  // Cache debug routing states
  const [debugPrefix, setDebugPrefix] = useState("");
  const [debugRouting, setDebugRouting] = useState({
    prefix: "",
    cache_node: "",
    in_cache: false,
    hit: false
  });

  const dropdownRef = useRef(null);

  // Poll metrics and trending every 1.5 seconds
  useEffect(() => {
    fetchMetrics();
    fetchTrending();
    const timer = setInterval(() => {
      fetchMetrics();
      fetchTrending();
    }, 1500);
    return () => clearInterval(timer);
  }, [metrics.ranking_mode]);

  // Handle autocomplete input debouncing (250ms)
  useEffect(() => {
    if (query.trim() === "") {
      setSuggestions([]);
      setDebugPrefix("");
      setDebugRouting({ prefix: "", cache_node: "", in_cache: false, hit: false });
      return;
    }

    const timer = setTimeout(() => {
      fetchSuggestions(query);
      fetchCacheDebug(query);
    }, 250);

    return () => clearTimeout(timer);
  }, [query]);

  // Click outside listener for suggestion dropdown closing
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchSuggestions = async (prefix) => {
    try {
      const res = await fetch(`${API_BASE}/suggest?q=${encodeURIComponent(prefix)}`);
      if (res.ok) {
        const data = await res.json();
        setSuggestions(data);
        setShowDropdown(true);
        setActiveSuggestionIndex(-1);
      }
    } catch (err) {
      console.error("Error fetching suggestions:", err);
    }
  };

  const fetchCacheDebug = async (prefix) => {
    try {
      const res = await fetch(`${API_BASE}/cache/debug?prefix=${encodeURIComponent(prefix)}`);
      if (res.ok) {
        const data = await res.json();
        setDebugPrefix(prefix);
        setDebugRouting(data);
      }
    } catch (err) {
      console.error("Error fetching cache debug info:", err);
    }
  };

  const fetchTrending = async () => {
    try {
      const res = await fetch(`${API_BASE}/trending`);
      if (res.ok) {
        const data = await res.json();
        setTrending(data);
      }
    } catch (err) {
      console.error("Error fetching trending searches:", err);
    }
  };

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`${API_BASE}/metrics`);
      if (res.ok) {
        const data = await res.json();
        setMetrics(data);
      }
    } catch (err) {
      console.error("Error fetching metrics:", err);
    }
  };

  const handleSearchSubmit = async (searchQuery) => {
    const finalQuery = searchQuery.trim();
    if (!finalQuery) return;

    try {
      const res = await fetch(`${API_BASE}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: finalQuery })
      });
      if (res.ok) {
        const data = await res.json();
        setSearchSuccess(`Successfully submitted search for: "${finalQuery}". Response: ${JSON.stringify(data)}`);
        setQuery("");
        setShowDropdown(false);
        fetchMetrics();
        // Clear message after 4s
        setTimeout(() => setSearchSuccess(null), 4000);
      }
    } catch (err) {
      console.error("Error submitting search:", err);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (activeSuggestionIndex >= 0 && activeSuggestionIndex < suggestions.length) {
        const selected = suggestions[activeSuggestionIndex].query;
        handleSearchSubmit(selected);
      } else if (query.trim() !== "") {
        handleSearchSubmit(query);
      }
      return;
    }

    if (!showDropdown || suggestions.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveSuggestionIndex((prev) => (prev + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveSuggestionIndex((prev) => (prev - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

  const toggleRanking = async () => {
    try {
      const res = await fetch(`${API_BASE}/ranking/toggle`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        fetchMetrics();
        fetchTrending();
      }
    } catch (err) {
      console.error("Error toggling ranking mode:", err);
    }
  };

  const triggerFlush = async () => {
    try {
      await fetch(`${API_BASE}/search/flush`, { method: "POST" });
      fetchMetrics();
      fetchTrending();
    } catch (err) {
      console.error("Error triggering flush:", err);
    }
  };

  const triggerDecay = async () => {
    try {
      await fetch(`${API_BASE}/decay/trigger`, { method: "POST" });
      fetchMetrics();
      fetchTrending();
    } catch (err) {
      console.error("Error triggering decay:", err);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="logo-dot" />
          <h1>Aditeey's Typeahead System</h1>
        </div>
        <div className="flex gap-2">
          <span className={`mode-badge ${metrics.ranking_mode === "enhanced" ? "enhanced" : ""}`}>
            {metrics.ranking_mode === "enhanced" ? "Enhanced Recency-Aware" : "Basic Cumulative"}
          </span>
        </div>
      </header>

      {/* Main Grid */}
      <div className="dashboard-grid">
        
        {/* Column 1: Control Panel & Diagnostics */}
        <aside className="panel-column">
          
          {/* Controls */}
          <div className="glass-card">
            <h2 className="panel-title">
              <Cpu size={18} /> System Controls
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
              <button className="control-btn toggle-btn" onClick={toggleRanking}>
                <Layers size={16} /> Toggle Ranking Rules
              </button>
              <button className="control-btn" onClick={triggerFlush}>
                <RefreshCw size={16} /> Force Flush Buffer
              </button>
              <button className="control-btn" onClick={triggerDecay}>
                <Flame size={16} /> Force Recency Decay
              </button>
            </div>
          </div>

          {/* Read/Write Telemetry */}
          <div className="glass-card">
            <h2 className="panel-title">
              <Database size={18} /> Buffer & Writes
            </h2>
            <div className="metrics-list">
              
              <div className="metric-item">
                <div className="metric-header">
                  <span>Pending in Buffer</span>
                  <span>{metrics.batch_writer_metrics.pending_buffered_searches} searches</span>
                </div>
                <div className="metric-value">
                  {metrics.batch_writer_metrics.buffer_unique_keys} <span style={{fontSize: "0.8rem", color: "var(--text-secondary)"}}>keys</span>
                </div>
              </div>

              <div className="metric-item">
                <div className="metric-header">
                  <span>Write Reduction Saved</span>
                  <span>{metrics.batch_writer_metrics.write_reduction_pct}%</span>
                </div>
                <div className="progress-bar-bg">
                  <div 
                    className="progress-bar-fill" 
                    style={{ 
                      width: `${metrics.batch_writer_metrics.write_reduction_pct}%`,
                      background: "linear-gradient(90deg, var(--accent-pink), var(--accent-violet))" 
                    }} 
                  />
                </div>
                <div className="metric-subinfo">
                  <span>Searches: {metrics.batch_writer_metrics.total_searches_received}</span>
                  <span>DB Writes: {metrics.batch_writer_metrics.total_db_writes}</span>
                </div>
              </div>

            </div>
          </div>

          {/* Cache Telemetry */}
          <div className="glass-card">
            <h2 className="panel-title">
              <Activity size={18} /> Cache Telemetry
            </h2>
            <div className="metrics-list">
              
              <div className="metric-item">
                <div className="metric-header">
                  <span>Global Cache Hit Rate</span>
                  <span>{metrics.cache_metrics.hit_rate_pct}%</span>
                </div>
                <div className="progress-bar-bg">
                  <div 
                    className="progress-bar-fill" 
                    style={{ width: `${metrics.cache_metrics.hit_rate_pct}%` }} 
                  />
                </div>
                <div className="metric-subinfo">
                  <span>Hits: {metrics.cache_metrics.total_hits}</span>
                  <span>Misses: {metrics.cache_metrics.total_misses}</span>
                </div>
              </div>

              {Object.entries(metrics.cache_metrics.nodes || {}).map(([nodeName, nodeInfo]) => (
                <div key={nodeName} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", borderTop: "1px solid rgba(255,255,255,0.03)", paddingTop: "0.4rem" }}>
                  <span style={{ color: "var(--text-secondary)" }}>{nodeName}</span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>
                    {nodeInfo.size} keys | {nodeInfo.hits}H / {nodeInfo.misses}M
                  </span>
                </div>
              ))}

            </div>
          </div>

        </aside>

        {/* Column 2: Search Box Autocomplete */}
        <main style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          
          {/* Main search card */}
          <div className="glass-card" style={{ padding: "2.5rem 2rem", minHeight: "350px", display: "flex", flexDirection: "column", justifyContent: "center", position: "relative", zIndex: 10 }}>
            <h2 style={{ textAlign: "center", marginBottom: "2rem", fontWeight: "600", fontSize: "1.5rem", letterSpacing: "-0.5px" }}>
              What are you looking for today?
            </h2>
            
            <div className="search-container" ref={dropdownRef}>
              <div className="search-input-wrapper">
                <Search 
                  className="search-icon" 
                  size={20} 
                  style={{ cursor: "pointer", pointerEvents: "auto" }}
                  onClick={() => handleSearchSubmit(query)}
                  title="Click to search"
                />
                <input
                  type="text"
                  className="search-input"
                  placeholder="Type a prefix (e.g. 'iph', 'pyt', 'react')..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onFocus={() => setShowDropdown(true)}
                />
                {query && (
                  <button className="search-clear-btn" onClick={() => setQuery("")}>
                    ✕
                  </button>
                )}
              </div>

              {/* Suggestions Dropdown */}
              {showDropdown && query && (
                <div className="suggest-dropdown">
                  {suggestions.length > 0 ? (
                    suggestions.map((item, index) => (
                      <div
                        key={item.query}
                        className={`suggest-item ${index === activeSuggestionIndex ? "active" : ""}`}
                        onClick={() => handleSearchSubmit(item.query)}
                      >
                        <div className="suggest-text">
                          <Search size={14} style={{ opacity: 0.5 }} />
                          <span>{item.query}</span>
                        </div>
                        <div className="suggest-meta">
                          {metrics.ranking_mode === "enhanced" && item.recent_count > 0 && (
                            <span className="recent-badge">
                              <Flame size={12} fill="var(--accent-pink)" /> {item.recent_count} recent
                            </span>
                          )}
                          <span className="count-badge">
                            {item.total_count.toLocaleString()} queries
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="no-suggestions">
                      No matching queries found. Press Enter to submit anyway.
                    </div>
                  )}
                </div>
              )}
            </div>

            {searchSuccess && (
              <div className="search-success-banner">
                <CheckCircle size={18} />
                <span>{searchSuccess}</span>
              </div>
            )}
          </div>

          {/* Latency Dashboard info */}
          <div className="glass-card" style={{ display: "flex", justifyContent: "space-around", padding: "1.2rem", position: "relative", zIndex: 1 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                <Clock size={14} /> Avg Latency
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "1.4rem", fontWeight: "600", color: "var(--accent-indigo)" }}>
                {metrics.latency_metrics_ms.avg}ms
              </div>
            </div>
            
            <div style={{ textAlign: "center", borderLeft: "1px solid var(--border-light)", borderRight: "1px solid var(--border-light)", padding: "0 2rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                <Clock size={14} /> p95 Latency
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "1.4rem", fontWeight: "600", color: "var(--accent-pink)" }}>
                {metrics.latency_metrics_ms.p95}ms
              </div>
            </div>

            <div style={{ textAlign: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                <Clock size={14} /> p99 Latency
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "1.4rem", fontWeight: "600", color: "var(--text-violet)" }}>
                {metrics.latency_metrics_ms.p99}ms
              </div>
            </div>
          </div>

        </main>

        {/* Column 3: Hashing Ring Visualizer & Trending */}
        <aside className="panel-column">
          
          {/* Hashing Ring Panel */}
          <div className="glass-card">
            <h2 className="panel-title">
              <Server size={18} /> Cache Node Routing
            </h2>
            
            <div className="cache-ring-container">
              <div className="ring-visualization">
                <div className="ring-center">
                  <Layers size={16} />
                  <span>Hash Ring</span>
                </div>
                
                {/* 3 nodes placed in a triangle on the circle */}
                <div className={`ring-node node-a ${debugRouting.cache_node === "CacheNode-A" ? "active-routing" : ""}`}>
                  A
                </div>
                <div className={`ring-node node-b ${debugRouting.cache_node === "CacheNode-B" ? "active-routing" : ""}`}>
                  B
                </div>
                <div className={`ring-node node-c ${debugRouting.cache_node === "CacheNode-C" ? "active-routing" : ""}`}>
                  C
                </div>
              </div>
            </div>

            {/* Trace Info */}
            <div className="debug-logs-panel">
              <div className="log-row">
                <span className="log-label">Prefix Key:</span>
                <span className="log-val">{debugPrefix ? `"${debugPrefix}"` : "-"}</span>
              </div>
              <div className="log-row">
                <span className="log-label">Routed Node:</span>
                <span className="log-val" style={{color: debugRouting.cache_node ? "var(--accent-indigo)" : "var(--text-muted)"}}>
                  {debugRouting.cache_node || "-"}
                </span>
              </div>
              <div className="log-row">
                <span className="log-label">Cache Status:</span>
                <span className={`log-val ${debugRouting.hit ? "hit" : "miss"}`}>
                  {debugPrefix ? (debugRouting.hit ? "HIT" : "MISS") : "-"}
                </span>
              </div>
            </div>
          </div>

          {/* Trending Panel */}
          <div className="glass-card">
            <h2 className="panel-title">
              <TrendingUp size={18} /> Trending Searches
            </h2>
            
            <div className="trending-list">
              {trending.slice(0, 7).map((item, idx) => (
                <div 
                  key={item.query} 
                  className="trending-item"
                  onClick={() => {
                    setQuery(item.query);
                    handleSearchSubmit(item.query);
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center" }}>
                    <span className="trending-rank">#{idx + 1}</span>
                    <span className="trending-query">{item.query}</span>
                  </div>
                  <div className="trending-count">
                    {metrics.ranking_mode === "enhanced" && item.recent_count > 0 ? (
                      <span style={{ color: "var(--accent-pink)", display: "flex", alignItems: "center", gap: "2px" }}>
                        <Flame size={12} fill="var(--accent-pink)" /> {item.recent_count}
                      </span>
                    ) : (
                      <span>{item.total_count.toLocaleString()}</span>
                    )}
                  </div>
                </div>
              ))}
              {trending.length === 0 && (
                <div className="no-suggestions" style={{ padding: "0.5rem" }}>
                  No searches submitted yet.
                </div>
              )}
            </div>
          </div>

        </aside>

      </div>
    </div>
  );
}
