"""Database schema definitions."""
from .connection import get_db

SCHEMA_SQL = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    preferences TEXT DEFAULT '{}'
);

-- Trucking Companies (seeded with realistic data)
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    contact_phone TEXT,
    contact_email TEXT,
    service_areas TEXT NOT NULL,
    fleet_info TEXT NOT NULL,
    personality TEXT NOT NULL CHECK (personality IN ('firm', 'flexible', 'desperate', 'premium')),
    base_rate_multiplier REAL DEFAULT 1.0,
    min_discount_threshold REAL DEFAULT 0.05,
    rating REAL DEFAULT 4.0,
    is_active INTEGER DEFAULT 1
);

-- Negotiation sessions (persisted)
CREATE TABLE IF NOT EXISTS negotiation_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    item_description TEXT NOT NULL,
    target_price REAL NOT NULL,
    max_price REAL NOT NULL,
    strategy TEXT NOT NULL,
    status TEXT DEFAULT 'in_progress',
    best_deal_company_id TEXT REFERENCES companies(id),
    best_deal_price REAL,
    total_rounds INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Provider negotiations (each company in a session)
CREATE TABLE IF NOT EXISTS provider_negotiations (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES negotiation_sessions(id) ON DELETE CASCADE,
    company_id TEXT REFERENCES companies(id),
    initial_price REAL NOT NULL,
    current_price REAL,
    min_price REAL NOT NULL,
    status TEXT DEFAULT 'negotiating',
    rounds INTEGER DEFAULT 0
);

-- Messages (conversation history)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_negotiation_id TEXT REFERENCES provider_negotiations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('negotiator', 'provider')),
    action TEXT NOT NULL,
    amount REAL,
    message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Negotiation results (for analytics)
CREATE TABLE IF NOT EXISTS negotiation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    session_id TEXT REFERENCES negotiation_sessions(id) ON DELETE CASCADE,
    company_id TEXT REFERENCES companies(id),
    company_name TEXT NOT NULL,
    initial_price REAL NOT NULL,
    final_price REAL NOT NULL,
    savings_amount REAL,
    savings_percent REAL,
    strategy TEXT NOT NULL,
    rounds_taken INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Voice call records
CREATE TABLE IF NOT EXISTS voice_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES negotiation_sessions(id),
    company_id TEXT REFERENCES companies(id),
    phone_number TEXT NOT NULL,
    twilio_call_sid TEXT,
    status TEXT DEFAULT 'initiated',
    transcript TEXT,
    duration_seconds INTEGER,
    outcome TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sessions_user ON negotiation_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON negotiation_sessions(status);
CREATE INDEX IF NOT EXISTS idx_results_user ON negotiation_results(user_id);
CREATE INDEX IF NOT EXISTS idx_provider_neg_session ON provider_negotiations(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_provider ON messages(provider_negotiation_id);
CREATE INDEX IF NOT EXISTS idx_voice_calls_session ON voice_calls(session_id);
"""


async def create_tables() -> None:
    """Create all database tables."""
    async with get_db() as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
