"""QA primitives for reviewed roof DXF imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RoofReviewIssue:
    status: str
    message: str
    layer: str = ""
    entity: str = ""


@dataclass
class RoofReviewQA:
    issues: list[RoofReviewIssue] = field(default_factory=list)

    def add(self, status: str, message: str, *, layer: str = "", entity: str = "") -> None:
        self.issues.append(RoofReviewIssue(status, message, layer, entity))

    @property
    def failures(self) -> list[RoofReviewIssue]:
        return [issue for issue in self.issues if issue.status == "FAIL"]

    @property
    def warnings(self) -> list[RoofReviewIssue]:
        return [issue for issue in self.issues if issue.status == "WARN"]

    @property
    def status(self) -> str:
        return "FAIL" if self.failures else "WARN" if self.warnings else "PASS"

    def raise_if_failed(self) -> None:
        if self.failures:
            first = self.failures[0]
            raise RoofReviewImportError(first.message, qa=self)

    def as_lines(self) -> list[str]:
        if not self.issues:
            return ["PASS roof-review DXF QA"]
        return [
            f"{issue.status} {issue.layer or '-'}: {issue.message}"
            for issue in self.issues
        ]

    def as_markdown(self, *, dxf_path: Path | None = None) -> str:
        lines = [
            "# Roof Review QA Report",
            "",
            f"- Status: {self.status}",
        ]
        if dxf_path is not None:
            lines.append(f"- DXF: {dxf_path}")
        lines.extend([
            f"- Failures: {len(self.failures)}",
            f"- Warnings: {len(self.warnings)}",
            "",
        ])
        if not self.issues:
            lines.extend([
                "## Result",
                "",
                "PASS roof-review DXF QA",
            ])
            return "\n".join(lines) + "\n"
        lines.extend([
            "## Issues",
            "",
            "| Status | Layer | Entity | Message |",
            "|---|---|---|---|",
        ])
        for issue in self.issues:
            lines.append(
                "| "
                f"{_md(issue.status)} | "
                f"{_md(issue.layer or '-')} | "
                f"{_md(issue.entity or '-')} | "
                f"{_md(issue.message)} |"
            )
        lines.extend([
            "",
            "## CAD Return Instructions",
            "",
            "- Fix all FAIL rows before importing.",
            "- Review WARN rows before module placement or permit rendering.",
            "- Keep accepted final geometry on ROOF_* layers; REFERENCE_* layers are ignored by import.",
        ])
        return "\n".join(lines) + "\n"


class RoofReviewImportError(ValueError):
    """Raised when a reviewed DXF cannot be converted to schema YAML."""

    def __init__(self, message: str, *, qa: RoofReviewQA | None = None):
        super().__init__(message)
        self.qa = qa or RoofReviewQA([
            RoofReviewIssue("FAIL", message),
        ])


def qa_reviewed_dxf(dxf_path: Path) -> RoofReviewQA:
    """Run importer QA without writing artifacts."""
    from .dxf_import import import_reviewed_dxf

    try:
        imported = import_reviewed_dxf(Path(dxf_path), strict=False)
        return imported.qa
    except RoofReviewImportError as exc:
        return exc.qa


def write_qa_report(
    qa: RoofReviewQA,
    output_path: Path,
    *,
    dxf_path: Path | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(qa.as_markdown(dxf_path=dxf_path), encoding="utf-8")
    return output_path


def _md(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
