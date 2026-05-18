"""Assemble the complete permit submittal PDF.

Pipeline:
1. Generate DXF sheets EE-1 (three-line) and EE-2 (grounding) → convert to PDF.
2. Generate native PDF sheets EE-0 (cover), EE-3 (panels), EE-4 (site), EE-5 (checklist).
3. Re-use existing labels.pdf as EE-6.
4. Merge all into a single multi-page PDF in the project's output/ directory.
"""
from __future__ import annotations

import importlib
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader, PdfWriter

from ..calc.engine import CalculationResult
from ..dxf.grounding_sheet import render_grounding_dxf
from ..dxf.render import render_dxf
from ..labels.render import render_for_result as render_labels
from .compliance import render_compliance_checklist
from .cover_sheet import render_cover_sheet
from .sheet_registry import (
    SheetSpec,
    cover_index_rows,
    registry_for_profile,
)


def _project_dir(result) -> Path:
    return Path.cwd() / "projects" / result.inputs.project.id


def _resolve_project_path(result, path: str) -> Path:
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    return _project_dir(result) / p


def _collect_cut_sheets(result) -> list[Path]:
    """Walk a project's cut_sheets/ directory and return every PDF found.

    Convention: place manufacturer datasheets in
      projects/<id>/cut_sheets/*.pdf
    and they'll be appended in alphabetical order at the back of the permit
    package. Common order:
      01-module.pdf · 02-inverter.pdf · 03-optimizer.pdf · 04-battery.pdf · ...
    """
    candidates = [_project_dir(result) / "cut_sheets"]
    out: list[Path] = []
    for d in candidates:
        if d.exists() and d.is_dir():
            out.extend(sorted(d.glob("*.pdf")))
    return out


def _selected_sheets(
    result: CalculationResult,
    *,
    package_profile: str,
    ahj_name: str | None,
) -> list[SheetSpec]:
    from ..ahj.profile import get_ahj_profile

    registry = list(registry_for_profile(package_profile))
    if ahj_name:
        required = set(get_ahj_profile(ahj_name).required_sheets)
        registry = [s for s in registry if s.code in required]

    if not _should_emit_one_line(result):
        registry = [s for s in registry if s.code != "one-line"]
    return registry


def _should_emit_one_line(result: CalculationResult) -> bool:
    methods = set(result.inputs.service.interconnection_methods)
    return bool(
        result.interconnect.recommended == "supply_side_tap"
        or "supply_side_tap" in methods
        or "service_intercept" in methods
        or "line_side_tap" in methods
    )


def _render_sheet(
    result: CalculationResult,
    spec: SheetSpec,
    out_path: Path,
    *,
    sheet_rows: list[tuple[str, str]],
) -> list[Path]:
    with _sheet_context(result, spec):
        if spec.code == "cover":
            render_cover_sheet(result, out_path, sheet_rows=sheet_rows)
            return [out_path]

        if spec.code == "spec":
            return _render_or_collect_specs(result, out_path)

        module_name, _, callable_name = spec.renderer.partition(":")
        if not module_name or not callable_name:
            raise ValueError(f"bad renderer path: {spec.renderer}")
        renderer = getattr(importlib.import_module(module_name), callable_name)

        if spec.output_kind == "dxf":
            dxf_path = out_path.with_suffix(".dxf")
            renderer(result, dxf_path)
            _dxf_to_pdf(dxf_path, out_path)
            return [out_path]

        # Labels renderer returns a label count; PDF renderers return None.
        renderer(result, out_path)
        return [out_path]


@contextmanager
def _sheet_context(result: CalculationResult, spec: SheetSpec):
    sentinel = object()
    old_code = getattr(result, "_active_sheet_display_code", sentinel)
    old_title = getattr(result, "_active_sheet_title", sentinel)
    result._active_sheet_display_code = spec.display_code
    result._active_sheet_title = spec.title
    try:
        yield
    finally:
        if old_code is sentinel:
            delattr(result, "_active_sheet_display_code")
        else:
            result._active_sheet_display_code = old_code
        if old_title is sentinel:
            delattr(result, "_active_sheet_title")
        else:
            result._active_sheet_title = old_title


def _render_or_collect_specs(result: CalculationResult, placeholder: Path) -> list[Path]:
    from .spec_sheets import render_spec_placeholder

    explicit: list[Path] = []
    for ref in result.inputs.project.spec_sheets:
        if not ref.path:
            continue
        p = _resolve_project_path(result, ref.path)
        if p.exists() and p.suffix.lower() == ".pdf":
            explicit.append(p)
    cut_sheets = _collect_cut_sheets(result)
    if explicit or cut_sheets:
        out: list[Path] = []
        seen: set[Path] = set()
        for p in explicit + cut_sheets:
            key = p.resolve()
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out
    render_spec_placeholder(result, placeholder)
    return [placeholder]


def _prepend_structural_packet(
    result: CalculationResult,
    tmp_dir: Path,
    *,
    package_profile: str,
) -> list[Path]:
    if package_profile == "internal":
        return []

    src = result.inputs.project.structural_letter_pdf
    if src:
        p = _resolve_project_path(result, src)
        if p.exists() and p.suffix.lower() == ".pdf":
            return [p]

    from .structural_letter import render_structural_letter_draft
    out = tmp_dir / "00-structural-letter-draft.pdf"
    render_structural_letter_draft(result, out)
    return [out]


def _dxf_to_pdf(dxf_path: Path, pdf_path: Path) -> None:
    """Render a DXF to a single-page PDF via matplotlib backend."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing import config as draw_config
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = ezdxf.readfile(str(dxf_path))
    cfg = draw_config.Configuration(
        background_policy=draw_config.BackgroundPolicy.WHITE
    )
    # ANSI B 17×11" landscape
    fig, ax = plt.subplots(figsize=(17, 11), dpi=150)
    ax.set_axis_off()
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(
        doc.modelspace(), finalize=True
    )
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(
        str(pdf_path), format="pdf",
        bbox_inches="tight", pad_inches=0.1, facecolor="white",
    )
    plt.close(fig)


def build_permit_package(
    result: CalculationResult,
    out_path: Path,
    *,
    ahj_name: str | None = None,
    package_profile: str | None = None,
) -> int:
    """Build the full permit PDF. Returns the number of pages."""
    package_profile = package_profile or result.inputs.project.permit_profile

    with TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        pdfs: list[Path] = []
        specs = _selected_sheets(
            result, package_profile=package_profile, ahj_name=ahj_name,
        )
        sheet_rows = [(s.display_code, s.title) for s in specs]

        pdfs.extend(_prepend_structural_packet(
            result, tmp_dir, package_profile=package_profile,
        ))
        for idx, spec in enumerate(specs, 1):
            safe_code = spec.display_code.lower().replace(".", "-")
            p = tmp_dir / f"{idx:02d}-{safe_code}.pdf"
            pdfs.extend(_render_sheet(result, spec, p, sheet_rows=sheet_rows))

        # Combine all PDFs into one
        writer = PdfWriter()
        page_count = 0
        for pdf in pdfs:
            reader = PdfReader(str(pdf))
            if pdf in _spec_paths_with_page_subset(result):
                # Page-subset handling is performed below by path lookup.
                pass
            page_subset = _page_subset_for_spec(result, pdf)
            pages = (
                [reader.pages[i - 1] for i in page_subset
                 if 1 <= i <= len(reader.pages)]
                if page_subset else reader.pages
            )
            for page in pages:
                writer.add_page(page)
                page_count += 1

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            writer.write(f)

        return page_count


def _spec_paths_with_page_subset(result) -> set[Path]:
    return {
        _resolve_project_path(result, ref.path)
        for ref in result.inputs.project.spec_sheets
        if ref.path and ref.pages
    }


def _page_subset_for_spec(result, pdf: Path) -> list[int]:
    for ref in result.inputs.project.spec_sheets:
        if ref.path and _resolve_project_path(result, ref.path) == pdf:
            return ref.pages
    return []
