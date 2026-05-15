from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .config import project_path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    password TEXT,
    role TEXT NOT NULL DEFAULT 'member',
    anythingllm_user_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone TEXT NOT NULL,
    department TEXT,
    file_identifier TEXT,
    title TEXT NOT NULL,
    category TEXT,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL UNIQUE,
    raw_path TEXT,
    wiki_path TEXT,
    item_id TEXT,
    doc_number TEXT,
    serial_number TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT,
    synced_to_anythingllm INTEGER NOT NULL DEFAULT 0,
    anythingllm_doc_name TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_zone_dept ON documents(zone, department);
CREATE INDEX IF NOT EXISTS idx_documents_item_id ON documents(item_id);
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);

CREATE TABLE IF NOT EXISTS sign_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    signer TEXT NOT NULL,
    sign_time TEXT,
    opinion TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sign_records_unique
ON sign_records(item_id, signer, COALESCE(sign_time, ''), COALESCE(opinion, ''));

CREATE INDEX IF NOT EXISTS idx_sign_records_item_id ON sign_records(item_id);

CREATE TABLE IF NOT EXISTS anythingllm_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    ref TEXT NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, ref)
);

CREATE TABLE IF NOT EXISTS workspace_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_slug TEXT NOT NULL,
    document_id INTEGER NOT NULL,
    doc_ref TEXT NOT NULL,
    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_slug, document_id)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

MIGRATIONS = [
    "CREATE TABLE IF NOT EXISTS anythingllm_documents (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL, ref TEXT NOT NULL, uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(document_id, ref))",
    "CREATE TABLE IF NOT EXISTS workspace_documents (id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_slug TEXT NOT NULL, document_id INTEGER NOT NULL, doc_ref TEXT NOT NULL, synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(workspace_slug, document_id))",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_sign_records_unique ON sign_records(item_id, signer, COALESCE(sign_time, ''), COALESCE(opinion, ''))",
]


def connect(cfg: Dict[str, Any]) -> sqlite3.Connection:
    db_path = project_path(cfg, "db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(cfg: Dict[str, Any]) -> None:
    with connect(cfg) as conn:
        conn.executescript(SCHEMA)
        for sql in MIGRATIONS:
            conn.execute(sql)
        conn.commit()


def upsert_department(conn: sqlite3.Connection, name: str, slug: str) -> None:
    conn.execute(
        """
        INSERT INTO departments(name, slug) VALUES(?, ?)
        ON CONFLICT(name) DO UPDATE SET slug=excluded.slug
        """,
        (name, slug),
    )


def upsert_user(
    conn: sqlite3.Connection,
    department: str,
    username: str,
    password: str | None,
    role: str,
    anythingllm_user_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO users(department, username, password, role, anythingllm_user_id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
          department=excluded.department,
          password=excluded.password,
          role=excluded.role,
          anythingllm_user_id=COALESCE(excluded.anythingllm_user_id, users.anythingllm_user_id)
        """,
        (department, username, password, role or "member", anythingllm_user_id),
    )


def insert_sign_record(conn: sqlite3.Connection, item_id: str, signer: str, sign_time: str | None, opinion: str | None) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO sign_records(item_id, signer, sign_time, opinion)
        VALUES (?, ?, ?, ?)
        """,
        (item_id, signer, sign_time, opinion),
    )


def sign_records_for_item(conn: sqlite3.Connection, item_id: str | None):
    if not item_id:
        return []
    return conn.execute(
        "SELECT * FROM sign_records WHERE item_id=? ORDER BY sign_time, id", (item_id,)
    ).fetchall()


def upsert_document(conn: sqlite3.Connection, doc: Dict[str, Any]) -> int:
    keys = [
        "zone",
        "department",
        "file_identifier",
        "title",
        "category",
        "original_filename",
        "stored_path",
        "raw_path",
        "wiki_path",
        "item_id",
        "doc_number",
        "serial_number",
        "checksum",
    ]
    values = [doc.get(k) for k in keys]
    conn.execute(
        f"""
        INSERT INTO documents({','.join(keys)})
        VALUES ({','.join(['?'] * len(keys))})
        ON CONFLICT(stored_path) DO UPDATE SET
          zone=excluded.zone,
          department=excluded.department,
          file_identifier=excluded.file_identifier,
          title=excluded.title,
          category=excluded.category,
          original_filename=excluded.original_filename,
          raw_path=excluded.raw_path,
          wiki_path=excluded.wiki_path,
          item_id=excluded.item_id,
          doc_number=excluded.doc_number,
          serial_number=excluded.serial_number,
          checksum=excluded.checksum,
          synced_to_anythingllm=0
        """,
        values,
    )
    row = conn.execute("SELECT id FROM documents WHERE stored_path=?", (doc.get("stored_path"),)).fetchone()
    return int(row["id"])


def mark_document_uploaded(conn: sqlite3.Connection, document_id: int, ref: str) -> None:
    conn.execute(
        """
        INSERT INTO anythingllm_documents(document_id, ref)
        VALUES (?, ?)
        ON CONFLICT(document_id, ref) DO UPDATE SET uploaded_at=CURRENT_TIMESTAMP
        """,
        (document_id, ref),
    )
    conn.execute(
        "UPDATE documents SET anythingllm_doc_name=? WHERE id=?",
        (ref, document_id),
    )


def mark_workspace_document(conn: sqlite3.Connection, workspace_slug: str, document_id: int, doc_ref: str) -> None:
    conn.execute(
        """
        INSERT INTO workspace_documents(workspace_slug, document_id, doc_ref)
        VALUES (?, ?, ?)
        ON CONFLICT(workspace_slug, document_id) DO UPDATE SET doc_ref=excluded.doc_ref, synced_at=CURRENT_TIMESTAMP
        """,
        (workspace_slug, document_id, doc_ref),
    )


def mark_document_synced(conn: sqlite3.Connection, document_id: int) -> None:
    conn.execute("UPDATE documents SET synced_to_anythingllm=1 WHERE id=?", (document_id,))


def log_sync(conn: sqlite3.Connection, target: str, action: str, status: str, message: str | None = None) -> None:
    conn.execute(
        "INSERT INTO sync_log(target, action, status, message) VALUES (?, ?, ?, ?)",
        (target, action, status, message),
    )


def list_departments(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM departments ORDER BY id").fetchall()


def list_documents(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM documents ORDER BY imported_at DESC, id DESC").fetchall()


def get_document(conn: sqlite3.Connection, doc_id: int):
    return conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
