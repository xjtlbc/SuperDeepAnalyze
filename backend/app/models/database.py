import sqlite3
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and BEGIN IMMEDIATE support."""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.SQLITE_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA encoding='UTF-8'")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database schema."""
    conn = get_connection()
    try:
        # Migration: add wiki_status column if missing
        try:
            conn.execute("ALTER TABLE knowledge_bases ADD COLUMN wiki_status TEXT NOT NULL DEFAULT 'pending'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS model_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL UNIQUE,
                base_url TEXT NOT NULL,
                model_name TEXT NOT NULL,
                api_key TEXT NOT NULL,
                max_tokens INTEGER NOT NULL DEFAULT 8192,
                dimension INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                config_version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS knowledge_bases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                config_version INTEGER NOT NULL DEFAULT 1,
                compile_status TEXT NOT NULL DEFAULT 'pending',
                wiki_status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_type TEXT NOT NULL,
                parse_status TEXT NOT NULL DEFAULT 'pending',
                compile_status TEXT NOT NULL DEFAULT 'pending',
                parse_error TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS precompile_cache (
                file_hash TEXT PRIMARY KEY,
                doc_id TEXT,
                kb_id TEXT,
                data_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS fts_content USING fts5(
                doc_id,
                chunk_id,
                content,
                tokenize='unicode61'
            );

            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                aliases TEXT DEFAULT '[]',
                attributes TEXT DEFAULT '{}',
                mentions TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS timeline_events (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                event_time TEXT,
                description TEXT,
                participants TEXT DEFAULT '[]',
                source_refs TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '新对话',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS wiki_catalog (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                title TEXT NOT NULL,
                path TEXT NOT NULL,
                parent_id TEXT,
                node_order INTEGER NOT NULL DEFAULT 0,
                node_type TEXT NOT NULL DEFAULT 'page',
                description TEXT DEFAULT '',
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id),
                FOREIGN KEY (parent_id) REFERENCES wiki_catalog(id)
            );

            CREATE TABLE IF NOT EXISTS wiki_pages (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                catalog_path TEXT NOT NULL,
                title TEXT NOT NULL,
                page_type TEXT NOT NULL,
                content TEXT NOT NULL,
                frontmatter TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS wiki_analysis (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                report_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS compile_queue (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT DEFAULT '',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error TEXT,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );
        """)
        conn.commit()

        # Migration: add compile_status column to existing documents table
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN compile_status TEXT NOT NULL DEFAULT 'pending'")
            conn.commit()
        except Exception:
            pass  # Column already exists

        # Backfill compile_status from filesystem (runs every startup if needed)
        try:
            from app.config import settings
            docs = conn.execute("SELECT id, kb_id FROM documents WHERE compile_status = 'pending'").fetchall()
            for row in docs:
                l1_path = settings.KB_DIR / row["kb_id"] / "documents" / row["id"] / "l1_summaries.json"
                if l1_path.exists():
                    conn.execute(
                        "UPDATE documents SET compile_status = 'completed' WHERE id = ?",
                        (row["id"],),
                    )
            conn.commit()
        except Exception as e:
            import logging
            logging.warning("compile_status backfill failed: %s", e)
            conn.rollback()

        # Migration: add compile_queue table
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS compile_queue (
                    id TEXT PRIMARY KEY,
                    kb_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT DEFAULT '',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    error TEXT,
                    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
                )
            """)
            conn.commit()
        except Exception:
            logger.debug("compile_queue table already exists or migration skipped")

        # Migration: add kb_memory table for persistent cross-session memory
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kb_memory (
                    id TEXT PRIMARY KEY,
                    kb_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_sessions TEXT DEFAULT '[]',
                    relevance_score REAL DEFAULT 0.5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_memory_kb ON kb_memory(kb_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_memory_type ON kb_memory(kb_id, memory_type)")
            conn.commit()
        except Exception:
            pass

        # Migration: backfill compile_queue from existing KB compile_status
        try:
            cursor = conn.execute("SELECT id, compile_status FROM knowledge_bases WHERE compile_status IN ('processing', 'completed', 'failed')")
            for row in cursor.fetchall():
                conn.execute(
                    "INSERT OR IGNORE INTO compile_queue (id, kb_id, status, message) VALUES (?, ?, ?, ?)",
                    (f"cq_init_{row['id']}", row["id"], row["compile_status"], f"Initial state: {row['compile_status']}"),
                )
            conn.commit()
        except Exception:
            pass  # compile_queue may not exist yet

        # Migration: add parse_error column to documents table
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN parse_error TEXT DEFAULT NULL")
            conn.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add updated_at column to documents table
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            conn.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add chunk_count column to documents table
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add compile_detail column to documents table
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN compile_detail TEXT DEFAULT NULL")
            conn.commit()
        except Exception:
            pass  # Column already exists
    finally:
        conn.close()
