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
                    CREATE TABLE IF NOT EXISTS web_leads (
                        lead_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL DEFAULT 'new',
                        contact_name TEXT NOT NULL DEFAULT '',
                        email TEXT NOT NULL DEFAULT '',
                        phone TEXT NOT NULL DEFAULT '',
                        site_address TEXT NOT NULL DEFAULT '',
                        project_type TEXT NOT NULL DEFAULT 'pv_ess',
                        utility TEXT NOT NULL DEFAULT '',
                        monthly_kwh_json TEXT NOT NULL DEFAULT '[]',
                        notes TEXT NOT NULL DEFAULT '',
                        utility_bill_path TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL DEFAULT 'public_form',
                        campaign_source TEXT NOT NULL DEFAULT '',
                        campaign_medium TEXT NOT NULL DEFAULT '',
                        campaign_name TEXT NOT NULL DEFAULT '',
                        campaign_content TEXT NOT NULL DEFAULT '',
                        referrer TEXT NOT NULL DEFAULT '',
                        landing_url TEXT NOT NULL DEFAULT '',
                        converted_job_id TEXT NOT NULL DEFAULT '',
                        last_contacted_at TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS web_lead_notifications (
                        notification_id TEXT PRIMARY KEY,
                        lead_id TEXT NOT NULL DEFAULT '',
                        event TEXT NOT NULL DEFAULT 'new_lead',
                        channel TEXT NOT NULL DEFAULT 'dry_run',
                        status TEXT NOT NULL DEFAULT 'pending',
                        attempts INTEGER NOT NULL DEFAULT 0,
                        recipient TEXT NOT NULL DEFAULT '',
                        subject TEXT NOT NULL DEFAULT '',
                        body TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{}',
                        response_text TEXT NOT NULL DEFAULT '',
                        error TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        sent_at TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL
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
                    CREATE INDEX IF NOT EXISTS idx_web_leads_status
                        ON web_leads(status);
                    CREATE INDEX IF NOT EXISTS idx_web_leads_created_at
                        ON web_leads(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_web_leads_email
                        ON web_leads(email);
                    CREATE INDEX IF NOT EXISTS idx_web_leads_site_address
                        ON web_leads(site_address);
                    CREATE INDEX IF NOT EXISTS idx_web_lead_notifications_created_at
                        ON web_lead_notifications(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_web_lead_notifications_status
                        ON web_lead_notifications(status);
                    CREATE INDEX IF NOT EXISTS idx_web_lead_notifications_lead
                        ON web_lead_notifications(lead_id);
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
                _ensure_column(
                    conn,
                    "web_leads",
                    "last_contacted_at",
                    "TEXT NOT NULL DEFAULT ''",
                )
                for column in [
                    "campaign_source",
                    "campaign_medium",
                    "campaign_name",
                    "campaign_content",
                    "referrer",
                    "landing_url",
                ]:
                    _ensure_column(
                        conn,
                        "web_leads",
                        column,
                        "TEXT NOT NULL DEFAULT ''",
                    )
                conn.executescript(
                    """
                    CREATE INDEX IF NOT EXISTS idx_web_leads_campaign_source
                        ON web_leads(campaign_source);
                    CREATE INDEX IF NOT EXISTS idx_web_leads_campaign_name
                        ON web_leads(campaign_name);
                    """
                )
                _ensure_column(
                    conn,
                    "web_lead_notifications",
                    "response_text",
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

    def create_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        self.ensure_ready()
        lead_id = str(lead.get("lead_id") or "")
        if not VALID_JOB_ID.fullmatch(lead_id):
            raise ValueError("invalid lead_id")
        now = str(lead.get("created_at") or datetime.now(timezone.utc).isoformat())
        row = {
            "lead_id": lead_id,
            "status": str(lead.get("status") or "new"),
            "contact_name": str(lead.get("contact_name") or ""),
            "email": str(lead.get("email") or ""),
            "phone": str(lead.get("phone") or ""),
            "site_address": str(lead.get("site_address") or ""),
            "project_type": str(lead.get("project_type") or "pv_ess"),
            "utility": str(lead.get("utility") or ""),
            "monthly_kwh_json": json.dumps(
                lead.get("monthly_kwh") or [],
                ensure_ascii=False,
            ),
            "notes": str(lead.get("notes") or ""),
            "utility_bill_path": str(lead.get("utility_bill_path") or ""),
            "source": str(lead.get("source") or "public_form"),
            "campaign_source": str(lead.get("campaign_source") or ""),
            "campaign_medium": str(lead.get("campaign_medium") or ""),
            "campaign_name": str(lead.get("campaign_name") or ""),
            "campaign_content": str(lead.get("campaign_content") or ""),
            "referrer": str(lead.get("referrer") or ""),
            "landing_url": str(lead.get("landing_url") or ""),
            "converted_job_id": str(lead.get("converted_job_id") or ""),
            "last_contacted_at": str(lead.get("last_contacted_at") or ""),
            "created_at": now,
            "updated_at": str(lead.get("updated_at") or now),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO web_leads (
                    lead_id, status, contact_name, email, phone,
                    site_address, project_type, utility, monthly_kwh_json,
                    notes, utility_bill_path, source,
                    campaign_source, campaign_medium, campaign_name,
                    campaign_content, referrer, landing_url,
                    converted_job_id,
                    last_contacted_at,
                    created_at, updated_at
                ) VALUES (
                    :lead_id, :status, :contact_name, :email, :phone,
                    :site_address, :project_type, :utility, :monthly_kwh_json,
                    :notes, :utility_bill_path, :source,
                    :campaign_source, :campaign_medium, :campaign_name,
                    :campaign_content, :referrer, :landing_url,
                    :converted_job_id,
                    :last_contacted_at,
                    :created_at, :updated_at
                )
                """,
                row,
            )
        return _lead_from_row(row)

    def list_leads(
        self,
        *,
        status: str | None = None,
        query: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.ensure_ready()
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            if status == "active":
                clauses.append("status != ?")
                params.append("archived")
            else:
                clauses.append("status = ?")
                params.append(status)
        if query.strip():
            like = f"%{query.strip().lower()}%"
            clauses.append(
                "(lower(contact_name) LIKE ? OR lower(email) LIKE ? "
                "OR lower(site_address) LIKE ? OR lower(lead_id) LIKE ? "
                "OR lower(campaign_source) LIKE ? "
                "OR lower(campaign_medium) LIKE ? "
                "OR lower(campaign_name) LIKE ?)"
            )
            params.extend([like, like, like, like, like, like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM web_leads {where} "
            "ORDER BY created_at DESC, lead_id DESC LIMIT ?"
        )
        params.append(max(1, min(int(limit), 100)))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_lead_from_row(row) for row in rows]

    def lead_metrics(self) -> dict[str, Any]:
        self.ensure_ready()
        with self._connect() as conn:
            status_rows = conn.execute(
                """
                SELECT status, count(*) AS count
                FROM web_leads
                GROUP BY status
                ORDER BY count DESC, status
                """
            ).fetchall()
            source_rows = conn.execute(
                """
                SELECT campaign_source, count(*) AS count
                FROM web_leads
                GROUP BY campaign_source
                ORDER BY count DESC, campaign_source
                LIMIT 8
                """
            ).fetchall()
            campaign_rows = conn.execute(
                """
                SELECT campaign_name, count(*) AS count
                FROM web_leads
                WHERE campaign_name != ''
                GROUP BY campaign_name
                ORDER BY count DESC, campaign_name
                LIMIT 8
                """
            ).fetchall()
            totals = conn.execute(
                """
                SELECT
                    count(*) AS total,
                    sum(CASE WHEN status = 'converted' THEN 1 ELSE 0 END)
                        AS converted
                FROM web_leads
                """
            ).fetchone()
        total = int(totals["total"] or 0) if totals is not None else 0
        converted = int(totals["converted"] or 0) if totals is not None else 0
        return {
            "total": total,
            "converted": converted,
            "conversion_rate": (converted / total) if total else 0.0,
            "by_status": [
                {"key": str(row["status"] or "unknown"), "count": int(row["count"])}
                for row in status_rows
            ],
            "by_source": [
                {
                    "key": str(row["campaign_source"] or "direct"),
                    "count": int(row["count"]),
                }
                for row in source_rows
            ],
            "by_campaign": [
                {"key": str(row["campaign_name"]), "count": int(row["count"])}
                for row in campaign_rows
            ],
        }

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(lead_id):
            return None
        row = self._lead_row(lead_id)
        return _lead_from_row(row) if row is not None else None

    def update_lead(
        self,
        lead_id: str,
        *,
        status: str | None = None,
        notes: str | None = None,
        mark_contacted: bool = False,
    ) -> dict[str, Any]:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(lead_id):
            raise ValueError("invalid lead_id")
        allowed = {"new", "contacted", "qualified", "converted", "archived"}
        assignments: list[str] = []
        params: list[Any] = []
        if status is not None:
            if status not in allowed:
                raise ValueError("invalid lead status")
            assignments.append("status = ?")
            params.append(status)
        if notes is not None:
            assignments.append("notes = ?")
            params.append(str(notes)[:1000])
        if mark_contacted or status == "contacted":
            assignments.append("last_contacted_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())
        if not assignments:
            row = self._lead_row(lead_id)
            if row is None:
                raise ValueError("lead not found")
            return _lead_from_row(row)
        assignments.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(lead_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE web_leads SET {', '.join(assignments)} WHERE lead_id = ?",
                params,
            )
        row = self._lead_row(lead_id)
        if row is None:
            raise ValueError("lead not found")
        return _lead_from_row(row)

    def mark_lead_converted(
        self,
        lead_id: str,
        *,
        converted_job_id: str,
    ) -> dict[str, Any]:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(lead_id):
            raise ValueError("invalid lead_id")
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE web_leads
                SET status = 'converted',
                    converted_job_id = ?,
                    last_contacted_at = COALESCE(NULLIF(last_contacted_at, ''), ?),
                    updated_at = ?
                WHERE lead_id = ?
                """,
                (converted_job_id, updated_at, updated_at, lead_id),
            )
        row = self._lead_row(lead_id)
        if row is None:
            raise ValueError("lead not found")
        return _lead_from_row(row)

    def create_lead_notification(
        self,
        notification: dict[str, Any],
    ) -> dict[str, Any]:
        self.ensure_ready()
        notification_id = str(notification.get("notification_id") or "")
        if not VALID_JOB_ID.fullmatch(notification_id):
            raise ValueError("invalid notification_id")
        now = str(
            notification.get("created_at")
            or datetime.now(timezone.utc).isoformat()
        )
        payload = notification.get("payload") or {}
        row = {
            "notification_id": notification_id,
            "lead_id": str(notification.get("lead_id") or ""),
            "event": str(notification.get("event") or "new_lead"),
            "channel": str(notification.get("channel") or "dry_run"),
            "status": str(notification.get("status") or "pending"),
            "attempts": int(notification.get("attempts") or 0),
            "recipient": str(notification.get("recipient") or ""),
            "subject": str(notification.get("subject") or ""),
            "body": str(notification.get("body") or ""),
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "response_text": str(notification.get("response_text") or ""),
            "error": str(notification.get("error") or ""),
            "created_at": now,
            "sent_at": str(notification.get("sent_at") or ""),
            "updated_at": str(notification.get("updated_at") or now),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO web_lead_notifications (
                    notification_id, lead_id, event, channel, status,
                    attempts, recipient, subject, body, payload_json,
                    response_text, error, created_at, sent_at, updated_at
                ) VALUES (
                    :notification_id, :lead_id, :event, :channel, :status,
                    :attempts, :recipient, :subject, :body, :payload_json,
                    :response_text, :error, :created_at, :sent_at, :updated_at
                )
                """,
                row,
            )
        return _lead_notification_from_row(row)

    def list_lead_notifications(
        self,
        *,
        status: str | None = None,
        lead_id: str = "",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        self.ensure_ready()
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 100)))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM web_lead_notifications
                {where}
                ORDER BY created_at DESC, notification_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_lead_notification_from_row(row) for row in rows]

    def get_lead_notification(
        self,
        notification_id: str,
    ) -> dict[str, Any] | None:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(notification_id):
            return None
        row = self._lead_notification_row(notification_id)
        return _lead_notification_from_row(row) if row is not None else None

    def update_lead_notification_result(
        self,
        notification_id: str,
        *,
        status: str,
        attempts: int,
        response_text: str = "",
        error: str = "",
        sent_at: str = "",
        channel: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_ready()
        if not VALID_JOB_ID.fullmatch(notification_id):
            raise ValueError("invalid notification_id")
        assignments = [
            "status = ?",
            "attempts = ?",
            "response_text = ?",
            "error = ?",
            "sent_at = ?",
            "updated_at = ?",
        ]
        params: list[Any] = [
            status,
            max(0, int(attempts)),
            response_text[:1000],
            error[:1000],
            sent_at,
            datetime.now(timezone.utc).isoformat(),
        ]
        if channel is not None:
            assignments.append("channel = ?")
            params.append(channel)
        params.append(notification_id)
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE web_lead_notifications
                SET {', '.join(assignments)}
                WHERE notification_id = ?
                """,
                params,
            )
        row = self._lead_notification_row(notification_id)
        if row is None:
            raise ValueError("notification not found")
        return _lead_notification_from_row(row)

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

    def _lead_row(self, lead_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM web_leads WHERE lead_id = ?",
                (lead_id,),
            ).fetchone()

    def _lead_notification_row(
        self,
        notification_id: str,
    ) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM web_lead_notifications WHERE notification_id = ?",
                (notification_id,),
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


def _lead_from_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    keys = set(row.keys())
    monthly_raw = row["monthly_kwh_json"] if "monthly_kwh_json" in keys else "[]"
    try:
        monthly = json.loads(monthly_raw or "[]")
    except json.JSONDecodeError:
        monthly = []
    return {
        "lead_id": str(row["lead_id"]),
        "status": str(row["status"] or "new"),
        "contact_name": str(row["contact_name"] or ""),
        "email": str(row["email"] or ""),
        "phone": str(row["phone"] or ""),
        "site_address": str(row["site_address"] or ""),
        "project_type": str(row["project_type"] or "pv_ess"),
        "utility": str(row["utility"] or ""),
        "monthly_kwh": monthly if isinstance(monthly, list) else [],
        "notes": str(row["notes"] or ""),
        "utility_bill_path": str(row["utility_bill_path"] or ""),
        "source": str(row["source"] or "public_form"),
        "campaign_source": str(row["campaign_source"] or ""),
        "campaign_medium": str(row["campaign_medium"] or ""),
        "campaign_name": str(row["campaign_name"] or ""),
        "campaign_content": str(row["campaign_content"] or ""),
        "referrer": str(row["referrer"] or ""),
        "landing_url": str(row["landing_url"] or ""),
        "converted_job_id": str(row["converted_job_id"] or ""),
        "last_contacted_at": str(row["last_contacted_at"] or ""),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _lead_notification_from_row(
    row: sqlite3.Row | dict[str, Any],
) -> dict[str, Any]:
    keys = set(row.keys())
    payload_raw = row["payload_json"] if "payload_json" in keys else "{}"
    try:
        payload = json.loads(payload_raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "notification_id": str(row["notification_id"]),
        "lead_id": str(row["lead_id"] or ""),
        "event": str(row["event"] or "new_lead"),
        "channel": str(row["channel"] or "dry_run"),
        "status": str(row["status"] or "pending"),
        "attempts": int(row["attempts"] or 0),
        "recipient": str(row["recipient"] or ""),
        "subject": str(row["subject"] or ""),
        "body": str(row["body"] or ""),
        "payload": payload if isinstance(payload, dict) else {},
        "response_text": str(row["response_text"] or ""),
        "error": str(row["error"] or ""),
        "created_at": str(row["created_at"] or ""),
        "sent_at": str(row["sent_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
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
