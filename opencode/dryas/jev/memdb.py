"""Dryas memory store: one SQLite file in WAL mode, stdlib sqlite3 (owned core, sub-project B).

The schema is a language-neutral contract; other tools may read it. migrate() is idempotent and keyed by
PRAGMA user_version; a database written by a newer Dryas opens read-only. MEM-5: when this sqlite build has
no FTS5 (or DRYAS_NO_FTS=1) search falls back to LIKE and the FTS triggers are dropped so writes keep
working; the index is rebuilt the next time a connection has FTS5."""
import contextlib
import hashlib
import os
import sqlite3
import sys
import urllib.request
from typing import Iterator, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

SCHEMA_VERSION = 1
BUSY_MS = 1500

TABLES = (
    """CREATE TABLE IF NOT EXISTS memory (
        id INTEGER PRIMARY KEY, ns TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]', task_id TEXT, "commit" TEXT,
        source TEXT NOT NULL DEFAULT 'dryas', key TEXT, hash TEXT NOT NULL, embedding BLOB,
        meta TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL, accessed REAL, hits INTEGER NOT NULL DEFAULT 0)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS memory_key ON memory(ns, source, key) WHERE key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS memory_ns_kind ON memory(ns, kind, created)",
    "CREATE INDEX IF NOT EXISTS memory_hash ON memory(ns, hash)",
    """CREATE TABLE IF NOT EXISTS edits (ns TEXT NOT NULL, session TEXT, task_id TEXT, file TEXT NOT NULL,
        ok INTEGER NOT NULL, ts REAL NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS edits_ns ON edits(ns, ts)",
    """CREATE TABLE IF NOT EXISTS tasks (task_id TEXT NOT NULL, ns TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
        scope TEXT NOT NULL DEFAULT '[]', tier_start TEXT, tier_end TEXT, outcome TEXT, started REAL, ended REAL,
        meta TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (ns, task_id))""",
    "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, ns TEXT NOT NULL, started REAL, ended REAL, summary TEXT)",
    """CREATE TABLE IF NOT EXISTS patterns (ns TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, value TEXT,
        support INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL, PRIMARY KEY (ns, kind, key))""",
    "CREATE TABLE IF NOT EXISTS access (session TEXT NOT NULL, memory_id INTEGER NOT NULL, ts REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS access_mem ON access(memory_id)",
    """CREATE TABLE IF NOT EXISTS forgotten (ns TEXT NOT NULL, source TEXT NOT NULL, key TEXT NOT NULL,
        ts REAL NOT NULL, PRIMARY KEY (ns, source, key))""",
    "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)",
)
FTS = ("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(title, body, tags, content='memory', "
       "content_rowid='id')")
TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
        INSERT INTO memory_fts(rowid, title, body, tags) VALUES (new.id, new.title, new.body, new.tags); END""",
    """CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
        INSERT INTO memory_fts(memory_fts, rowid, title, body, tags)
        VALUES ('delete', old.id, old.title, old.body, old.tags); END""",
    """CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE OF title, body, tags ON memory BEGIN
        INSERT INTO memory_fts(memory_fts, rowid, title, body, tags)
        VALUES ('delete', old.id, old.title, old.body, old.tags);
        INSERT INTO memory_fts(rowid, title, body, tags) VALUES (new.id, new.title, new.body, new.tags); END""",
)
TRIGGER_NAMES = ("memory_ai", "memory_ad", "memory_au")


class Conn(sqlite3.Connection):
    """A connection that knows whether FTS5 search is usable and whether it may write."""
    fts = False
    readonly = False


def db_path() -> str:
    return os.environ.get("DRYAS_DB") or os.path.join(paths.data_root(), "dryas.db")


def content_hash(title: str, body: str) -> str:
    norm = " ".join(("%s\n%s" % (title, body)).split()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def fts5_available(conn: sqlite3.Connection) -> bool:
    if os.environ.get("DRYAS_NO_FTS") == "1":
        return False
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE temp.fts5_probe")
        return True
    except sqlite3.Error:
        return False


@contextlib.contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One write transaction. Takes the write lock up front, so a busy store fails at BEGIN, not halfway."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _kv(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None


def migrate(conn: Conn) -> None:
    with tx(conn):
        for stmt in TABLES:
            conn.execute(stmt)
        if conn.fts:
            conn.execute(FTS)
            for stmt in TRIGGERS:
                conn.execute(stmt)
            if _kv(conn, "fts") != "1":  # new store, or rows written while FTS5 was missing
                conn.execute("INSERT INTO memory_fts(memory_fts) VALUES ('rebuild')")
                conn.execute("INSERT OR REPLACE INTO kv(key, value) VALUES ('fts', '1')")
        else:
            for name in TRIGGER_NAMES:
                conn.execute("DROP TRIGGER IF EXISTS %s" % name)
            conn.execute("INSERT OR REPLACE INTO kv(key, value) VALUES ('fts', '0')")
        conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)


def _open(target: str, busy_ms: int, uri: bool = False) -> Conn:
    conn = sqlite3.connect(target, timeout=busy_ms / 1000.0, isolation_level=None, factory=Conn, uri=uri)
    conn.row_factory = sqlite3.Row
    return conn


def _tighten(p: str) -> None:
    """Make the store and its WAL/SHM files owner-only; a store left 0644 is fixed on the next connect."""
    for f in (p, p + "-wal", p + "-shm"):
        try:
            if os.stat(f).st_mode & 0o077:
                os.chmod(f, 0o600)  # portable-ok: POSIX file privacy; only called when os.name == "posix"
        except FileNotFoundError:
            pass


def connect(path: Optional[str] = None, busy_ms: int = BUSY_MS) -> Conn:
    """Open the store, creating or migrating it. Raises sqlite3.Error or OSError; callers degrade (MEM-5).
    On POSIX the files are created under umask 077 and tightened to 0600."""
    p = path or db_path()
    posix = os.name == "posix"
    old_umask = os.umask(0o077) if posix else None
    try:
        conn = _connect(p, busy_ms)
    finally:
        if posix:
            os.umask(old_umask)
    if posix:
        _tighten(p)
    return conn


def _connect(p: str, busy_ms: int) -> Conn:
    os.makedirs(os.path.dirname(os.path.abspath(p)), mode=0o700, exist_ok=True)
    conn = _open(p, busy_ms)
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver > SCHEMA_VERSION:  # written by a newer Dryas: read, never write
        conn.close()
        conn = _open("file:%s?mode=ro" % urllib.request.pathname2url(os.path.abspath(p)), busy_ms, uri=True)
        conn.readonly = True
        conn.fts = fts5_available(conn) and _has_table(conn, "memory_fts")
        return conn
    conn.fts = fts5_available(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    if not (ver == SCHEMA_VERSION and _kv(conn, "fts") == ("1" if conn.fts else "0")):
        migrate(conn)
    return conn
