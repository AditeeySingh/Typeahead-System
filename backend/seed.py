import os
import random
import csv
import sqlite3
import time

# Ensure folders exist
os.makedirs("../data", exist_ok=True)
os.makedirs("data", exist_ok=True)  # in case relative paths are tricky, let's establish clean absolute paths or paths relative to execution dir

CSV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/queries.csv"))
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/typeahead.db"))

print(f"CSV Path: {CSV_PATH}")
print(f"DB Path: {DB_PATH}")

# Vocabulary for generating queries
ADJECTIVES = [
    "best", "cheap", "free", "latest", "top", "easy", "online", "fast", "slow", "simple",
    "advanced", "modern", "vintage", "custom", "luxury", "portable", "wireless", "wired",
    "smart", "digital", "analog", "electric", "manual", "waterproof", "durable", "premium",
    "heavy duty", "lightweight", "mini", "pocket", "organic", "natural", "healthy", "vegan"
]

NOUNS = [
    "iphone", "macbook", "samsung", "ipad", "laptop", "keyboard", "mouse", "monitor", "headphone",
    "earbuds", "speaker", "camera", "lens", "tripod", "charger", "cable", "adapter", "backpack",
    "wallet", "watch", "shoes", "sneakers", "tshirt", "jeans", "jacket", "socks", "hat", "glasses",
    "water bottle", "coffee mug", "desk", "chair", "lamp", "notebook", "pen", "pencil", "eraser",
    "python", "javascript", "java", "c++", "rust", "golang", "html", "css", "react", "vue", "angular",
    "fastapi", "flask", "django", "nodejs", "express", "sql", "sqlite", "postgresql", "redis", "mongodb",
    "docker", "kubernetes", "git", "github", "aws", "gcp", "azure", "linux", "windows", "macos"
]

ACTIONS = [
    "tutorial", "guide", "course", "book", "video", "review", "price", "specs", "vs", "alternative",
    "how to learn", "how to build", "how to fix", "problems", "errors", "bugs", "solutions",
    "documentation", "examples", "tips", "tricks", "hacks", "best practices", "setup", "install",
    "download", "source code", "templates", "framework", "library", "comparison", "deals", "coupon"
]

SUBJECTS = [
    "for beginners", "for developers", "in 2026", "with code", "step by step", "near me", "under 100",
    "under 500", "for college", "for office", "for gaming", "for programming", "for kids", "for adults",
    "with examples", "without coding", "free download", "pro max", "ultra", "plus", "lite", "se"
]

def generate_queries(target_count=120000):
    print(f"Generating {target_count} unique queries...")
    queries = set()
    
    # Pre-add some specific high-frequency queries to make the dataset look realistic
    curated = [
        "iphone", "iphone 15", "iphone charger", "java tutorial", "python tutorial",
        "react crash course", "docker container guide", "how to write consistent hashing",
        "redis cache tutorial", "fastapi setup with postgres", "sqlite wal mode",
        "best mechanical keyboard", "cheap running shoes", "how to learn coding fast",
        "what is a trie data structure", "trending searches today", "javascript array methods"
    ]
    for q in curated:
        queries.add(q)
        
    attempts = 0
    while len(queries) < target_count and attempts < 1000000:
        attempts += 1
        
        # Decide query structure randomly
        structure = random.choice([
            "adj noun",
            "noun action",
            "noun subject",
            "adj noun action",
            "noun action subject",
            "adj noun action subject",
            "verb noun"
        ])
        
        parts = []
        if "verb" in structure:
            parts.append(random.choice(["learn", "use", "code", "buy", "find", "get", "make", "create"]))
        if "adj" in structure:
            parts.append(random.choice(ADJECTIVES))
        
        parts.append(random.choice(NOUNS))
        
        if "action" in structure:
            parts.append(random.choice(ACTIONS))
        if "subject" in structure:
            parts.append(random.choice(SUBJECTS))
            
        query_text = " ".join(parts).lower().strip()
        if query_text:
            queries.add(query_text)
            
    print(f"Generated {len(queries)} unique queries in {attempts} attempts.")
    return sorted(list(queries))

def apply_zipf_distribution(queries):
    print("Applying Zipfian distribution counts...")
    # Zipf parameter s = 0.8
    # count = Scale / (rank^s)
    scale = 200000
    decay = 0.75
    
    query_data = []
    # Shuffle so that the alphabetical sorting doesn't dictate the count rank
    random.shuffle(queries)
    
    for i, q in enumerate(queries):
        rank = i + 1
        count = int(scale / (rank ** decay)) + 1
        # Set some base random noise
        count += random.randint(0, 5)
        # Assign a random recent_count representing searches in the last 24h
        # High overall count doesn't always mean high recent count (trending)
        # Let's say recent count is normally small, but occasionally spikes (viral queries)
        recent_count = 0
        if random.random() < 0.05:  # 5% of queries have active recent searches
            recent_count = int(count * random.uniform(0.01, 0.1)) + random.randint(1, 10)
        else:
            recent_count = random.randint(0, 3)
            
        # Give a random last_searched_at timestamp within the last 7 days
        days_ago = random.uniform(0, 7)
        timestamp = time.time() - (days_ago * 86400)
        formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
        
        query_data.append((q, count, recent_count, formatted_time))
        
    # Sort by overall count descending for display/verifying
    query_data.sort(key=lambda x: x[1], reverse=True)
    return query_data

def save_to_csv(data):
    print(f"Saving to CSV at {CSV_PATH}...")
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["query", "count", "recent_count", "last_searched_at"])
        writer.writerows(data)
    print("CSV saved successfully.")

def seed_database():
    print(f"Initializing database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Set WAL mode and performance pragmas
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    
    # Drop table if exists to ensure clean seed
    cursor.execute("DROP TABLE IF EXISTS search_queries;")
    
    cursor.execute("""
    CREATE TABLE search_queries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query_text TEXT UNIQUE NOT NULL,
        total_count INTEGER DEFAULT 0,
        recent_count INTEGER DEFAULT 0,
        last_searched_at TEXT
    );
    """)
    conn.commit()
    
    # Read CSV data to insert
    print("Reading CSV and inserting data...")
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader) # Skip header
        
        # Insert in batches
        batch = []
        count = 0
        for row in reader:
            batch.append((row[0], int(row[1]), int(row[2]), row[3]))
            if len(batch) >= 10000:
                cursor.executemany("""
                INSERT INTO search_queries (query_text, total_count, recent_count, last_searched_at)
                VALUES (?, ?, ?, ?);
                """, batch)
                count += len(batch)
                batch = []
        if batch:
            cursor.executemany("""
            INSERT INTO search_queries (query_text, total_count, recent_count, last_searched_at)
            VALUES (?, ?, ?, ?);
            """, batch)
            count += len(batch)
            
    print(f"Inserted {count} rows.")
    
    # Create indexes for fast prefix search and ranking sorting
    print("Creating indexes...")
    t0 = time.time()
    # Case-insensitive index for prefix matching
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_query_text_nocase ON search_queries(query_text COLLATE NOCASE);")
    # Indexes for ranking sorting
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_total_count ON search_queries(total_count DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recent_count ON search_queries(recent_count DESC);")
    conn.commit()
    t1 = time.time()
    print(f"Indexes created in {t1 - t0:.2f}s.")
    
    # Verify count
    cursor.execute("SELECT COUNT(*) FROM search_queries;")
    db_count = cursor.fetchone()[0]
    print(f"Verification: Database has {db_count} queries.")
    
    conn.close()
    print("Database seeding completed.")

if __name__ == "__main__":
    t_start = time.time()
    raw_queries = generate_queries(120000)
    zipf_data = apply_zipf_distribution(raw_queries)
    save_to_csv(zipf_data)
    seed_database()
    print(f"Total time elapsed: {time.time() - t_start:.2f} seconds.")
