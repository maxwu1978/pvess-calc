"""Package-level QA checks for generated Web jobs.

This is the Web-facing counterpart to a manual review pass: it runs the
structural doctor, verifies the downloadable ZIP, and checks rendered PDFs
are readable enough to review.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from ..doctor import CheckResult, run_doctor


def build_package_qa(
    project_dir: Path,
    files: list[Any],
    *,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    """Run package QA and return a JSON-serializable report."""
    project_dir = Path(project_dir)
    doctor = run_doctor(project_dir)
    doctor_payload = _doctor_payload(doctor)
    archive_payload = _archive_payload(
        _resolve_archive_path(project_dir, files, archive_path)
    )
    pdf_payload = _pdf_payload(project_dir, files)

    status = _overall_status(doctor_payload, archive_payload, pdf_payload)
    return {
        "version": 1,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "doctor_failed": doctor_payload["failed"],
            "doctor_warned": doctor_payload["warned"],
            "pdf_failed": pdf_payload["failed"],
            "pdf_warned": pdf_payload["warned"],
            "archive_status": archive_payload["status"],
        },
        "doctor": doctor_payload,
        "archive": archive_payload,
        "pdfs": pdf_payload,
    }


def write_package_qa_artifacts(
    project_dir: Path,
    report: dict[str, Any],
) -> tuple[Path, Path]:
    output_dir = project_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "package-qa.json"
    md_path = output_dir / "package-qa.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(format_package_qa_markdown(report), encoding="utf-8")
    return json_path, md_path


def format_package_qa_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    doctor = report.get("doctor") or {}
    archive = report.get("archive") or {}
    pdfs = report.get("pdfs") or {}
    lines = [
        "# Package QA",
        "",
        f"- Status: **{report.get('status', 'UNKNOWN')}**",
        f"- Generated: `{report.get('generated_at', '')}`",
        f"- Doctor failures: {summary.get('doctor_failed', 0)}",
        f"- Doctor warnings: {summary.get('doctor_warned', 0)}",
        f"- PDF failures: {summary.get('pdf_failed', 0)}",
        f"- PDF warnings: {summary.get('pdf_warned', 0)}",
        f"- Archive: {archive.get('status', 'UNKNOWN')}",
        "",
        "## Doctor",
        "",
        (
            f"{doctor.get('passed', 0)} passed, "
            f"{doctor.get('warned', 0)} warned, "
            f"{doctor.get('failed', 0)} failed, "
            f"{doctor.get('skipped', 0)} skipped."
        ),
    ]
    if doctor.get("failures"):
        lines.extend(["", "### Failures", ""])
        lines.extend(_bullet_rows(doctor["failures"]))
    if doctor.get("warnings"):
        lines.extend(["", "### Warnings", ""])
        lines.extend(_bullet_rows(doctor["warnings"][:12]))

    lines.extend(["", "## Archive", ""])
    lines.append(
        f"- `{archive.get('path', '')}`: {archive.get('status', 'UNKNOWN')} "
        f"({archive.get('entry_count', 0)} entries)"
    )
    if archive.get("detail"):
        lines.append(f"- Detail: {archive['detail']}")

    lines.extend(["", "## PDFs", ""])
    for item in pdfs.get("items") or []:
        lines.append(
            f"- `{item.get('path', '')}`: {item.get('status', 'UNKNOWN')}; "
            f"{item.get('page_count', 0)} page(s); "
            f"{item.get('text_char_count', 0)} text chars"
        )
        if item.get("detail"):
            lines.append(f"  - {item['detail']}")
    if not (pdfs.get("items") or []):
        lines.append("- No PDF artifacts found.")
    lines.append("")
    return "\n".join(lines)


def _doctor_payload(results: list[CheckResult]) -> dict[str, Any]:
    failures = [_check_row(item) for item in results if item.status == "FAIL"]
    warnings = [_check_row(item) for item in results if item.status == "WARN"]
    return {
        "status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        "total": len(results),
        "passed": sum(1 for item in results if item.status == "PASS"),
        "warned": len(warnings),
        "failed": len(failures),
        "skipped": sum(1 for item in results if item.status == "SKIP"),
        "failures": failures,
        "warnings": warnings,
    }


def _check_row(item: CheckResult) -> dict[str, str]:
    return {
        "name": item.name,
        "status": item.status,
        "detail": item.detail,
    }


def _archive_payload(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "status": "WARN",
            "path": "",
            "entry_count": 0,
            "detail": "Complete Project ZIP not found.",
        }
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            names = zf.namelist()
    except Exception as exc:
        return {
            "status": "FAIL",
            "path": path.as_posix(),
            "entry_count": 0,
            "detail": f"ZIP unreadable: {exc}",
        }
    if bad:
        return {
            "status": "FAIL",
            "path": path.as_posix(),
            "entry_count": len(names),
            "detail": f"First corrupt archive member: {bad}",
        }
    return {
        "status": "PASS",
        "path": path.as_posix(),
        "entry_count": len(names),
        "detail": "Archive integrity check passed.",
    }


def _pdf_payload(project_dir: Path, files: list[Any]) -> dict[str, Any]:
    items = []
    for file in files:
        if _file_value(file, "kind") != "pdf":
            continue
        path = project_dir / str(_file_value(file, "path") or "")
        items.append(_pdf_item(path, label=str(_file_value(file, "label") or "")))
    failed = sum(1 for item in items if item["status"] == "FAIL")
    warned = sum(1 for item in items if item["status"] == "WARN")
    return {
        "status": "FAIL" if failed else ("WARN" if warned else "PASS"),
        "total": len(items),
        "failed": failed,
        "warned": warned,
        "items": items,
    }


def _pdf_item(path: Path, *, label: str) -> dict[str, Any]:
    base = {
        "label": label,
        "path": path.as_posix(),
        "status": "FAIL",
        "page_count": 0,
        "text_char_count": 0,
        "low_text_pages": [],
        "detail": "",
    }
    if not path.exists():
        base["detail"] = "PDF file is missing."
        return base
    try:
        reader = PdfReader(path)
        page_count = len(reader.pages)
        page_text_counts = [
            len((page.extract_text() or "").strip())
            for page in reader.pages
        ]
    except Exception as exc:
        base["detail"] = f"PDF unreadable: {exc}"
        return base
    low_text_pages = [
        idx + 1 for idx, count in enumerate(page_text_counts)
        if count < 8
    ]
    text_char_count = sum(page_text_counts)
    status = "PASS"
    detail = "PDF readable and searchable."
    if page_count == 0:
        status = "FAIL"
        detail = "PDF has no pages."
    elif low_text_pages and _is_core_pdf(label):
        status = "WARN"
        detail = "Core PDF has low-text pages: " + ", ".join(
            str(page) for page in low_text_pages[:12]
        )
    return {
        **base,
        "status": status,
        "page_count": page_count,
        "text_char_count": text_char_count,
        "low_text_pages": low_text_pages,
        "detail": detail,
    }


def _is_core_pdf(label: str) -> bool:
    lower = label.lower()
    return any(token in lower for token in (
        "permit package", "nec labels", "customer summary",
    ))


def _resolve_archive_path(
    project_dir: Path,
    files: list[Any],
    archive_path: Path | None,
) -> Path | None:
    if archive_path is not None and archive_path.exists():
        return archive_path
    for file in files:
        if _file_value(file, "kind") == "zip":
            path = project_dir / str(_file_value(file, "path") or "")
            if path.exists():
                return path
    matches = sorted((project_dir / "output").glob("project-package-*.zip"))
    return matches[-1] if matches else None


def _overall_status(
    doctor: dict[str, Any],
    archive: dict[str, Any],
    pdfs: dict[str, Any],
) -> str:
    if (
        doctor.get("status") == "FAIL"
        or archive.get("status") == "FAIL"
        or pdfs.get("status") == "FAIL"
    ):
        return "FAIL"
    if (
        doctor.get("status") == "WARN"
        or archive.get("status") == "WARN"
        or pdfs.get("status") == "WARN"
    ):
        return "WARN"
    return "PASS"


def _bullet_rows(rows: list[dict[str, str]]) -> list[str]:
    return [
        f"- `{row.get('name', '')}`: {row.get('detail', '')}"
        for row in rows
    ]


def _file_value(file: Any, key: str) -> Any:
    if isinstance(file, dict):
        return file.get(key)
    return getattr(file, key, None)
