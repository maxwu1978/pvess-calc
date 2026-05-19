"""SQLite job index for the local Web generator.

Generated artifacts stay on disk.  The database owns discovery and metadata
so the browser can list, filter, and migrate jobs without scanning every
project directory on each request.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any


JOB_DB_FILENAME = "web-jobs.sqlite3"
VALID_JOB_ID = re.compile(r"[A-Za-z0-9_.-]+")


class JobStore:
    def __init__(self, jobs_dir: Path, *, db_path: Path | None = None) -> None:
        self.jobs_dir = Path(jobs_dir)
        self.db_path = db_path or self.jobs_dir / JOB_DB_FILENAME
        self._lock = threading.Lock()
        self._initialized = False

    def ensure_ready(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self._initialized and self.db_path.exists():
            return
        with self._lock:
            if self._initialized and self.db_path.exists():
                return
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS web_jobs (
                        job_id TEXT PRIMARY KEY,
                        project_dir TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress INTEGER NOT NULL DEFAULT 0,
                        stage TEXT NOT NULL DEFAULT '',
                        message TEXT NOT NULL DEFAULT '',
                        owner_id TEXT NOT NULL DEFAULT 'local',
                        project_name TEXT NOT NULL DEFAULT '',
                        site_address TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        source_status TEXT NOT NULL DEFAULT '',
                        readiness_status TEXT NOT NULL DEFAULT '',
                        package_qa_status TEXT NOT NULL DEFAULT '',
                        installed_cost_usd REAL,
                        state_json TEXT NOT NULL,
                        payload_summary_json TEXT NOT NULL DEFAULT '{}',
                        source_materials_json TEXT NOT NULL DEFAULT '{}',
                        artifact_count INTEGER NOT NULL DEFAULT 0,
                        imported_from_legacy INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS web_job_artifacts (
                        job_id TEXT NOT NULL,
                        path TEXT NOT NULL,
                        label TEXT NOT NULL,
                        category TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        bytes INTEGER NOT NULL DEFAULT 0,
                        url TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY (job_id, path),
                        FOREIGN KEY (job_id)
                            REFERENCES web_jobs(job_id) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS web_operators (
                        operator_id TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        token_hash TEXT NOT NULL UNIQUE,
                        role TEXT NOT NULL DEFAULT 'operator',
                        created_at TEXT NOT NULL,
                        last_seen_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_web_jobs_owner
                        ON web_jobs(owner_id);
                    CREATE INDEX IF NOT EXISTS idx_web_jobs_status
                        ON web_jobs(status);
                    CREATE INDEX IF NOT EXISTS idx_web_jobs_created_at
                        ON web_jobs(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_web_jobs_project_name
                        ON web_jobs(project_name);
                    CREATE INDEX IF NOT EXISTS idx_web_jobs_site_address
                        ON web_jobs(site_address);
                    """
                )
                _ensure_column(
                    conn,
                    "web_jobs",
                    "owner_id",
                    "TEXT NOT NULL DEFAULT 'local'",
                )
                _ensure_column(
                    conn,
                    "web_jobs",
                    "package_qa_status",
                    "TEXT NOT NULL DEFAULT ''",
                )
            self._initialized = True

    def import_legacy_jobs(self) -> int:
        self.ensure_ready()
        imported = 0
        for status_path in sorted(self.jobs_dir.glob("*/job-status.json")):
            try:
                state = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            job_id = str(state.get("job_id") or status_path.parent.name)
            if not VALID_JOB_ID.fullmatch(job_id):
                continue
            if self._job_row(job_id) is not None:
                continue
            payload = _load_payload(status_path.parent / "request.json")
            self.upsert_state(state, payload=payload, imported_from_legacy=True)
            imported += 1
        return imported

    def upsert_state(
        self,
        state: dict[str, Any],
        *,
        payload: dict[str, Any] | None = None,
        owner_id: str | None = None,
        imported_from_legacy: bool = False,
    ) -> None:
        self.ensure_ready()
        job_id = str(state.get("job_id") or "")
        if not VALID_JOB_ID.fullmatch(job_id):
            raise ValueError("invalid job_id")
        existing = self._job_row(job_id)
        resolved_owner_id = _clean_operator_id(
            owner_id
            or state.get("owner_id")
            or (existing["owner_id"] if existing is not None else "")
            or "local"
        )
        payload_summary = (
            summarize_payload(payload)
            if payload is not None
            else json.loads(existing["payload_summary_json"])
            if existing is not None
            else {}
        )
        result = state.get("result") if isinstance(state.get("result"), dict) else {}
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        bom = result.get("bom") if isinstance(result.get("bom"), dict) else {}
        source_materials = (
            result.get("source_materials")
            if isinstance(result.get("source_materials"), dict)
            else {}
        )
        readiness = (
            result.get("readiness") if isinstance(result.get("readiness"), dict) else {}
        )
        package_qa = (
            result.get("package_qa")
            if isinstance(result.get("package_qa"), dict)
            else {}
        )
        files = result.get("files") if isinstance(result.get("files"), list) else []

        project_name = _first_text(
            summary.get("project_name"),
            payload_summary.get("project_name"),
            existing["project_name"] if existing is not None else "",
            job_id,
        )
        site_address = _first_text(
            payload_summary.get("site_address"),
            existing["site_address"] if existing is not None else "",
        )
        source_status = _first_text(
            source_materials.get("site_data_source"),
            existing["source_status"] if existing is not None else "",
        )
        readiness_status = _first_text(
            readiness.get("status"),
            existing["readiness_status"] if existing is not None else "",
        )
        package_qa_status = _first_text(
            package_qa.get("status"),
            existing["package_qa_status"] if existing is not None else "",
        )
        installed_cost = _float_or_none(
            bom.get("installed_cost_usd")
            if isinstance(bom, dict) else None
        )
        if installed_cost is None and existing is not None:
            installed_cost = existing["installed_cost_usd"]

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO web_jobs (
                    job_id, project_dir, status, progress, stage, message,
                    owner_id, project_name, site_address, created_at, updated_at,
                    source_status, readiness_status, package_qa_status,
                    installed_cost_usd,
                    state_json, payload_summary_json, source_materials_json,
                    artifact_count, imported_from_legacy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    project_dir = excluded.project_dir,
                    status = excluded.status,
                    progress = excluded.progress,
                    stage = excluded.stage,
                    message = excluded.message,
                    owner_id = excluded.owner_id,
                    project_name = excluded.project_name,
                    site_address = excluded.site_address,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    source_status = excluded.source_status,
                    readiness_status = excluded.readiness_status,
                    package_qa_status = excluded.package_qa_status,
                    installed_cost_usd = excluded.installed_cost_usd,
                    state_json = excluded.state_json,
                    payload_summary_json = excluded.payload_summary_json,
                    source_materials_json = excluded.source_materials_json,
                    artifact_count = excluded.artifact_count,
                    imported_from_legacy = (
                        web_jobs.imported_from_legacy
                        OR excluded.imported_from_legacy
                    )
                """,
                (
                    job_id,
                    str(state.get("project_dir") or self.jobs_dir / job_id),
                    str(state.get("status") or ""),
                    int(state.get("progress") or 0),
                    str(state.get("stage") or ""),
                    str(state.get("message") or ""),
                    resolved_owner_id,
                    project_name,
                    site_address,
                    str(state.get("created_at") or ""),
                    str(state.get("updated_at") or ""),
                    source_status,
                    readiness_status,
                    package_qa_status,
                    installed_cost,
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(payload_summary, ensure_ascii=False),
                    json.dumps(source_materials, ensure_ascii=False),
                    len(files),
                    1 if imported_from_legacy else 0,
                ),
            )
            conn.execute(
                "DELETE FROM web_job_artifacts WHERE job_id = ?",
                (job_id,),
            )
            conn.executemany(
                """
                INSERT INTO web_job_artifacts (
                    job_id, path, label, category, kind, bytes, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        job_id,
                        str(file.get("path") or ""),
                        str(file.get("label") or ""),
                        str(file.get("category") or ""),
                        str(file.get("kind") or ""),
                        int(file.get("bytes") or 0),
                        str(file.get("url") or ""),
                    )
                    for file in files
                    if isinstance(file, dict) and file.get("path")
                ],
            )

    def list_jobs(
        self,
        *,
        owner_id: str | None = None,
        include_all: bool = False,
        status: str | None = None,
        query: str = "",
        created_from: str = "",
        created_to: str = "",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        self.import_legacy_jobs()
        clauses: list[str] = []
        params: list[Any] = []
        if owner_id and not include_all:
            clauses.append("owner_id = ?")
            params.append(_clean_operator_id(owner_id))
        if status:
            clauses.append("status = ?")
            params.append(status)
        if query.strip():
            like = f"%{query.strip().lower()}%"
            clauses.append(
                "(lower(project_name) LIKE ? OR lower(site_address) LIKE ? "
                "OR lower(job_id) LIKE ?)"
            )
            params.extend([like, like, like])
        if created_from.strip():
            clauses.append("created_at >= ?")
            params.append(_date_floor(created_from))
        if created_to.strip():
            clauses.append("created_at <= ?")
            params.append(_date_ceiling(created_to))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT state_json FROM web_jobs {where} "
            "ORDER BY created_at DESC, job_id DESC LIMIT ?"
        )
        params.append(max(1, min(int(limit), 100)))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(row["state_json"]) for row in rows]

    def get_state(self, job_id: str) -> dict[str, Any] | None:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(job_id):
            return None
        row = self._job_row(job_id)
        if row is None:
            self.import_legacy_jobs()
            row = self._job_row(job_id)
        return json.loads(row["state_json"]) if row is not None else None

    def job_owner(self, job_id: str) -> str | None:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(job_id):
            return None
        row = self._job_row(job_id)
        if row is None:
            self.import_legacy_jobs()
            row = self._job_row(job_id)
        return str(row["owner_id"]) if row is not None else None

    def list_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(job_id):
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT path, label, category, kind, bytes, url
                FROM web_job_artifacts
                WHERE job_id = ?
                ORDER BY path
                """,
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_job(self, job_id: str) -> None:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(job_id):
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM web_jobs WHERE job_id = ?", (job_id,))

    def create_operator(
        self,
        *,
        display_name: str,
        operator_id: str = "",
    ) -> dict[str, str]:
        self.ensure_ready()
        base_id = _clean_operator_id(operator_id or display_name or "operator")
        token = f"op_{secrets.token_urlsafe(24)}"
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            resolved_id = base_id
            suffix = 2
            while conn.execute(
                "SELECT 1 FROM web_operators WHERE operator_id = ?",
                (resolved_id,),
            ).fetchone():
                resolved_id = f"{base_id}-{suffix}"
                suffix += 1
            conn.execute(
                """
                INSERT INTO web_operators (
                    operator_id, display_name, token_hash, role, created_at
                ) VALUES (?, ?, ?, 'operator', ?)
                """,
                (
                    resolved_id,
                    display_name.strip() or resolved_id,
                    _hash_token(token),
                    now,
                ),
            )
        return {
            "operator_id": resolved_id,
            "display_name": display_name.strip() or resolved_id,
            "token": token,
            "created_at": now,
        }

    def operator_for_token(self, token: str) -> dict[str, str] | None:
        self.ensure_ready()
        text = token.strip()
        if not text:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT operator_id, display_name, role, created_at, last_seen_at
                FROM web_operators
                WHERE token_hash = ?
                """,
                (_hash_token(text),),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE web_operators SET last_seen_at = ? WHERE operator_id = ?",
                (datetime.now(timezone.utc).isoformat(), row["operator_id"]),
            )
        return {key: str(row[key] or "") for key in row.keys()}

    def _job_row(self, job_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM web_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def summarize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "project_name": str(payload.get("project_name") or ""),
        "site_address": str(payload.get("site_address") or ""),
        "location": str(payload.get("location") or ""),
        "utility": str(payload.get("utility") or ""),
        "modules": payload.get("modules"),
        "battery_quantity": payload.get("battery_quantity"),
        "inverter_choice": payload.get("inverter_choice"),
    }


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _clean_operator_id(raw: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw or "").strip().lower())
    text = text.strip(".-")
    return text[:64] or "operator"


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _load_payload(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_floor(raw: str) -> str:
    text = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text}T00:00:00+00:00"
    return text


def _date_ceiling(raw: str) -> str:
    text = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text}T23:59:59.999999+00:00"
    return text
