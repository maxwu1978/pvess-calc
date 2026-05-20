"""Lead notification helpers for the local Web generator."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


LEAD_NOTIFICATION_MODES = {"off", "dry_run", "webhook"}


@dataclass(frozen=True)
class LeadNotificationConfig:
    mode: str = "dry_run"
    webhook_url: str = ""
    public_base_url: str = ""
    timeout_s: float = 5.0

    @property
    def normalized_mode(self) -> str:
        mode = self.mode.strip().lower()
        return mode if mode in LEAD_NOTIFICATION_MODES else "dry_run"


@dataclass(frozen=True)
class WebhookResult:
    status_code: int
    body: str = ""


@dataclass(frozen=True)
class NotificationDispatchResult:
    status: str
    attempted: bool
    response_text: str = ""
    error: str = ""
    sent_at: str = ""


def default_lead_notification_config() -> LeadNotificationConfig:
    timeout_raw = os.environ.get("PVESS_LEAD_NOTIFICATION_TIMEOUT_S", "").strip()
    try:
        timeout_s = float(timeout_raw) if timeout_raw else 5.0
    except ValueError:
        timeout_s = 5.0
    return LeadNotificationConfig(
        mode=os.environ.get("PVESS_LEAD_NOTIFICATION_MODE", "dry_run"),
        webhook_url=os.environ.get("PVESS_LEAD_NOTIFICATION_WEBHOOK_URL", "").strip(),
        public_base_url=os.environ.get("PVESS_PUBLIC_BASE_URL", "").strip().rstrip("/"),
        timeout_s=max(0.5, min(timeout_s, 30.0)),
    )


def lead_notification_config_summary(config: LeadNotificationConfig) -> dict[str, Any]:
    return {
        "mode": config.normalized_mode,
        "webhook_configured": bool(config.webhook_url),
        "public_base_url_configured": bool(config.public_base_url),
    }


def build_new_lead_notification(
    lead: dict[str, Any],
    *,
    config: LeadNotificationConfig,
) -> dict[str, Any]:
    lead_id = str(lead.get("lead_id") or "")
    address = str(lead.get("site_address") or "").strip()
    name = str(lead.get("contact_name") or "").strip()
    project_type = _project_type_label(str(lead.get("project_type") or ""))
    usage = _usage_summary(lead.get("monthly_kwh") or [])
    subject = f"New TGE Solar lead: {name or address or lead_id}"
    body = "\n".join([
        f"Lead: {name or 'Homeowner'}",
        f"Address: {address or 'not provided'}",
        f"Email: {str(lead.get('email') or '').strip() or 'not provided'}",
        f"Phone: {str(lead.get('phone') or '').strip() or 'not provided'}",
        f"Project type: {project_type}",
        f"Utility: {str(lead.get('utility') or '').strip() or 'not provided'}",
        f"Usage: {usage}",
        f"Notes: {str(lead.get('notes') or '').strip() or 'none'}",
    ])
    dashboard_url = f"{config.public_base_url}/" if config.public_base_url else ""
    payload = {
        "event": "new_lead",
        "notification_id": _make_notification_id(),
        "lead": _lead_payload(lead),
        "subject": subject,
        "body": body,
        "dashboard_url": dashboard_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "notification_id": payload["notification_id"],
        "lead_id": lead_id,
        "event": "new_lead",
        "channel": config.normalized_mode,
        "status": "pending",
        "attempts": 0,
        "recipient": "operator",
        "subject": subject,
        "body": body,
        "payload": payload,
    }


def dispatch_lead_notification(
    notification: dict[str, Any],
    *,
    config: LeadNotificationConfig,
) -> NotificationDispatchResult:
    mode = config.normalized_mode
    if mode == "off":
        return NotificationDispatchResult(
            status="skipped",
            attempted=False,
            response_text="Lead notifications are disabled.",
        )
    if mode == "dry_run":
        return NotificationDispatchResult(
            status="sent",
            attempted=True,
            response_text="Dry-run notification recorded.",
            sent_at=datetime.now(timezone.utc).isoformat(),
        )
    if not config.webhook_url:
        return NotificationDispatchResult(
            status="failed",
            attempted=True,
            error="PVESS_LEAD_NOTIFICATION_WEBHOOK_URL is not configured.",
        )
    try:
        response = post_webhook_json(
            config.webhook_url,
            notification.get("payload") or {},
            timeout_s=config.timeout_s,
        )
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
        return NotificationDispatchResult(
            status="failed",
            attempted=True,
            error=str(exc)[:500],
        )
    return NotificationDispatchResult(
        status="sent",
        attempted=True,
        response_text=f"Webhook HTTP {response.status_code}: {response.body[:300]}",
        sent_at=datetime.now(timezone.utc).isoformat(),
    )


def post_webhook_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_s: float,
) -> WebhookResult:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "pvess-calc-web/lead-notifier",
        },
    )
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - user URL.
        body = response.read().decode("utf-8", errors="replace")
        return WebhookResult(status_code=response.status, body=body)


def _make_notification_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"note-{stamp}-{uuid4().hex[:8]}"


def _lead_payload(lead: dict[str, Any]) -> dict[str, Any]:
    return {
        "lead_id": str(lead.get("lead_id") or ""),
        "status": str(lead.get("status") or ""),
        "contact_name": str(lead.get("contact_name") or ""),
        "email": str(lead.get("email") or ""),
        "phone": str(lead.get("phone") or ""),
        "site_address": str(lead.get("site_address") or ""),
        "project_type": str(lead.get("project_type") or ""),
        "utility": str(lead.get("utility") or ""),
        "monthly_kwh": lead.get("monthly_kwh") or [],
        "campaign_source": str(lead.get("campaign_source") or ""),
        "campaign_medium": str(lead.get("campaign_medium") or ""),
        "campaign_name": str(lead.get("campaign_name") or ""),
        "campaign_content": str(lead.get("campaign_content") or ""),
        "referrer": str(lead.get("referrer") or ""),
        "landing_url": str(lead.get("landing_url") or ""),
        "created_at": str(lead.get("created_at") or ""),
    }


def _project_type_label(value: str) -> str:
    if value == "pv_only":
        return "Solar only"
    if value == "not_sure":
        return "Not sure yet"
    return "Solar + battery"


def _usage_summary(values: Any) -> str:
    if not isinstance(values, list) or len(values) != 12:
        return "not provided"
    monthly: list[float] = []
    for value in values:
        try:
            monthly.append(float(value))
        except (TypeError, ValueError):
            return "not provided"
    if not monthly:
        return "not provided"
    return f"average {sum(monthly) / len(monthly):.0f} kWh/month"
