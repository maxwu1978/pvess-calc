"""K.7 — `pvess` unified root CLI.

Single entry point that groups every existing `pvess-*` CLI command
plus three workflow `pipeline` shortcuts. Keeps legacy
commands working (additive compatibility) — the root is just a
nicer surface area for new users + a place for pipeline composition.

Subcommand layout mirrors the natural customer workflow phases:

  Phase 1 — INTAKE        pvess init        new project + wizard
                          pvess survey      site-checklist PDF
                          pvess lookup      verify address lookup
                          pvess roof-review CAD roof trace package

  Phase 2 — DESIGN        pvess calc        NEC math + report.md
                          pvess customer    customer-summary PDF
                          pvess compare     scenario comparison
                          pvess serve       browser UI for web estimates

  Phase 3 — SUBMIT        pvess permit      12-page permit PDF
                          pvess dxf         EE-1 + EE-2 DXF
                          pvess labels      NEC labels PDF
                          pvess render      QET single-line diagram
                          pvess ee4-trace   EE-4 trace skeleton YAML
                          pvess ee4-preview EE-4 PDF/PNG preview
                          pvess roof-import import reviewed roof DXF

  Phase 4 — VERIFY        pvess doctor      structural self-checks
                          pvess readiness   source-data readiness report
                          pvess roof-qa     reviewed roof DXF QA
                          pvess visual-benchmark compare roof-plan visuals
                          pvess visual-iterate bounded visual benchmark loop
                          pvess web-smoke   production Web smoke check
                          pvess symbols     symbols preview

  Phase 5 — PIPELINES     pvess pipeline customer   calc + customer-summary
                          pvess pipeline submit     calc + permit + dxf + doctor
                          pvess pipeline review     same as submit + opens PDF
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from .cli import (
    calc_cmd,
    compare_cmd,
    customer_summary_cmd,
    dxf_cmd,
    ee4_preview_cmd,
    ee4_trace_cmd,
    init_cmd,
    labels_cmd,
    lookup_check_cmd,
    permit_cmd,
    readiness_cmd,
    render_cmd,
    roof_import_cmd,
    roof_qa_cmd,
    roof_review_cmd,
    roof_vis_cmd,
    site_checklist_cmd,
    symbols_preview_cmd,
    visual_benchmark_cmd,
    visual_iterate_cmd,
)
from .doctor import doctor_cmd
from .web.server import serve_cmd
from .web.smoke import smoke_cmd


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@click.group(
    name="pvess",
    help=(
        "PV + ESS permit-package toolchain.\n\n"
        "Workflow phases (run in order for a new project):\n\n"
        "  1. INTAKE   :  `pvess init`, `pvess survey`, `pvess lookup`, "
        "`pvess roof-vis`, `pvess roof-review`\n"
        "  2. DESIGN   :  `pvess calc`, `pvess customer`, `pvess compare`\n"
        "                `pvess serve` for the browser-based estimator\n"
        "  3. SUBMIT   :  `pvess permit`, `pvess dxf`, `pvess labels`, "
        "`pvess render`, `pvess ee4-trace`, `pvess ee4-preview`, "
        "`pvess roof-import`\n"
        "  4. VERIFY   :  `pvess doctor`, `pvess readiness`, "
        "`pvess roof-qa`, `pvess visual-benchmark`, "
        "`pvess visual-iterate`, `pvess symbols`\n"
        "                `pvess web-smoke` for production Web health checks\n\n"
        "Or skip the choreography and use a pipeline:\n"
        "  `pvess pipeline customer projects/<id>/`   "
        "→ calc + customer-summary in one shot\n"
        "  `pvess pipeline submit projects/<id>/`     "
        "→ full permit package + doctor check\n\n"
        "Legacy `pvess-*` commands continue to work unchanged."
    ),
)
@click.version_option(package_name="pvess-calc")
def pvess() -> None:
    """Single-entry CLI for the PV + ESS permit-package toolchain."""


# ─── Phase 1: INTAKE ─────────────────────────────────────────────────


pvess.add_command(init_cmd, name="init")
pvess.add_command(site_checklist_cmd, name="survey")
pvess.add_command(lookup_check_cmd, name="lookup")
pvess.add_command(roof_vis_cmd, name="roof-vis")
pvess.add_command(roof_review_cmd, name="roof-review")


# ─── Phase 2: DESIGN ────────────────────────────────────────────────


pvess.add_command(calc_cmd, name="calc")
pvess.add_command(customer_summary_cmd, name="customer")
pvess.add_command(compare_cmd, name="compare")
pvess.add_command(serve_cmd, name="serve")


# ─── Phase 3: SUBMIT ────────────────────────────────────────────────


pvess.add_command(permit_cmd, name="permit")
pvess.add_command(dxf_cmd, name="dxf")
pvess.add_command(labels_cmd, name="labels")
pvess.add_command(render_cmd, name="render")
pvess.add_command(ee4_trace_cmd, name="ee4-trace")
pvess.add_command(ee4_preview_cmd, name="ee4-preview")
pvess.add_command(roof_import_cmd, name="roof-import")


# ─── Phase 4: VERIFY ────────────────────────────────────────────────


pvess.add_command(doctor_cmd, name="doctor")
pvess.add_command(readiness_cmd, name="readiness")
pvess.add_command(roof_qa_cmd, name="roof-qa")
pvess.add_command(visual_benchmark_cmd, name="visual-benchmark")
pvess.add_command(visual_iterate_cmd, name="visual-iterate")
pvess.add_command(smoke_cmd, name="web-smoke")
pvess.add_command(symbols_preview_cmd, name="symbols")


# ─── Phase 5: PIPELINES ─────────────────────────────────────────────


@pvess.group(name="pipeline", help="Common multi-step workflows.")
def pipeline() -> None:
    """Pipeline shortcuts: combine 2-5 individual subcommands into one
    invocation. Each pipeline echoes the steps it ran so the user sees
    what would have been typed by hand."""


def _echo_step(num: int, total: int, label: str) -> None:
    click.echo(click.style(f"[{num}/{total}] {label}", fg="cyan", bold=True))


@pipeline.command(name="customer",
                  help="calc → customer-summary (sales-meeting one-pager).")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--address", "-a", type=str, default=None,
              help="Site address for K.3 lookup pre-fill.")
def pipeline_customer(project_dir: Path, address: str | None) -> None:
    """Two-step pipeline: NEC calculation + customer-friendly PDF.

    Use when meeting a homeowner: gives them the engineering report
    plus the marketing one-pager in one command.
    """
    total = 2
    _echo_step(1, total, f"pvess calc {project_dir}")
    ctx = click.get_current_context()
    ctx.invoke(calc_cmd, project_dir=project_dir)

    _echo_step(2, total, f"pvess customer {project_dir}")
    ctx.invoke(customer_summary_cmd, project_dir=project_dir, address=address)

    click.echo(click.style("\n✓ Customer pipeline complete.", fg="green",
                           bold=True))
    click.echo(f"  open {project_dir / 'output' / 'customer-summary.pdf'}")
    click.echo(f"  open {project_dir / 'output' / 'report.md'}")


@pipeline.command(name="submit",
                  help="calc → permit → dxf → doctor (AHJ submission bundle).")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--ahj", type=str, default=None,
              help="AHJ profile (e.g. phoenix_az, austin_tx).")
@click.option("--profile", "package_profile", type=str, default=None,
              help="Permit package profile (internal / tx_residential_pv / wyssling_like).")
def pipeline_submit(
    project_dir: Path, ahj: str | None, package_profile: str | None,
) -> None:
    """Full AHJ-submission pipeline. Runs every artifact needed for a
    real permit package + the structural doctor self-check at the end
    so you never submit a package with broken invariants.
    """
    total = 4
    ctx = click.get_current_context()

    _echo_step(1, total, f"pvess calc {project_dir}")
    ctx.invoke(calc_cmd, project_dir=project_dir)

    _echo_step(2, total, f"pvess permit {project_dir}"
                         + (f" --ahj {ahj}" if ahj else "")
                         + (f" --profile {package_profile}" if package_profile else ""))
    ctx.invoke(
        permit_cmd,
        project_dir=project_dir,
        ahj=ahj,
        package_profile=package_profile,
        readiness_appendix=False,
    )

    _echo_step(3, total, f"pvess dxf --preview {project_dir}")
    ctx.invoke(dxf_cmd, project_dir=project_dir, preview=True)

    _echo_step(4, total, f"pvess doctor {project_dir}")
    try:
        ctx.invoke(doctor_cmd, project_dir=project_dir, quiet=False)
    except SystemExit as exc:
        # doctor exits non-zero on FAIL; propagate so CI catches it.
        if exc.code:
            click.echo(click.style(
                "\n✗ Submit pipeline aborted — doctor found issues. "
                "Fix above failures before sending the package.",
                fg="red", bold=True,
            ))
            raise

    click.echo(click.style("\n✓ Submit pipeline complete — ready for AHJ.",
                           fg="green", bold=True))
    click.echo(f"  Package: "
               f"{project_dir / 'output'}/permit-package-*.pdf")


@pipeline.command(name="review",
                  help="Submit pipeline + open the permit PDF for review.")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--ahj", type=str, default=None,
              help="AHJ profile (e.g. phoenix_az).")
@click.option("--profile", "package_profile", type=str, default=None,
              help="Permit package profile (internal / tx_residential_pv / wyssling_like).")
def pipeline_review(
    project_dir: Path, ahj: str | None, package_profile: str | None,
) -> None:
    """Run the full submit pipeline then open the permit PDF in the
    default macOS PDF viewer (Preview / Acrobat / whatever is bound to
    .pdf). On other platforms, prints the file path."""
    ctx = click.get_current_context()
    ctx.invoke(
        pipeline_submit,
        project_dir=project_dir,
        ahj=ahj,
        package_profile=package_profile,
    )

    proj_id = project_dir.name
    permit_pdf = (project_dir / "output"
                  / f"permit-package-{proj_id}.pdf")
    if permit_pdf.exists() and sys.platform == "darwin":
        click.echo(click.style(
            f"\n  Opening {permit_pdf} in Preview…", fg="green",
        ))
        try:
            subprocess.run(["open", str(permit_pdf)], check=False)
        except FileNotFoundError:
            click.echo(f"  (could not invoke `open`; PDF at {permit_pdf})")
    else:
        click.echo(f"  Permit PDF: {permit_pdf}")


def main() -> None:
    """Entry-point for `pvess` console script."""
    pvess()
