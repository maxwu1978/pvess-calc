"""Assemble the complete permit submittal PDF.

Pipeline:
1. Generate DXF sheets EE-1 (three-line) and EE-2 (grounding) → convert to PDF.
2. Generate native PDF sheets EE-0 (cover), EE-3 (panels), EE-4 (site), EE-5 (checklist).
3. Re-use existing labels.pdf as EE-6.
4. Merge all into a single multi-page PDF in the project's output/ directory.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader, PdfWriter

from ..calc.engine import CalculationResult
from ..dxf.grounding_sheet import render_grounding_dxf
from ..dxf.render import render_dxf
from ..labels.render import render_for_result as render_labels
from .compliance import render_compliance_checklist
from .cover_sheet import render_cover_sheet
from .general_notes import render_general_notes
from .panel_schedule import render_panel_schedule
from .site_plan import render_site_plan
from .structural import (
    render_attachment_plan,
    render_mounting_details,
    render_string_plan,
)


def _collect_cut_sheets(result) -> list[Path]:
    """Walk a project's cut_sheets/ directory and return every PDF found.

    Convention: place manufacturer datasheets in
      projects/<id>/cut_sheets/*.pdf
    and they'll be appended in alphabetical order at the back of the permit
    package. Common order:
      01-module.pdf · 02-inverter.pdf · 03-optimizer.pdf · 04-battery.pdf · ...
    """
    project_id = result.inputs.project.id
    candidates = [
        Path.cwd() / "projects" / project_id / "cut_sheets",
    ]
    out: list[Path] = []
    for d in candidates:
        if d.exists() and d.is_dir():
            out.extend(sorted(d.glob("*.pdf")))
    return out


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
) -> int:
    """Build the full permit PDF. Returns the number of pages."""
    # Phase G hook: if an AHJ name is provided, filter sheets accordingly.
    # For now we always emit every sheet; AHJ profiles will refine later.
    from ..ahj.profile import get_ahj_profile

    profile = get_ahj_profile(ahj_name) if ahj_name else None
    required_sheets = (
        profile.required_sheets if profile
        else [
            "cover", "ee-1", "ee-2", "ee-3", "ee-4", "ee-5",
            "pv-4", "pv-5", "pv-6",   # attachment / mounting / string plan
            "notes", "labels",
        ]
    )

    with TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        pdfs: list[Path] = []

        # EE-0 cover
        if "cover" in required_sheets:
            p = tmp_dir / "ee-0-cover.pdf"
            render_cover_sheet(result, p)
            pdfs.append(p)

        # EE-1 three-line (DXF → PDF)
        if "ee-1" in required_sheets:
            dxf = tmp_dir / "sheet-EE-1.dxf"
            render_dxf(result, dxf)
            p = tmp_dir / "ee-1.pdf"
            _dxf_to_pdf(dxf, p)
            pdfs.append(p)

        # EE-2 grounding (DXF → PDF)
        if "ee-2" in required_sheets:
            dxf = tmp_dir / "sheet-EE-2.dxf"
            render_grounding_dxf(result, dxf)
            p = tmp_dir / "ee-2.pdf"
            _dxf_to_pdf(dxf, p)
            pdfs.append(p)

        # EE-3 panel schedules
        if "ee-3" in required_sheets:
            p = tmp_dir / "ee-3-panels.pdf"
            render_panel_schedule(result, p)
            pdfs.append(p)

        # EE-4 site plan
        if "ee-4" in required_sheets:
            p = tmp_dir / "ee-4-site.pdf"
            render_site_plan(result, p)
            pdfs.append(p)

        # PV-4 attachment plan
        if "pv-4" in required_sheets:
            p = tmp_dir / "pv-4-attachment.pdf"
            render_attachment_plan(result, p)
            pdfs.append(p)

        # PV-5 mounting details
        if "pv-5" in required_sheets:
            p = tmp_dir / "pv-5-mounting.pdf"
            render_mounting_details(result, p)
            pdfs.append(p)

        # PV-6 string layout plan
        if "pv-6" in required_sheets:
            p = tmp_dir / "pv-6-strings.pdf"
            render_string_plan(result, p)
            pdfs.append(p)

        # EE-5 NEC compliance checklist
        if "ee-5" in required_sheets:
            p = tmp_dir / "ee-5-compliance.pdf"
            render_compliance_checklist(result, p)
            pdfs.append(p)

        # PV-N general + electrical notes
        if "notes" in required_sheets:
            p = tmp_dir / "pv-n-notes.pdf"
            render_general_notes(result, p)
            pdfs.append(p)

        # EE-6 labels
        if "labels" in required_sheets:
            p = tmp_dir / "ee-6-labels.pdf"
            render_labels(result, p)
            pdfs.append(p)

        # Cut sheets — append any datasheet PDFs the project ships
        cut_sheets = _collect_cut_sheets(result)
        pdfs.extend(cut_sheets)

        # Combine all PDFs into one
        writer = PdfWriter()
        page_count = 0
        for pdf in pdfs:
            reader = PdfReader(str(pdf))
            for page in reader.pages:
                writer.add_page(page)
                page_count += 1

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            writer.write(f)

        return page_count
