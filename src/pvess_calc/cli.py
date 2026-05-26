"""Command-line entry points."""
from __future__ import annotations

import sys
from pathlib import Path

import click

from .calc.engine import run
from .compare.report import write_outputs as write_compare_outputs
from .compare.scenarios import run_scenarios
from .dxf.grounding_sheet import render_grounding_dxf
from .dxf.one_line import render_one_line_dxf
from .dxf.render import export_preview_png, render_for_result as render_dxf_for_result
from .labels.render import render_for_result as render_labels_for_result
from .qet.inject import inject_from_result
from .report.json_dump import write_json
from .report.markdown import write_markdown
from .schema import Inputs

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "library" / "templates" / "residential-ess-v1.qet"


def _load(project_dir: Path) -> Inputs:
    inputs_path = project_dir / "inputs.yaml"
    if not inputs_path.exists():
        click.echo(f"error: {inputs_path} not found", err=True)
        sys.exit(2)
    return Inputs.from_yaml(inputs_path)


@click.command(name="pvess-calc")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def calc_cmd(project_dir: Path) -> None:
    """Run NEC calculations for the project and write calculation.json + report.md."""
    inputs = _load(project_dir)
    result = run(inputs)
    output_dir = project_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(result, output_dir / "calculation.json")
    write_markdown(result, output_dir / "report.md")
    click.echo(f"wrote {output_dir / 'calculation.json'}")
    click.echo(f"wrote {output_dir / 'report.md'}")
    click.echo(
        f"interconnect: {result.interconnect.overall_status} "
        f"({result.interconnect.recommended or 'no method PASS'})"
    )


@click.command(name="pvess-render")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--template",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=TEMPLATE_PATH,
    show_default=True,
    help="QET template file (.qet) to inject into.",
)
def render_cmd(project_dir: Path, template: Path) -> None:
    """Inject calculation results into the QET template → output/system.qet."""
    inputs = _load(project_dir)
    result = run(inputs)
    output_path = project_dir / "output" / "system.qet"
    report = inject_from_result(result, template_path=template, output_path=output_path)
    click.echo(
        f"wrote {report.output_path} "
        f"({report.substitutions_applied} substitutions, "
        f"{len(report.keys_used)} unique keys used)"
    )


@click.command(name="pvess-labels")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def labels_cmd(project_dir: Path) -> None:
    """Generate the NEC label PDF (DC/AC disconnect, RSD, 705.x, 706.7, ...).

    Writes to output/labels.pdf. Print on adhesive label paper or weather-
    resistant placards per AHJ requirements."""
    inputs = _load(project_dir)
    result = run(inputs)
    output_path = project_dir / "output" / "labels.pdf"
    count = render_labels_for_result(result, output_path)
    click.echo(f"wrote {output_path} ({count} labels)")


@click.command(name="pvess-permit")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--ahj", default=None, help="AHJ profile name (Phase G).")
@click.option(
    "--profile",
    "package_profile",
    default=None,
    help="Permit package profile: internal / tx_residential_pv / wyssling_like.",
)
@click.option(
    "--readiness-appendix",
    is_flag=True,
    help=(
        "Append an INTERNAL REVIEW ONLY data-readiness appendix. "
        "Not included by default for AHJ submission packages."
    ),
)
def permit_cmd(
    project_dir: Path,
    ahj: str | None,
    package_profile: str | None,
    readiness_appendix: bool,
) -> None:
    """Generate a complete permit submittal PDF (Phase F)."""
    from .permit.builder import build_permit_package
    inputs = _load(project_dir)
    result = run(inputs, ahj_profile=ahj)
    out = project_dir / "output" / f"permit-package-{inputs.project.id}.pdf"
    n_pages = build_permit_package(
        result, out, ahj_name=ahj, package_profile=package_profile,
        include_readiness_appendix=readiness_appendix,
        project_dir=project_dir,
    )
    click.echo(f"wrote {out} ({n_pages} pages)")
    if readiness_appendix:
        click.echo(
            "included INTERNAL REVIEW ONLY readiness appendix "
            "(remove before AHJ submission unless explicitly approved)"
        )


@click.command(name="pvess-readiness")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--output", "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output Markdown path. Default: <project>/output/reference-readiness.md",
)
@click.option(
    "--checklist-output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Real-data checklist path. Default: <project>/output/real-data-checklist.md",
)
@click.option(
    "--checklist/--no-checklist",
    default=True,
    show_default=True,
    help="Also write the real-data replacement checklist.",
)
@click.option(
    "--stdout", "to_stdout",
    is_flag=True,
    help="Print the readiness report instead of writing a file.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit 1 when any field is simulated or missing.",
)
def readiness_cmd(
    project_dir: Path,
    output: Path | None,
    checklist_output: Path | None,
    checklist: bool,
    to_stdout: bool,
    strict: bool,
) -> None:
    """Generate a reference-profile data-readiness report.

    This is a source-data gate, not a renderer. It lets a team iterate with
    simulated site photos / utility data while keeping those placeholders
    visible before AHJ submission.
    """
    from .permit.readiness import (
        assess_reference_profile_readiness,
        format_real_data_checklist_markdown,
        format_reference_readiness_markdown,
    )

    inputs = _load(project_dir)
    result = run(inputs)
    readiness = assess_reference_profile_readiness(result, project_dir)
    text = format_reference_readiness_markdown(readiness)
    checklist_text = format_real_data_checklist_markdown(readiness)

    if to_stdout:
        click.echo(text, nl=False)
    else:
        out = output or project_dir / "output" / "reference-readiness.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        click.echo(f"wrote {out}")
        if checklist:
            checklist_out = (
                checklist_output
                or project_dir / "output" / "real-data-checklist.md"
            )
            checklist_out.parent.mkdir(parents=True, exist_ok=True)
            checklist_out.write_text(checklist_text, encoding="utf-8")
            click.echo(f"wrote {checklist_out}")

    status = "WARN" if readiness.needs_review else "PASS"
    click.echo(f"readiness: {status} — {readiness.doctor_detail()}")
    if strict and readiness.needs_review:
        raise SystemExit(1)


@click.command(name="pvess-compare")
@click.argument("scenarios_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def compare_cmd(scenarios_dir: Path) -> None:
    """Run every subdirectory containing inputs.yaml as a scenario and emit
    a side-by-side comparison + BOM breakdown.

    Folder layout:
      scenarios_dir/
        A/inputs.yaml
        B/inputs.yaml
        C/inputs.yaml
    """
    scenarios = run_scenarios(scenarios_dir)
    if not scenarios:
        click.echo(f"no scenarios found in {scenarios_dir}", err=True)
        sys.exit(2)
    md = scenarios_dir / "comparison.md"
    js = scenarios_dir / "comparison.json"
    write_compare_outputs(scenarios, md, js)
    click.echo(f"wrote {md} ({len(scenarios)} scenarios)")
    click.echo(f"wrote {js}")


@click.command(name="pvess-dxf")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--preview / --no-preview",
    default=False,
    help="Also emit a PNG preview alongside each DXF (matplotlib).",
)
def dxf_cmd(project_dir: Path, preview: bool) -> None:
    """Generate ACADE-friendly DXF schematics (ANSI B, 11×17"):

    \b
      • output/sheet-EE-1.dxf — three-line diagram
      • output/sheet-EE-2.dxf — grounding & bonding (NEC 250 + 690.41–50)
      • output/sheet-EE-2.1.dxf — one-line diagram when line-side tap applies
    """
    inputs = _load(project_dir)
    result = run(inputs)

    sheet1 = project_dir / "output" / "sheet-EE-1.dxf"
    sheet2 = project_dir / "output" / "sheet-EE-2.dxf"
    sheet_paths = [sheet1, sheet2]

    n_devices = render_dxf_for_result(result, sheet1)
    click.echo(f"wrote {sheet1} ({n_devices} devices)")

    render_grounding_dxf(result, sheet2)
    click.echo(f"wrote {sheet2} (grounding & bonding)")

    from .permit.builder import _should_emit_one_line
    if _should_emit_one_line(result):
        sheet21 = project_dir / "output" / "sheet-EE-2.1.dxf"
        render_one_line_dxf(result, sheet21)
        sheet_paths.append(sheet21)
        click.echo(f"wrote {sheet21} (one-line)")

    if preview:
        for path in sheet_paths:
            png_path = path.with_suffix(".png")
            export_preview_png(path, png_path)
            click.echo(f"wrote {png_path}")


@click.command(name="pvess-init")
@click.argument("project_id", type=str)
@click.option(
    "--resume", is_flag=True,
    help="Resume an interrupted wizard session for this project_id.",
)
@click.option(
    "--address", "-a", type=str, default=None,
    help=("Free-text site address (e.g. '2500 Hollow Hill Lane, "
          "Lewisville, TX 75067'). Pre-fills utility / AHJ / NEC "
          "edition / ASHRAE temps from the offline lookup tables. The "
          "wizard still asks each field — pre-fills appear as the "
          "default; press <enter> to accept."),
)
def init_cmd(project_id: str, resume: bool, address: str | None) -> None:
    """Run the interactive wizard to create a new project (Phase K.2).

    Walks every required `inputs.yaml` field with a hint + yaml_path
    tag, validates via pydantic at the end, writes the file to
    `projects/<project_id>/inputs.yaml`. Wizard state is checkpointed
    after every prompt; ctrl-C then `pvess-init --resume <id>` picks
    up where you left off.

    \b
      pvess-init 003-jones-residence
      pvess-init --resume 003-jones-residence
      pvess-init --address "Phoenix, AZ" 004-aps-residence
    """
    from .wizard.runner import run_wizard
    try:
        run_wizard(project_id, resume=resume, address=address)
    except (KeyboardInterrupt, click.exceptions.Abort):
        click.echo(click.style(
            f"\n  Wizard interrupted. Resume with: "
            f"pvess-init --resume {project_id}", fg="yellow"))
        raise SystemExit(130)


@click.command(name="pvess-customer-summary")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--address", "-a", type=str, default=None,
              help=("Optional site address to pull NREL/Mapbox/utility-rate "
                    "data for a city-specific savings estimate. Falls back "
                    "to the project's `project.location` field, then to "
                    "USA-average rates."))
def customer_summary_cmd(project_dir: Path, address: str | None) -> None:
    """Generate the customer-friendly one-pager PDF (Phase K.4).

    Reads the project's inputs.yaml, runs the NEC engine, optionally
    enriches via the K.3 lookup chain (NREL PVWatts + utility rate), and
    writes `output/customer-summary.pdf` — a homeowner-readable summary
    with system size / monthly savings / backup runtime / monthly
    production chart.

    \b
      pvess-customer-summary projects/002-phoenix-25kw/
      pvess-customer-summary -a "Phoenix, AZ" projects/002-phoenix-25kw/
    """
    from .customer.pdf import render_customer_summary
    inputs = _load(project_dir)
    result = run(inputs)

    # Try address-based lookup for richer numbers; fall back gracefully.
    lookup_fields: dict | None = None
    addr = address or inputs.project.location
    if addr:
        try:
            from .lookup import resolve
            lookup_fields = resolve(addr).fields
        except Exception as exc:
            click.echo(click.style(
                f"  (lookup for {addr!r} failed: {exc!r} — "
                "using default rates)", fg="yellow"))
            lookup_fields = None

    out = project_dir / "output" / "customer-summary.pdf"
    render_customer_summary(result, out, lookup_fields=lookup_fields)
    click.echo(f"wrote {out}")


@click.command(name="pvess-ee4-trace")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--output", "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Output YAML snippet path. Default: "
        "<project>/output/ee4-trace-skeleton.yaml"
    ),
)
@click.option(
    "--stdout", "to_stdout",
    is_flag=True,
    help="Print the YAML snippet instead of writing a file.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite the output file if it already exists.",
)
def ee4_trace_cmd(
    project_dir: Path,
    output: Path | None,
    to_stdout: bool,
    force: bool,
) -> None:
    """Generate a paste-ready `site.ee4_trace` skeleton for EE-4.

    The generated block is a first-pass vector trace scaffold derived
    from roof_sections, module placements, and known obstructions. Paste
    it into `inputs.yaml`, then adjust points against the EE-4 preview.

    \b
      pvess ee4-trace projects/003-frisco-glasshouse/
      pvess ee4-trace --stdout projects/<id>/
    """
    from .permit.ee4_trace import build_ee4_trace_skeleton, ee4_trace_yaml

    inputs = _load(project_dir)
    result = run(inputs)
    text = ee4_trace_yaml(build_ee4_trace_skeleton(result))

    if to_stdout:
        click.echo(text, nl=False)
        return

    out = output or project_dir / "output" / "ee4-trace-skeleton.yaml"
    if out.exists() and not force:
        click.echo(
            f"error: {out} already exists; pass --force to overwrite",
            err=True,
        )
        raise SystemExit(2)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    click.echo(f"wrote {out}")
    click.echo(
        "paste the `site.ee4_trace` block into inputs.yaml, then tune points"
    )


@click.command(name="pvess-ee4-preview")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--pdf-output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output PDF path. Default: <project>/output/ee4-preview.pdf",
)
@click.option(
    "--png-output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output PNG path. Default: <project>/output/ee4-preview.png",
)
@click.option(
    "--png/--no-png",
    default=True,
    show_default=True,
    help="Rasterize the PDF to a PNG preview with pdftoppm.",
)
@click.option(
    "--dpi",
    type=int,
    default=180,
    show_default=True,
    help="PNG preview resolution.",
)
@click.option(
    "--open",
    "open_preview",
    is_flag=True,
    help="Open the PNG/PDF in the default macOS viewer after writing.",
)
@click.option(
    "--lint/--no-lint",
    default=True,
    show_default=True,
    help="Run Stage 9.4 visual lint checks for the EE-4 preview.",
)
@click.option(
    "--strict-lint",
    is_flag=True,
    help="Exit non-zero when visual lint emits WARN/FAIL.",
)
def ee4_preview_cmd(
    project_dir: Path,
    pdf_output: Path | None,
    png_output: Path | None,
    png: bool,
    dpi: int,
    open_preview: bool,
    lint: bool,
    strict_lint: bool,
) -> None:
    """Render a fast EE-4-only preview PDF/PNG for trace review."""
    import subprocess

    from .doctor import _check_ee4_trace_ready_for_review
    from .permit.ee4_lint import lint_ee4_preview
    from .permit.ee4_review import render_ee4_review

    inputs = _load(project_dir)
    result = run(inputs)
    output_dir = project_dir / "output"
    pdf_path = pdf_output or output_dir / "ee4-preview.pdf"
    png_path = png_output or output_dir / "ee4-preview.png"

    [trace_check] = _check_ee4_trace_ready_for_review(result)
    click.echo(
        f"trace-check: {trace_check.status}"
        + (f" — {trace_check.detail}" if trace_check.detail else "")
    )
    lint_has_warning = False
    if lint:
        lint_results = lint_ee4_preview(result)
        lint_issues = [r for r in lint_results if r.status != "PASS"]
        lint_has_warning = bool(lint_issues)
        if lint_issues:
            for item in lint_issues:
                click.echo(
                    f"visual-lint: {item.status} {item.name}"
                    + (f" — {item.detail}" if item.detail else "")
                )
        else:
            click.echo(f"visual-lint: PASS ({len(lint_results)} checks)")

    try:
        artifacts = render_ee4_review(
            result,
            pdf_path,
            png_path=png_path if png else None,
            dpi=dpi,
        )
    except RuntimeError as exc:
        click.echo(click.style(f"warning: {exc}", fg="yellow"), err=True)
        artifacts = render_ee4_review(result, pdf_path, png_path=None, dpi=dpi)

    click.echo(f"wrote {artifacts.pdf_path}")
    if artifacts.png_path is not None:
        click.echo(f"wrote {artifacts.png_path}")

    if open_preview:
        target = artifacts.png_path or artifacts.pdf_path
        if sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            click.echo(f"preview: {target}")

    if strict_lint and lint_has_warning:
        raise SystemExit(1)


@click.command(name="pvess-roof-review")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--address", "-a",
    type=str,
    default=None,
    help="Optional address for lookup-based roof face candidates.",
)
@click.option(
    "--satellite/--no-satellite",
    default=False,
    show_default=True,
    help=(
        "Fetch Google Solar dataLayers / Google Static imagery when needed. "
        "This can incur Google API charges."
    ),
)
@click.option(
    "--confirm-cost",
    is_flag=True,
    help="Acknowledge paid imagery calls for --satellite mode.",
)
def roof_review_cmd(
    project_dir: Path,
    address: str | None,
    satellite: bool,
    confirm_cost: bool,
) -> None:
    """Generate the CAD roof-review package for a project.

    The command never mutates inputs.yaml. It writes a review DXF,
    underlay PNG, roof-mask candidate JSON, and audit Markdown under
    output/roof-review. If API keys or cached satellite layers are absent,
    it still emits a blank CAD template with the layer standard.
    """
    import os
    from .roof_review import build_roof_review_package

    if satellite:
        env_allow = os.environ.get("PVESS_ALLOW_PAID_RENDERS", "").strip()
        env_confirmed = env_allow in ("1", "true", "yes")
        if not confirm_cost and not env_confirmed:
            click.echo(click.style(
                "warning: --satellite may call paid Google imagery APIs.",
                fg="yellow",
            ), err=True)
            click.echo(
                "Pass --confirm-cost or set PVESS_ALLOW_PAID_RENDERS=1 "
                "to proceed.",
                err=True,
            )
            raise SystemExit(4)

    artifacts = build_roof_review_package(
        project_dir,
        address=address,
        allow_paid_satellite=satellite,
    )
    for key in (
        "review_dxf",
        "review_preview",
        "underlay",
        "candidate_json",
        "line_candidates_json",
        "design_guidance_json",
        "audit_markdown",
    ):
        click.echo(f"wrote {artifacts[key]}")
    click.echo(
        "CAD review: draw/edit ROOF_OUTLINE and ROOF_FACET, save as "
        "roof-reviewed.dxf, then run `pvess roof-import`."
    )


@click.command(name="pvess-roof-import")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("reviewed_dxf",
                type=click.Path(exists=True, dir_okay=False, path_type=Path))
def roof_import_cmd(project_dir: Path, reviewed_dxf: Path) -> None:
    """Import a CAD-reviewed roof DXF into paste-ready roof YAML."""
    from .roof_review import write_import_outputs
    from .roof_review.qa import RoofReviewImportError

    inputs = _load(project_dir)
    try:
        artifacts = write_import_outputs(
            reviewed_dxf,
            project_dir / "output" / "roof-review",
            original_inputs_path=project_dir / "inputs.yaml",
            default_pitch_deg=inputs.site.roof_pitch_deg,
            default_azimuth_deg=inputs.site.array_azimuth_deg,
        )
    except RoofReviewImportError as exc:
        from .roof_review.qa import write_qa_report
        report = write_qa_report(
            exc.qa,
            project_dir / "output" / "roof-review" / "roof-qa-report.md",
            dxf_path=reviewed_dxf,
        )
        for line in exc.qa.as_lines():
            click.echo(line, err=True)
        click.echo(f"wrote {report}", err=True)
        raise SystemExit(2)

    click.echo(f"wrote {artifacts['yaml']}")
    click.echo(f"wrote {artifacts['preview']}")
    click.echo(f"wrote {artifacts['qa_report']}")
    click.echo(f"wrote {artifacts['merge_preview']}")
    click.echo(f"wrote {artifacts['merged_inputs']}")
    click.echo(f"wrote {artifacts['validation']}")
    click.echo(
        "Review inputs.roof-merged.yaml. The original inputs.yaml was not modified."
    )


@click.command(name="pvess-roof-qa")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("reviewed_dxf",
                type=click.Path(exists=True, dir_okay=False, path_type=Path))
def roof_qa_cmd(project_dir: Path, reviewed_dxf: Path) -> None:
    """Run CAD roof-review DXF QA without writing import artifacts."""
    from .roof_review import qa_reviewed_dxf
    from .roof_review.qa import write_qa_report

    _load(project_dir)  # keep the command scoped to a real project
    qa = qa_reviewed_dxf(reviewed_dxf)
    report = write_qa_report(
        qa,
        project_dir / "output" / "roof-review" / "roof-qa-report.md",
        dxf_path=reviewed_dxf,
    )
    for line in qa.as_lines():
        click.echo(line)
    click.echo(f"wrote {report}")
    if qa.failures:
        raise SystemExit(2)


@click.command(name="pvess-visual-benchmark")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--target", required=True,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Formal reference roof-plan PNG to compare against.")
@click.option("--sheet",
              type=click.Choice(["PV-2", "PV-4", "EE-1"],
                                case_sensitive=False),
              default=None,
              help="Limit comparison to one sheet.")
def visual_benchmark_cmd(
    project_dir: Path,
    target: Path,
    sheet: str | None,
) -> None:
    """Benchmark current roof/PV sheet visuals against a reference image."""
    from .permit.visual_benchmark import run_visual_benchmark

    try:
        result = run_visual_benchmark(project_dir, target, sheet=sheet)
    except ValueError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(2)
    paths = result["paths"]
    metrics = result["metrics"]
    click.echo(f"wrote {paths.permit_pdf}")
    click.echo(f"wrote {paths.metrics_json}")
    click.echo(f"wrote {paths.comparison_md}")
    click.echo(
        f"overall_score={metrics['overall_score']:.1f} "
        f"qa_constraints_pass={metrics['qa_constraints_pass']}"
    )


@click.command(name="pvess-visual-iterate")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--target", required=True,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Formal reference roof-plan PNG to compare against.")
@click.option("--max-rounds", default=3, show_default=True,
              type=click.IntRange(1, 10),
              help="Maximum benchmark rounds to run.")
def visual_iterate_cmd(
    project_dir: Path,
    target: Path,
    max_rounds: int,
) -> None:
    """Run bounded visual benchmark iterations and write round artifacts."""
    from .permit.visual_benchmark import run_visual_iteration

    summary = run_visual_iteration(
        project_dir,
        target,
        max_rounds=max_rounds,
    )
    click.echo(f"status={summary['status']}")
    click.echo(f"wrote {summary['final_summary']}")
    if summary["status"] != "PASS":
        for action in summary.get("next_actions", []):
            click.echo(f"- {action}")


@click.command(name="pvess-lookup-check")
@click.argument("address", nargs=-1, required=False)
def lookup_check_cmd(address: tuple[str, ...]) -> None:
    """Verify lookup-service configuration & connectivity (Phase K.3).

    Prints **fingerprints** (NOT full values) of any API keys found,
    runs the K.3a offline chain, and — if keys are configured — exercises
    the online providers against the given address. Default address is
    'Phoenix, AZ' for a quick smoke test.

    Use this after creating `.env` to confirm the file is being picked
    up before running the real wizard:

    \b
      pvess-lookup-check
      pvess-lookup-check "2500 Hollow Hill Lane, Lewisville TX"
    """
    from .lookup import resolve
    from .lookup.config import (
        ENV_GOOGLE_SOLAR_KEY, ENV_MAPBOX_TOKEN, ENV_NREL_API_KEY,
        get_google_solar_key, get_mapbox_token, get_nrel_api_key,
        token_fingerprint,
        _find_dotenv,
    )

    # 1. Show where credentials came from.
    dotenv = _find_dotenv()
    click.echo(click.style("Configuration", bold=True))
    if dotenv:
        click.echo(f"  .env file:           {dotenv}")
    else:
        click.echo("  .env file:           (none found in CWD upward)")
    mbox = get_mapbox_token()
    nrel = get_nrel_api_key()
    gsolar = get_google_solar_key()
    click.echo(f"  {ENV_MAPBOX_TOKEN}:     "
               + click.style(token_fingerprint(mbox),
                             fg="green" if mbox else "yellow"))
    click.echo(f"  {ENV_NREL_API_KEY}:      "
               + click.style(token_fingerprint(nrel),
                             fg="green" if nrel else "yellow"))
    click.echo(f"  {ENV_GOOGLE_SOLAR_KEY}:  "
               + click.style(token_fingerprint(gsolar),
                             fg="green" if gsolar else "yellow"))

    if mbox and mbox.startswith("sk."):
        click.echo(click.style(
            "  ⚠ Mapbox token is SECRET (sk.*). Rotate to a public (pk.*) "
            "token with URL whitelist for safer use.", fg="yellow"))

    # 2. Run a resolve() on the address and print field provenance.
    addr_str = " ".join(address) if address else "Phoenix, AZ"
    click.echo()
    click.echo(click.style(f"Resolving: {addr_str!r}", bold=True))
    result = resolve(addr_str, use_cache=False)

    if not result.fields:
        click.echo(click.style(
            "  ✗ no fields returned — address may not be in offline tables",
            fg="red"))
        raise SystemExit(2)

    offline_count = 0
    online_count = 0
    for k, v in result.fields.items():
        src = result.field_sources[k]
        conf = result.field_confidence[k]
        is_online = src.startswith(("mapbox", "nrel", "google"))
        if is_online:
            online_count += 1
        else:
            offline_count += 1
        marker = "🛰 " if is_online else "  "
        # Truncate long values for terminal hygiene.
        v_str = str(v)
        if len(v_str) > 60:
            v_str = v_str[:57] + "..."
        click.echo(
            f"  {marker}{k:34} = {v_str:30}  [{src}, {conf}]"
        )

    # 3. Summary + verdict.
    click.echo()
    click.echo(click.style(
        f"Summary: {offline_count} offline + {online_count} online "
        f"= {len(result.fields)} fields", bold=True))
    if mbox and online_count == 0:
        click.echo(click.style(
            "  ⚠ Mapbox token configured but no online fields returned — "
            "check network or token scope.", fg="yellow"))
        raise SystemExit(1)
    if not mbox and not nrel and not gsolar:
        click.echo("  (Set PVESS_MAPBOX_TOKEN / PVESS_NREL_API_KEY / "
                   "PVESS_GOOGLE_SOLAR_KEY to enable online enrichment.)")
    # K.3c hint: only emitted when Google Solar key is missing AND
    # other online providers already work — otherwise the message
    # competes with the broader "no keys set" hint.
    elif (mbox or nrel) and not gsolar:
        click.echo("  (Set PVESS_GOOGLE_SOLAR_KEY to auto-populate "
                   "per-face roof_sections from Google Solar API.)")


@click.command(name="pvess-site-checklist")
@click.option(
    "--output", "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("site-survey-checklist.pdf"),
    show_default=True,
    help="Output PDF path.",
)
def site_checklist_cmd(output: Path) -> None:
    """Generate the site-survey checklist PDF (Phase K.1).

    A field-technician form covering every on-site measurement the
    design engine needs (MSP / busbar / roof faces / wire lengths /
    climate). Field list lives in
    `src/pvess_calc/site_checklist/field_specs.py`.

    \b
      pvess-site-checklist                         # → site-survey-checklist.pdf
      pvess-site-checklist -o /tmp/survey.pdf      # custom path
    """
    from .site_checklist.builder import render_checklist
    render_checklist(output)
    click.echo(f"wrote {output}")


@click.command(name="pvess-symbols-preview")
@click.option(
    "--output", "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("symbols-swatch.pdf"),
    show_default=True,
    help="Output PDF path.",
)
@click.option(
    "--dxf-only",
    is_flag=True,
    help="Emit only the DXF (skip PDF conversion). Useful for CI / fast loops.",
)
def symbols_preview_cmd(output: Path, dxf_only: bool) -> None:
    """Render a one-page swatch of all icon glyphs (DEV TOOL).

    Use this to iterate on `dxf/symbols.py` without running the full
    permit pipeline. Each icon is rendered at its production size,
    same dispatch path the EE-1 sheet uses.

    \b
      pvess-symbols-preview                          # → symbols-swatch.pdf
      pvess-symbols-preview -o /tmp/swatch.pdf       # custom path
      pvess-symbols-preview --dxf-only -o swatch.dxf # skip matplotlib pass
    """
    from tempfile import TemporaryDirectory
    from .dxf.symbols_preview import render_swatch

    if dxf_only:
        render_swatch(output)
        click.echo(f"wrote {output}")
        return

    # DXF → PDF via the same matplotlib backend as the permit pipeline.
    from .permit.builder import _dxf_to_pdf
    with TemporaryDirectory() as tmp:
        dxf_path = Path(tmp) / "swatch.dxf"
        render_swatch(dxf_path)
        _dxf_to_pdf(dxf_path, output)
    click.echo(f"wrote {output}")


# ─── K.3c sidekick: address → rooftop visualization ──────────────────


@click.command(name="pvess-roof-vis")
@click.argument("address", nargs=-1, required=True)
@click.option(
    "--output", "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output PNG path. Default: <slugified-address>-roof-diagram.png",
)
@click.option(
    "--density",
    type=click.Choice(["rural", "suburban", "urban", "unknown"]),
    default="unknown",
    show_default=True,
    help="Site density — drives default shading factor when a face's "
         "shading_factor stays at 1.0 (the 'I didn't measure' default).",
)
@click.option(
    "--dpi", type=int, default=150, show_default=True,
    help="Output resolution. 150 dpi → ~2100×1200 px (Letter-friendly).",
)
@click.option(
    "--satellite/--no-satellite",
    default=False,
    show_default=True,
    help="Include real aerial imagery + annual-flux heatmap via Google "
         "Solar dataLayers (~$0.50 / render). Recommended for SIGNED "
         "customers only; the free analytical view is plenty for "
         "prospects.",
)
@click.option(
    "--confirm-cost", is_flag=True,
    help="Skip the interactive 'this will cost $0.50, continue?' prompt "
         "for --satellite renders. Use in non-interactive contexts "
         "(scripts, batch). Also honours PVESS_ALLOW_PAID_RENDERS=1.",
)
def roof_vis_cmd(
    address: tuple[str, ...], output: Path | None,
    density: str, dpi: int, satellite: bool, confirm_cost: bool,
) -> None:
    """Generate a rooftop visualization PNG straight from an address.

    Runs the K.3 / K.3c lookup chain (Mapbox + NREL + Google Solar) and
    renders a 2-panel analytical diagram (compass rose + ranked bars) by
    default. Pass `--satellite` to additionally overlay real aerial
    imagery + an annual-flux heatmap — paid Google Solar dataLayers
    feature, ~$0.50 per render.

    \b
    PROSPECT-tier (no deposit) — free analytical view:
      pvess roof-vis "7652 Glasshouse Walk, Frisco TX 75035"

    \b
    SIGNED-customer-tier (deposit paid) — full satellite + flux:
      pvess roof-vis "7652 Glasshouse Walk, Frisco TX 75035" \\
                     --satellite --confirm-cost

    Requires `PVESS_GOOGLE_SOLAR_KEY` (see `.env.example`). Without the
    key, exits 2. Satellite renders without confirmation prompt exit 4.
    """
    import os
    from .lookup.config import get_google_solar_key

    if not get_google_solar_key():
        click.echo(click.style(
            "✗ PVESS_GOOGLE_SOLAR_KEY not set — this command needs Google "
            "Solar API access.", fg="red"))
        click.echo(
            "  Enable at https://console.cloud.google.com/apis/library/"
            "solar.googleapis.com and add to .env (see .env.example).")
        raise SystemExit(2)

    addr_str = " ".join(address).strip()
    if output is None:
        slug = "".join(
            c if c.isalnum() else "-" for c in addr_str.lower()
        ).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        slug = slug[:60] or "roof"
        suffix = "-roof-satellite" if satellite else "-roof-diagram"
        output = Path(f"{slug}{suffix}.png")

    # ── Paid-render gate ────────────────────────────────────────────
    if satellite:
        env_allow = os.environ.get("PVESS_ALLOW_PAID_RENDERS", "").strip()
        env_confirmed = env_allow in ("1", "true", "yes")
        if not confirm_cost and not env_confirmed:
            click.echo(click.style(
                "⚠ --satellite uses Google Solar dataLayers (~$0.50/render).",
                fg="yellow", bold=True))
            click.echo("  For PROSPECT-tier leads (no deposit), drop "
                       "--satellite and use the free analytical view.")
            click.echo("  Pass --confirm-cost (one-shot) or set "
                       "PVESS_ALLOW_PAID_RENDERS=1 (session) to acknowledge "
                       "and proceed.")
            raise SystemExit(4)

    click.echo(click.style(f"Resolving: {addr_str!r}", bold=True))

    if satellite:
        from .customer.roof_satellite import render_from_address as render_sat
        from .lookup.providers.google_solar_data_layers import DataLayersError
        try:
            written = render_sat(addr_str, output,
                                 urban_density=density, dpi=dpi)
        except DataLayersError as exc:
            click.echo(click.style(
                f"✗ Satellite render failed: {exc}", fg="red"))
            click.echo("  (Charge may still have been recorded; check "
                       "Google Cloud billing if you see this often.)")
            raise SystemExit(5)
    else:
        from .customer.roof_diagram import render_from_address as render_an
        written = render_an(addr_str, output,
                            urban_density=density)

    if written is None:
        click.echo(click.style(
            "✗ Google Solar returned no roof_sections for this address.",
            fg="red"))
        click.echo(
            "  Possible causes: address geocoded outside Solar API "
            "coverage (rural / new construction); a multi-family / "
            "commercial building closer to the lat/lng than the target. "
            "Consider EagleView fallback.")
        raise SystemExit(3)

    mode = "satellite + analysis" if satellite else "analysis"
    click.echo(click.style(
        f"✓ wrote {written}   ({output.stat().st_size:,} B, "
        f"{mode}, {dpi} dpi)", fg="green"))
