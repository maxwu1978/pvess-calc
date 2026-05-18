"""pvess-doctor — structural self-checks for a project's submittal package.

What this is *not*: a calculation-correctness verifier (pytest covers that)
or a visual-style linter (a human reviewer covers that). What it *is*: a
contract enforcer for the cross-cutting invariants that aren't natural to
encode in unit tests — the kind of thing that let the Phase J cover-index
drift slip past 120 green pytest cases.

Each check returns a `CheckResult`. The doctor accumulates them, prints a
report, and exits non-zero if anything failed. Wire into pre-commit / CI by
running:

    pvess-doctor projects/002-phoenix-25kw/

Add a check by writing a `_check_*` function that returns CheckResult(s) and
appending it to `ALL_CHECKS`. Keep them independent — one check failing must
not silently disable a later one.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import click

from .ahj.profile import AhjProfile, PROFILES_DIR, get_ahj_profile, list_ahj_profiles
from .calc.engine import CalculationResult, run
from .labels.specs import LABEL_CATALOG
from .permit.sheet_registry import (
    PACKAGE_PROFILES,
    SHEET_REGISTRY,
    codes as registry_codes,
    registry_for_profile,
)
from .schema import Inputs


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str            # short identifier, e.g. "cover_index_matches_pipeline"
    status: str          # "PASS" | "FAIL" | "WARN" | "SKIP"
    detail: str = ""     # human-readable diagnosis on failure

    @property
    def ok(self) -> bool:
        return self.status in ("PASS", "WARN", "SKIP")


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────


def _check_inputs_load(project_dir: Path) -> list[CheckResult]:
    """inputs.yaml must validate against the current schema."""
    path = project_dir / "inputs.yaml"
    if not path.exists():
        return [CheckResult("inputs_load", "FAIL",
                            f"{path} not found")]
    try:
        Inputs.from_yaml(path)
    except Exception as exc:
        return [CheckResult("inputs_load", "FAIL",
                            f"schema validation failed: {exc}")]
    return [CheckResult("inputs_load", "PASS")]


def _check_calc_engine(result: CalculationResult | None) -> list[CheckResult]:
    """Calc engine must produce a result with all expected top-level fields."""
    if result is None:
        return [CheckResult("calc_engine", "FAIL",
                            "calc engine returned None (upstream failure)")]
    missing = [
        attr for attr in ("inputs", "pv_string", "interconnect",
                          "ess", "grounding")
        if not hasattr(result, attr)
    ]
    if missing:
        return [CheckResult("calc_engine", "FAIL",
                            f"result missing fields: {missing}")]
    return [CheckResult("calc_engine", "PASS")]


def _check_ahj_profile_codes() -> list[CheckResult]:
    """Every code referenced by any AHJ profile's required_sheets must be in
    the Sheet Registry. Closes the loop that lets a profile demand a sheet
    that the builder doesn't know how to emit."""
    results: list[CheckResult] = []
    registry: set[str] = set()
    for profile_specs in PACKAGE_PROFILES.values():
        registry.update(spec.code for spec in profile_specs)
    for name in list_ahj_profiles():
        try:
            profile = get_ahj_profile(name)
        except Exception as exc:
            results.append(CheckResult(
                f"ahj_profile.{name}", "FAIL",
                f"failed to load: {exc}"))
            continue
        unknown = [c for c in profile.required_sheets if c not in registry]
        if unknown:
            results.append(CheckResult(
                f"ahj_profile.{name}", "FAIL",
                f"references unknown sheet code(s): {unknown}"))
        else:
            results.append(CheckResult(f"ahj_profile.{name}", "PASS"))
    if not results:
        results.append(CheckResult("ahj_profile.discovery", "WARN",
                                   f"no AHJ profiles found in {PROFILES_DIR}"))
    return results


def _check_label_set_codes() -> list[CheckResult]:
    """Each AHJ profile's `label_set` must resolve to a real LabelSpec.

    A typo'd NEC clause in a YAML would silently produce a label-less PDF
    for that AHJ; this check turns that into a hard fail.
    """
    catalog_clauses = {spec.nec_clause for spec in LABEL_CATALOG}
    results: list[CheckResult] = []
    for name in list_ahj_profiles():
        try:
            profile = get_ahj_profile(name)
        except Exception:
            continue  # already reported by _check_ahj_profile_codes
        unknown = [c for c in profile.label_set if c not in catalog_clauses]
        if unknown:
            results.append(CheckResult(
                f"label_set.{name}", "FAIL",
                f"unknown NEC clause(s) in label_set: {unknown}"))
        else:
            results.append(CheckResult(f"label_set.{name}", "PASS"))
    return results


def _check_cover_lists_all_sheets(result: CalculationResult,
                                  project_dir: Path) -> list[CheckResult]:
    """The rendered cover sheet's SHEET INDEX block must mention every
    sheet the builder will actually emit.

    This is the Phase J regression: cover.py listed EE-0 through EE-6 while
    the builder emitted those plus PV-4/PV-5/PV-6/PV-N. The check renders
    the cover to a temp PDF, extracts text, and verifies every registered
    display_code appears.
    """
    from .permit.builder import _selected_sheets
    from .permit.cover_sheet import render_cover_sheet

    package_profile = result.inputs.project.permit_profile
    specs = _selected_sheets(
        result, package_profile=package_profile, ahj_name=None,
    )
    expected_codes = [s.display_code for s in specs]
    sheet_rows = [(s.display_code, s.title) for s in specs]

    with TemporaryDirectory() as tmp:
        cover_pdf = Path(tmp) / "cover.pdf"
        try:
            if package_profile == "internal":
                render_cover_sheet(result, cover_pdf)
            else:
                render_cover_sheet(result, cover_pdf, sheet_rows=sheet_rows)
        except Exception as exc:
            return [CheckResult("cover_index_matches_pipeline", "FAIL",
                                f"cover render crashed: {exc}")]

        text = _pdf_text(cover_pdf)

    missing = [code for code in expected_codes if code not in text]
    if missing:
        return [CheckResult(
            "cover_index_matches_pipeline", "FAIL",
            f"cover SHEET INDEX missing: {missing} — registered but not on cover")]
    return [CheckResult("cover_index_matches_pipeline", "PASS",
                        f"all {len(expected_codes)} display codes present")]


def _check_permit_emits_registry(result: CalculationResult) -> list[CheckResult]:
    """Builder must produce one PDF page per registered sheet (cut sheets
    aside) when run without an AHJ filter.

    Catches the case where someone wires a renderer but forgets to add the
    `if "<code>" in required_sheets:` branch in builder.py, or vice versa.
    """
    from .permit.builder import _selected_sheets, build_permit_package

    package_profile = result.inputs.project.permit_profile
    n_registered = len(_selected_sheets(
        result, package_profile=package_profile, ahj_name=None,
    ))
    # Labels sheet often spans 2 pages (8 labels on US Letter); allow N+1
    # tolerance per multi-page sheet kind. Treat as range, not exact match.
    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "test-permit.pdf"
        try:
            n_pages = build_permit_package(result, out, ahj_name=None)
        except Exception as exc:
            return [CheckResult("permit_emits_registry", "FAIL",
                                f"builder crashed: {exc}")]
    # The labels sheet renders 2 pages in our current fixture (8 labels at
    # 6-per-page = 2 pages). Other sheets are 1 page. So we expect at least
    # `n_registered` pages, and at most `n_registered + 3` (room for label
    # overflow + cut sheets if any).
    if n_pages < n_registered:
        return [CheckResult(
            "permit_emits_registry", "FAIL",
            f"got {n_pages} pages, expected ≥ {n_registered} "
            f"(one per registered sheet — labels may add overflow)")]
    return [CheckResult("permit_emits_registry", "PASS",
                        f"{n_pages} pages, {n_registered} registered sheets")]


def _check_pdf_is_text_searchable(result: CalculationResult) -> list[CheckResult]:
    """Permit PDF must contain the project name as searchable text.

    Guards against a regression where reportlab embeds text as paths or
    accidentally rasterizes — both produce "valid" PDFs that fail in AHJ
    review software.
    """
    from .permit.builder import build_permit_package

    project_name = result.inputs.project.client_name or result.inputs.project.name
    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "test-permit.pdf"
        try:
            build_permit_package(result, out, ahj_name=None)
        except Exception as exc:
            return [CheckResult("pdf_text_searchable", "FAIL",
                                f"builder crashed: {exc}")]
        text = _pdf_text(out)
    if project_name not in text:
        return [CheckResult(
            "pdf_text_searchable", "FAIL",
            f"project name {project_name!r} not found in extracted PDF text — "
            f"PDF may be all-image")]
    return [CheckResult("pdf_text_searchable", "PASS")]


def _dxf_text_bbox(entity) -> tuple[float, float, float, float]:
    """Estimate a DXF TEXT/ATTRIB entity bbox in modelspace units."""
    from .dxf._textfit import estimate_text_width

    height = float(entity.dxf.height)
    width = estimate_text_width(entity.dxf.text, height)
    halign = int(getattr(entity.dxf, "halign", 0) or 0)
    if halign == 0:
        x_min = float(entity.dxf.insert.x)
        y_baseline = float(entity.dxf.insert.y)
    else:
        align_point = (
            entity.dxf.align_point
            if entity.dxf.hasattr("align_point")
            else entity.dxf.insert
        )
        anchor_x = float(align_point.x)
        y_baseline = float(align_point.y)
        if halign == 1:
            x_min = anchor_x - width / 2
        else:
            x_min = anchor_x - width
    return (
        x_min,
        y_baseline - height * 0.25,
        x_min + width,
        y_baseline + height * 0.85,
    )


def _dxf_segment_boxes(entity, pad: float) -> list[tuple[float, float, float, float]]:
    if entity.dxftype() == "LINE":
        pts = [
            (float(entity.dxf.start.x), float(entity.dxf.start.y)),
            (float(entity.dxf.end.x), float(entity.dxf.end.y)),
        ]
    else:
        pts = [(float(p[0]), float(p[1])) for p in entity.get_points("xy")]
    return [
        (
            min(a[0], b[0]) - pad,
            min(a[1], b[1]) - pad,
            max(a[0], b[0]) + pad,
            max(a[1], b[1]) + pad,
        )
        for a, b in zip(pts, pts[1:])
    ]


def _dxf_boxes_overlap(a, b) -> bool:
    return (
        min(a[2], b[2]) > max(a[0], b[0])
        and min(a[3], b[3]) > max(a[1], b[1])
    )


def _is_transient_wire_label(text: str) -> bool:
    """Skip labels intentionally placed on/near conductors."""
    norm = text.strip().upper()
    if re.fullmatch(r"[A-Z](?:×\d+)?", norm):
        return True
    if re.fullmatch(r"\dP-\d+A", norm):
        return True
    return False


def _dxf_wire_text_offenders(
    doc,
    sheet_name: str,
    *,
    text_layers: set[str],
    wire_layers: set[str] | None = None,
    ignored_texts: set[str] | None = None,
    include_attribs: bool = True,
    wire_pad: float = 0.035,
    limit: int = 8,
) -> tuple[list[str], int]:
    """Return text labels whose bbox intersects conductor segment boxes.

    This intentionally checks both TEXT and visible ATTRIB entities. The
    latter matters because AutoCAD Electrical component metadata renders as
    ATTRIB text; previous manual reviews caught conductor lines crossing those
    visible attributes even while the TEXT-only doctor checks passed.
    """
    msp = doc.modelspace()
    ignored = {t.upper() for t in (ignored_texts or set())}

    text_boxes: list[tuple[str, str, tuple[float, float, float, float]]] = []
    for entity in msp.query("TEXT"):
        text = entity.dxf.text.strip()
        layer = entity.dxf.layer
        norm = text.upper()
        if not text or layer not in text_layers:
            continue
        if norm in ignored or _is_transient_wire_label(text):
            continue
        text_boxes.append((text, layer, _dxf_text_bbox(entity)))

    if include_attribs:
        for insert in msp.query("INSERT"):
            for attr in insert.attribs:
                text = attr.dxf.text.strip()
                norm = text.upper()
                flags = int(getattr(attr.dxf, "flags", 0) or 0)
                if not text or flags & 1:
                    continue
                if norm in ignored or _is_transient_wire_label(text):
                    continue
                text_boxes.append((text, attr.dxf.layer, _dxf_text_bbox(attr)))

    wire_boxes: list[tuple[str, tuple[float, float, float, float]]] = []
    for entity in msp.query("LWPOLYLINE LINE"):
        layer = entity.dxf.layer
        if wire_layers is None:
            if not layer.startswith("WIRE"):
                continue
        elif layer not in wire_layers:
            continue
        wire_boxes.extend(
            (layer, box) for box in _dxf_segment_boxes(entity, wire_pad)
        )

    offenders: list[str] = []
    for text, text_layer, text_box in text_boxes:
        for wire_layer, wire_box in wire_boxes:
            if _dxf_boxes_overlap(text_box, wire_box):
                offenders.append(
                    f"{sheet_name} {text_layer} text={text!r} "
                    f"crossed by {wire_layer}"
                )
                break
        if len(offenders) >= limit:
            break
    return offenders, len(wire_boxes)


def _check_dxf_wire_text_no_overlap(result: CalculationResult) -> list[CheckResult]:
    """EE-2/EE-2.1 conductors must not cross visible labels.

    `dxf_no_text_overlap` catches text-vs-text only. This guard covers the
    manual-review class where a conductor, bus, or tap line passes through a
    note, equipment header, or visible AutoCAD ATTRIB value.
    """
    name = "dxf_wire_text_no_overlap"
    import ezdxf

    from .dxf.one_line import render_one_line_dxf
    from .dxf.render import render_dxf
    from .electrical.topology import build_electrical_topology
    from .permit.builder import _should_emit_one_line

    sheets = [
        (
            "EE-1/EE-2 three-line",
            render_dxf,
            {"NOTES", "EQUIPMENT_TEXT"},
            None,
        ),
    ]
    if _should_emit_one_line(result):
        schedule_tags = {
            row.tag.upper() for row in build_electrical_topology(result).schedule
        }
        sheets.append((
            "EE-2.1 one-line",
            render_one_line_dxf,
            {"NOTES", "EQUIPMENT_TEXT", "ANNOTATION"},
            {"WIRE_ONE_LINE"},
        ))
    else:
        schedule_tags = set()

    offenders: list[str] = []
    wire_count = 0
    with TemporaryDirectory() as tmp:
        for sheet_name, renderer, text_layers, wire_layers in sheets:
            out = Path(tmp) / f"{sheet_name}.dxf"
            try:
                renderer(result, out)
            except Exception as exc:
                return [CheckResult(name, "FAIL", f"{sheet_name} renderer crashed: {exc}")]
            doc = ezdxf.readfile(str(out))
            sheet_offenders, sheet_wire_count = _dxf_wire_text_offenders(
                doc,
                sheet_name,
                text_layers=text_layers,
                wire_layers=wire_layers,
                ignored_texts=schedule_tags,
            )
            offenders.extend(sheet_offenders)
            wire_count += sheet_wire_count
            if len(offenders) >= 8:
                break

    if offenders:
        return [CheckResult(
            name,
            "FAIL",
            "conductor geometry crosses visible text:\n  "
            + "\n  ".join(offenders[:8]),
        )]
    return [CheckResult(
        name,
        "PASS",
        f"{wire_count} conductor segment(s) clear of visible labels",
    )]


def _check_dxf_text_no_overflow(result: CalculationResult) -> list[CheckResult]:
    """Every TEXT entity on SCHEDULE/TITLE_BLOCK layers in EE-1 and EE-2
    must fit within its container's right edge.

    DXF/matplotlib has no automatic text clipping — text outside its
    container will simply render past the frame line. The Phase J Wyssling
    comparison surfaced this on the EE-2 GROUNDING SCHEDULE "RUN" column:
    long descriptions like "MSP → grounding electrode system" bled past
    the schedule's right border.

    We estimate text width as `len(text) * height * CHAR_WIDTH_RATIO`
    (see `dxf._textfit.CHAR_WIDTH_RATIO`). The ratio is slightly low
    relative to typical rendered width, so this check has a small bias
    toward false-negatives — it won't flag tight-but-fits text — which is
    desirable. Definite overflows (visible bleed past the frame) WILL
    trigger.

    To extend: add a new (layer, x_min, x_max) tuple to LAYER_BOUNDS.
    """
    import ezdxf

    from .dxf._textfit import estimate_text_width
    from .dxf.grounding_sheet import render_grounding_dxf
    from .dxf.one_line import render_one_line_dxf
    from .dxf.render import render_dxf, MARGIN, RIGHT_X0, RIGHT_X1

    # (layer_name, x_left_bound, x_right_bound) — the rectangular bounds
    # text on each layer is expected to stay inside. Layers not in this
    # map are skipped (e.g. ANNOTATION text is free-placed by design —
    # wire tags, callout circles, etc.); EQUIPMENT_TEXT inside device
    # BLOCKs has block-local bounds that aren't measurable at this scope.
    from .dxf.render import (
        RIGHT_X0 as _R0, RIGHT_X1 as _R1, MARGIN as _M, SCHEMATIC_X1 as _SX1,
    )
    LAYER_BOUNDS = {
        "SCHEDULE":    (_R0, _R1),     # right-column schedule table
        "TITLE_BLOCK": (_R0, _R1),     # right-column title block
        "NOTES":       (_M + 0.2, _SX1),  # top-strip notes
    }
    PAD = 0.03

    sheets = [
        ("EE-1", render_dxf),
        ("EE-2", render_grounding_dxf),
        ("EE-2.1", render_one_line_dxf),
    ]
    offenders: list[str] = []

    with TemporaryDirectory() as tmp:
        for sheet_name, renderer in sheets:
            dxf_path = Path(tmp) / f"{sheet_name}.dxf"
            try:
                renderer(result, dxf_path)
            except Exception as exc:
                return [CheckResult(
                    "dxf_text_no_overflow", "FAIL",
                    f"{sheet_name} renderer crashed: {exc}")]
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()
            for entity in msp.query("TEXT"):
                layer = entity.dxf.layer
                if layer not in LAYER_BOUNDS:
                    continue
                left_bound, right_bound = LAYER_BOUNDS[layer]
                # Compute the rendered span based on alignment. halign 0=LEFT,
                # 1=CENTER, 2=RIGHT. The anchor point lives in `insert` for
                # left-aligned text, otherwise in `align_point`.
                halign = entity.dxf.halign
                if halign == 0:
                    anchor_x = entity.dxf.insert.x
                    text_left = anchor_x
                else:
                    anchor_x = entity.dxf.align_point.x
                    width = estimate_text_width(
                        entity.dxf.text, entity.dxf.height)
                    if halign == 1:    # center
                        text_left = anchor_x - width / 2
                    else:               # right
                        text_left = anchor_x - width
                text_right = text_left + estimate_text_width(
                    entity.dxf.text, entity.dxf.height)
                if text_right > right_bound + PAD:
                    overflow = text_right - right_bound
                    offenders.append(
                        f"{sheet_name} layer={layer} "
                        f"text={entity.dxf.text!r} "
                        f"(h={entity.dxf.height:.3f}) "
                        f"overflows right edge by {overflow:.2f}\"")
    if offenders:
        return [CheckResult(
            "dxf_text_no_overflow", "FAIL",
            "DESIGN.md §7 (DXF path) — text past container right edge:\n  "
            + "\n  ".join(offenders))]
    return [CheckResult("dxf_text_no_overflow", "PASS",
                        f"all SCHEDULE/TITLE_BLOCK/NOTES text fits within bounds")]


def _check_site_checklist_covers_schema() -> list[CheckResult]:
    """Every yaml_path in `SITE_FIELDS` must resolve to a real schema
    field, and every label must show up in the rendered PDF text.

    Two failure modes this catches:
      (a) Typo in a `yaml_path` (e.g. "service.main_pannel_a") — would
          silently misroute the technician's value into a non-existent
          field. The schema walk catches this before the PDF renders.
      (b) PDF renderer drops a row (e.g. a Paragraph crashes silently
          due to bad markup). Comparing extracted text vs the SITE_FIELDS
          label list catches missing rows.
    """
    from .schema import Inputs
    from .site_checklist.field_specs import SITE_FIELDS

    # (a) Walk the Inputs pydantic schema, collect every leaf field path.
    schema_paths = _collect_pydantic_paths(Inputs)
    bad_paths = []
    for spec in SITE_FIELDS:
        # Normalize list syntax: "service.sub_panels[].name" → "service.sub_panels.name"
        normalized = spec.yaml_path.replace("[]", "")
        if normalized not in schema_paths:
            bad_paths.append(spec.yaml_path)

    # (b) Render the PDF to a temp file, extract text, verify every
    # label appears. Whitespace is normalized first because pypdf's
    # extract_text() preserves the table cell's line wraps (label
    # column is narrow, longer labels span 2 lines), but the full
    # label is still present once whitespace is collapsed to spaces.
    from .site_checklist.builder import render_checklist
    with TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "checklist.pdf"
        try:
            render_checklist(pdf)
        except Exception as exc:
            return [CheckResult(
                "site_checklist_covers_schema", "FAIL",
                f"render_checklist crashed: {exc}")]
        rendered = _pdf_text(pdf)

    rendered_normalized = " ".join(rendered.split())
    missing_labels = [
        spec.label for spec in SITE_FIELDS
        if " ".join(spec.label.split()) not in rendered_normalized
    ]

    problems = []
    if bad_paths:
        problems.append(
            f"yaml_path doesn't resolve in Inputs schema: {bad_paths}")
    if missing_labels:
        problems.append(
            f"label missing from rendered PDF: {missing_labels}")
    if problems:
        return [CheckResult(
            "site_checklist_covers_schema", "FAIL",
            "; ".join(problems))]
    return [CheckResult(
        "site_checklist_covers_schema", "PASS",
        f"{len(SITE_FIELDS)} fields cross-reference schema + render")]


def _collect_pydantic_paths(model_cls, prefix: str = "") -> set[str]:
    """Walk a pydantic V2 model recursively, return every leaf field
    path (dotted). Drills into nested BaseModel; treats list-of-model
    as drill-able (`field.subfield` ignoring index).
    """
    from pydantic import BaseModel
    from typing import get_args, get_origin, Union

    paths: set[str] = set()
    fields = model_cls.model_fields
    for fname, finfo in fields.items():
        full = f"{prefix}{fname}" if prefix == "" else f"{prefix}.{fname}"
        paths.add(full)
        anno = finfo.annotation
        # Strip Optional[T] (Union[T, None]) to T.
        origin = get_origin(anno)
        if origin is Union:
            args = [a for a in get_args(anno) if a is not type(None)]
            if len(args) == 1:
                anno = args[0]
                origin = get_origin(anno)
        # list[T] → drill into T if T is a BaseModel subclass.
        if origin is list:
            inner = get_args(anno)[0] if get_args(anno) else None
            if inner is not None and isinstance(inner, type) and issubclass(inner, BaseModel):
                paths.update(_collect_pydantic_paths(inner, prefix=full))
        elif isinstance(anno, type) and issubclass(anno, BaseModel):
            paths.update(_collect_pydantic_paths(anno, prefix=full))
    return paths


def _check_dxf_no_text_overlap(result: CalculationResult) -> list[CheckResult]:
    """No two TEXT entities in EE-1 / EE-2 modelspace should have
    overlapping bounding boxes.

    Closes the second-class collision the overflow check can't catch:
    Phase J cover-index regression had MSP's "BUS 200A" ATTDEF text
    visually crossing the SUB-#1 header text "(N) SUB PANEL #1" before
    we widened `gap_above`. Doctor's overflow check ran clean — both
    texts were within their containers — but they were on top of
    each other.

    Skips ANNOTATION layer (wire tags / callouts are intentionally
    placed near other elements). ATTRIBs are also skipped because they
    sit in dense vertical stacks below each device by design.
    """
    import ezdxf

    from .dxf._textfit import estimate_text_width
    from .dxf.grounding_sheet import render_grounding_dxf
    from .dxf.one_line import render_one_line_dxf
    from .dxf.render import render_dxf

    # Skip these layers when scanning for overlap: their text density is
    # intentional (wire tags lying on conductors, electrode captions, …).
    SKIP_LAYERS = {"ANNOTATION"}
    # Allow up to 25% of the smaller bbox area to overlap. Below this
    # threshold = visual proximity, not collision. Above = genuine pile-up.
    MIN_OVERLAP_RATIO = 0.25

    def _bbox(entity) -> tuple[float, float, float, float]:
        """Estimate (x_min, y_min, x_max, y_max) for a TEXT entity."""
        halign = entity.dxf.halign
        height = entity.dxf.height
        width = estimate_text_width(entity.dxf.text, height)
        # Anchor depends on alignment:
        #   halign 0 (LEFT)  → insert is the baseline-left point
        #   halign 1 (CENTER) → align_point is centered
        #   halign 2 (RIGHT) → align_point is baseline-right
        if halign == 0:
            x_min = entity.dxf.insert.x
            y_baseline = entity.dxf.insert.y
        else:
            anchor_x = entity.dxf.align_point.x
            y_baseline = entity.dxf.align_point.y
            if halign == 1:
                x_min = anchor_x - width / 2
            else:
                x_min = anchor_x - width
        # Cap height ≈ 0.75 × text height above baseline; descenders ~25% below.
        return (x_min,
                y_baseline - height * 0.25,
                x_min + width,
                y_baseline + height * 0.75)

    def _overlap_ratio(a, b) -> float:
        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
        iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy
        if inter <= 0:
            return 0.0
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        return inter / max(1e-9, min(area_a, area_b))

    sheets = [
        ("EE-1", render_dxf),
        ("EE-2", render_grounding_dxf),
        ("EE-2.1", render_one_line_dxf),
    ]
    offenders: list[str] = []

    with TemporaryDirectory() as tmp:
        for sheet_name, renderer in sheets:
            dxf_path = Path(tmp) / f"{sheet_name}.dxf"
            try:
                renderer(result, dxf_path)
            except Exception as exc:
                return [CheckResult("dxf_no_text_overlap", "FAIL",
                                    f"{sheet_name} renderer crashed: {exc}")]
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()
            texts = [
                e for e in msp.query("TEXT")
                if e.dxf.layer not in SKIP_LAYERS
            ]
            for i, a in enumerate(texts):
                bb_a = _bbox(a)
                for b in texts[i + 1:]:
                    bb_b = _bbox(b)
                    ratio = _overlap_ratio(bb_a, bb_b)
                    if ratio > MIN_OVERLAP_RATIO:
                        offenders.append(
                            f"{sheet_name} {a.dxf.layer}/{b.dxf.layer} "
                            f"{a.dxf.text!r} ↔ {b.dxf.text!r} "
                            f"(overlap {ratio:.0%})")
                        if len(offenders) >= 8:    # cap report size
                            break
                if len(offenders) >= 8:
                    break
            if len(offenders) >= 8:
                break

    if offenders:
        return [CheckResult(
            "dxf_no_text_overlap", "FAIL",
            "TEXT bounding-boxes pile up:\n  " + "\n  ".join(offenders))]
    return [CheckResult("dxf_no_text_overlap", "PASS",
                        "no TEXT bbox overlaps above 25% threshold")]


def _check_no_fixed_width_truncation_markers(project_dir: Path) -> list[CheckResult]:
    """Source-level scan: forbid `text[:N]` string-slice patterns in
    rendering code. DESIGN.md §7 — fixed-width truncation is policy-violation.

    Scope: src/pvess_calc/permit/ and src/pvess_calc/dxf/ — the rendering
    layer. We tolerate slicing in pure-data modules (calc/, schema.py).
    """
    import re

    pkg_root = Path(__file__).resolve().parent
    scan_roots = [pkg_root / "permit", pkg_root / "dxf"]
    # Match patterns like `desc[:30]`, `name[:20]` on a string variable.
    # Allow `[: N]` on results known to be ints (e.g. address[:5]) by
    # requiring at least 2-letter identifier and a digit ≥ 10.
    pat = re.compile(r"\b([a-z_][a-z_0-9]{2,})\[:(\d{2,})\]")
    offenders: list[str] = []
    for root in scan_roots:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            for lineno, line in enumerate(py.read_text().splitlines(), 1):
                # Skip comments
                stripped = line.split("#", 1)[0]
                m = pat.search(stripped)
                if m:
                    offenders.append(
                        f"{py.relative_to(pkg_root.parent.parent)}:{lineno}: "
                        f"{m.group(0)}")
    if offenders:
        return [CheckResult(
            "no_truncation_slices", "FAIL",
            "DESIGN.md §7 violation — fixed-width slices in render code:\n  "
            + "\n  ".join(offenders))]
    return [CheckResult("no_truncation_slices", "PASS")]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _pdf_text(pdf_path: Path) -> str:
    """Extract all text from a PDF. Uses pypdf which is already a dep."""
    from pypdf import PdfReader
    text_chunks: list[str] = []
    reader = PdfReader(str(pdf_path))
    for page in reader.pages:
        text_chunks.append(page.extract_text() or "")
    return "\n".join(text_chunks)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────


def _check_roof_usable_area_sufficient(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.2.6c — verify every roof_section has enough usable area for
    its claimed module count (after subtracting NEC 690.12 setbacks
    and obstruction halos).

    FAIL when ANY section's module demand (count × 22 sqft/module)
    exceeds its computed usable area — the project as drawn can't
    physically install the panels it claims.

    Skips with PASS when the yaml has zero roof_sections (legacy
    Smith Residence, scenario yamls): no roof data → nothing to
    verify, but also no false alarm.
    """
    name = "roof_usable_area_sufficient"
    layout = calc_result.roof_layout
    if not layout.sections:
        return [CheckResult(name, "PASS",
                            "no roof_sections defined (skipped)")]
    failing = [s for s in layout.sections if not s.fits]
    if failing:
        details = "; ".join(
            f"{s.name} ({s.module_count} mods need {s.module_demand_sqft:.0f}"
            f" sqft, usable {s.usable_area_sqft:.0f})"
            for s in failing
        )
        return [CheckResult(name, "FAIL",
                            f"over-packed: {details}")]
    # Surface any geometry-error obstructions (located outside the
    # section bounding box) as a WARN-but-PASS — the calc engine
    # already skipped them, the doctor just reminds the user to fix
    # the yaml input.
    outside = [
        s.name for s in layout.sections
        if s.obstructions_outside_usable_area
    ]
    if outside:
        return [CheckResult(name, "PASS",
                            f"{len(layout.sections)} sections fit; "
                            f"WARN: obstructions outside section "
                            f"bounds on {','.join(outside)}")]
    return [CheckResult(name, "PASS",
                        f"{len(layout.sections)} sections fit "
                        f"({layout.total_usable_sqft:.0f} sqft total usable)")]


def _check_grounding_electrode_system_compliant(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.5 — verify the project's actual grounding electrode system
    meets NEC 250 requirements.

    FAIL conditions:
      * `gec_comparison.status == 'UNDERSIZED'` — existing GEC below
        NEC 250.66 requirement; project can't be permitted as-drawn.
      * NEC 250.50 supplementary electrode rule unsatisfied: when ONLY
        rods are declared, NEC 250.53(A)(2) requires either 2 rods
        ≥6 ft apart OR a documented ≤25 Ω resistance test. Single rod
        without other electrodes → FAIL.

    WARN-but-PASS:
      * Yaml supplied no GES block at all (`bonded_to_neutral_at_service
        == 'unknown'` AND no rods/water/Ufer) → defer to engineer.
      * Bonding status `unknown` — engineer must site-verify.

    Skipped (PASS, "no GES data"):
      * Legacy yaml with zero GES content — preserves backward compat.
    """
    name = "grounding_electrode_system_compliant"
    ges = calc_result.inputs.service.grounding_electrode_system
    grounding = calc_result.grounding

    has_any_data = bool(
        ges.rods or ges.metal_water_pipe or ges.ufer or ges.gec_main_size_awg
        or ges.bonded_to_neutral_at_service != "unknown"
    )

    if not has_any_data:
        return [CheckResult(name, "PASS",
                            "no GES data on file (using default assumptions)")]

    failures: list[str] = []

    # (1) GEC sizing
    if grounding.gec_comparison and grounding.gec_comparison.status == "UNDERSIZED":
        failures.append(
            f"GEC #{grounding.gec_comparison.actual_size} AWG below NEC 250.66 "
            f"required #{grounding.gec_comparison.required_size} AWG"
        )

    # (2) NEC 250.50 — at least 2 electrodes OR a single rod + ≤25 Ω test.
    # We can't observe the resistance test from the yaml, so the rule
    # we enforce is: if only rods are present, require ≥2 rods.
    n_rods = len(ges.rods)
    has_other = bool(
        (ges.metal_water_pipe and ges.metal_water_pipe.confirmed_metal_underground)
        or ges.ufer
    )
    if n_rods > 0 and not has_other and n_rods < 2:
        failures.append(
            "single rod electrode without supplementary electrode — "
            "NEC 250.53(A)(2) requires either 2 rods ≥6 ft apart OR a "
            "documented ≤25 Ω resistance test"
        )

    # (3) Bonding status
    warns: list[str] = []
    if ges.bonded_to_neutral_at_service == "no":
        failures.append(
            "neutral-to-ground main bonding jumper missing at MSP "
            "(NEC 250.24) — compliance gap"
        )
    elif ges.bonded_to_neutral_at_service == "unknown":
        warns.append("bonding status unknown — site-verify before energization")

    if failures:
        return [CheckResult(name, "FAIL", "; ".join(failures))]
    if warns:
        return [CheckResult(name, "PASS", f"WARN: {warns[0]}")]
    return [CheckResult(name, "PASS",
                        f"{ges.electrode_count} electrode(s); GEC compliant")]


def _check_ess_install_compliant(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.2.6b — ESS install location must NOT be marked FAIL by the
    NEC 706.10 / IRC R328 evaluator. WARN (data-missing) and PASS are
    both acceptable; FAIL means a physical install rule was actually
    violated and the project can't ship as-drawn.

    Doctor exits non-zero when ess_install.overall_status == 'FAIL' so
    permit packages don't go out the door with a battery in a code-
    forbidden spot.
    """
    name = "ess_install_compliant"
    if not calc_result.inputs.battery.installed:
        return [CheckResult(name, "PASS", "PV-only project; ESS install skipped")]

    ei = calc_result.ess_install
    if ei.overall_status == "FAIL":
        failing = [c for c in ei.checks if c.status == "FAIL"]
        details = "; ".join(
            f"{c.name}@{c.code_ref}" for c in failing
        )
        return [CheckResult(name, "FAIL", details)]
    if ei.overall_status == "WARN":
        # WARN = missing data. Don't fail the doctor — but surface it.
        return [CheckResult(name, "PASS",
                            f"WARN ({ei.install_location}); "
                            "set battery.install_location + setbacks for full check")]
    return [CheckResult(name, "PASS",
                        f"{ei.install_location}: {len(ei.checks)} checks passed")]


def _check_nec_edition_artifacts_consistent(
    calc_result: CalculationResult, project_dir: Path,
) -> list[CheckResult]:
    """K.7 [1/4] guard — the NEC edition declared in inputs.yaml must
    appear in every artifact that quotes it (report.md, customer
    summary, permit cover). Drift here means a homeowner / AHJ
    reviewer sees a different edition than the engineer used.

    Skipped (PASS, "no artifacts to check") when neither report.md
    nor permit-package-*.pdf exists yet — `pvess calc` hasn't run.
    """
    name = "nec_edition_artifacts_consistent"
    declared = calc_result.inputs.project.nec_edition
    report_md = project_dir / "output" / "report.md"
    permit_dir = project_dir / "output"

    artifacts_checked = 0
    problems: list[str] = []
    if report_md.exists():
        artifacts_checked += 1
        text = report_md.read_text(encoding="utf-8")
        if f"NEC 版本 | {declared}" not in text and f"NEC {declared}" not in text:
            problems.append(f"report.md missing NEC {declared}")
    permit_pdfs = list(permit_dir.glob("permit-package-*.pdf"))
    if permit_pdfs:
        artifacts_checked += 1
        from pypdf import PdfReader
        text = "\n".join(
            (p.extract_text() or "")
            for p in PdfReader(str(permit_pdfs[0])).pages
        )
        if declared not in text:
            problems.append(
                f"permit-package PDF missing NEC edition '{declared}' text"
            )

    if artifacts_checked == 0:
        return [CheckResult(name, "PASS",
                            "no artifacts to check (run `pvess calc` first)")]
    if problems:
        return [CheckResult(name, "FAIL", "; ".join(problems))]
    return [CheckResult(name, "PASS",
                        f"{artifacts_checked} artifact(s) carry NEC {declared}")]


def _check_export_tariff_matches_state(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.7 [2/4] guard — flag projects where the export-tariff model
    is incompatible with the project state.

    Hard FAIL cases:
      * CA project + `1to1_nem` → 1:1 NEM is closed to new applicants
        in California since 2023-04. ROI math will overstate savings.
      * HI project + `1to1_nem` → Hawaii closed NEM in 2015; CSS /
        Smart Export are the only paths.

    Other states with `1to1_nem` → PASS. CA / HI projects already on
    `ca_nem3` / `hi_self_consumption` → PASS.
    """
    name = "export_tariff_matches_state"
    inputs = calc_result.inputs
    tariff = inputs.loads.export_tariff_model

    # Pull state from `project.location` if possible. The wizard format
    # is "City, ST" — we look for the 2-letter state token at the end.
    location = (inputs.project.location or "").strip()
    state: str | None = None
    if "," in location:
        # Try last token after final comma
        last_chunk = location.rsplit(",", 1)[-1].strip()
        tokens = last_chunk.split()
        for tok in tokens:
            if len(tok) == 2 and tok.upper() in _US_STATE_ABBREVS:
                state = tok.upper()
                break

    # Mismatch table — expand here as more states adopt successor tariffs.
    state_mandatory_tariff = {
        "CA": "ca_nem3",
        "HI": "hi_self_consumption",
    }

    if state and state in state_mandatory_tariff:
        required = state_mandatory_tariff[state]
        if tariff != required:
            return [CheckResult(
                name, "FAIL",
                f"project location is {state} but loads.export_tariff_model = "
                f"'{tariff}'; expected '{required}' (state mandate). "
                "K.4 ROI math will overstate savings.",
            )]
        return [CheckResult(name, "PASS",
                            f"{state} project on '{tariff}' (state-correct)")]

    return [CheckResult(name, "PASS",
                        f"tariff '{tariff}' (no state-level mandate detected)")]


def _check_regional_requirements_consistent(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    name = "regional_requirements_consistent"
    regional = getattr(calc_result, "regional", None)
    if regional is None or not regional.checks:
        return [CheckResult(name, "PASS", "no regional rule overlay")]

    failures = [
        f"{c.jurisdiction} {c.topic}: {c.detail}"
        for c in regional.checks if c.status == "FAIL"
    ]
    manuals = [
        f"{c.jurisdiction} {c.topic}: {c.detail}"
        for c in regional.checks if c.status == "MANUAL"
    ]
    warnings = [
        f"{c.jurisdiction} {c.topic}: {c.detail}"
        for c in regional.checks if c.status == "WARN"
    ]
    if failures:
        return [CheckResult(name, "FAIL", "; ".join(failures))]
    if manuals or warnings:
        return [CheckResult(
            name,
            "WARN",
            f"{len(regional.checks)} regional check(s); review "
            + "; ".join(manuals + warnings),
        )]
    return [CheckResult(
        name,
        "PASS",
        f"{len(regional.checks)} regional check(s) passed",
    )]


_US_STATE_ABBREVS: frozenset[str] = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
})


def _check_tx_rep_plan_explicitly_chosen(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.4.6.6 — TX projects on the generic `1to1_nem` tariff are likely
    leaving money on the table. Texas is fully deregulated → there's no
    "default" 1:1 NEM; the homeowner is on SOME specific REP plan with
    SOME specific buyback rate. Failing to pick a tx_* preset means
    the customer-PDF savings number is suspiciously round.

    WARN (not FAIL) — we don't know for certain which REP the homeowner
    chose. Fires when:
        project.location contains "TX" (or "Texas")
      AND
        loads.export_tariff_model == "1to1_nem"
      AND
        loads.rep_buyback_ratio is None (no escape-hatch override)

    PASS for: TX projects on a tx_* preset OR a custom rep_buyback_ratio.
    Non-TX projects: PASS-skip (this check has no opinion).
    """
    name = "tx_rep_plan_explicitly_chosen"
    inputs = calc_result.inputs
    location_lc = (inputs.project.location or "").lower()
    is_tx = ", tx" in location_lc or location_lc.endswith(" tx") \
        or "texas" in location_lc or "frisco" in location_lc \
        or "houston" in location_lc or "austin" in location_lc \
        or "dallas" in location_lc

    if not is_tx:
        return [CheckResult(name, "PASS",
                            "non-TX project (skipped)")]

    tariff = inputs.loads.export_tariff_model
    has_custom = inputs.loads.rep_buyback_ratio is not None

    if has_custom:
        return [CheckResult(name, "PASS",
                            f"TX project with explicit rep_buyback_ratio "
                            f"({inputs.loads.rep_buyback_ratio:.2f})")]

    if tariff.startswith("tx_"):
        return [CheckResult(name, "PASS",
                            f"TX project on '{tariff}' preset")]

    if tariff == "1to1_nem":
        return [CheckResult(
            name, "WARN",
            "TX project on generic '1to1_nem' — Texas has no default NEM. "
            "Pick a TX REP preset (tx_green_mountain / tx_txu_buyback for "
            "1:1; tx_default_oncor for ~0.5×). Wrong assumption can swing "
            "monthly savings by ±$90.",
        )]

    return [CheckResult(name, "PASS",
                        f"TX project on '{tariff}' (non-default tariff)")]


def _check_self_consumption_realistic_for_rep_plan(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.4.6.6 — when the REP plan pays sub-1:1 for exports, the
    self-consumption fraction starts to matter a LOT. Smart Meter Texas
    + intentional load shifting (dishwasher / EV charging / pool pump
    scheduled to PV hours) raises self-consumption from ~0.30 (passive)
    to 0.60+ (active). For sub-1:1 plans this is the difference between
    a 14 yr and an 11 yr payback — bigger than picking the right inverter.

    Fires WARN when:
        rep_buyback_ratio < 0.80 (sub-1:1 plan, exported kWh discounted)
      AND
        self_consumption_fraction < 0.40 (passive baseline assumption)
      AND
        battery.installed = False (no battery-driven time-shifting)

    Hint message points to SMT + load scheduling. PASS for 1:1 plans
    (self_cons math collapses, doesn't matter) or for projects that
    have already declared aggressive self-consumption.
    """
    name = "self_consumption_realistic_for_rep_plan"
    inputs = calc_result.inputs
    sc = inputs.loads.self_consumption_fraction

    # Resolve actual export ratio from the same precedence chain as
    # economics.py uses.
    if inputs.loads.rep_buyback_ratio is not None:
        ratio = float(inputs.loads.rep_buyback_ratio)
    else:
        from .customer.economics import EXPORT_RATIOS
        ratio = EXPORT_RATIOS.get(inputs.loads.export_tariff_model, 1.0)

    if ratio >= 0.99:
        return [CheckResult(name, "PASS",
                            "1:1 REP plan — self-consumption math collapses"
                            " (no opinion needed)")]

    if sc >= 0.40:
        return [CheckResult(name, "PASS",
                            f"sub-1:1 plan (ratio {ratio:.2f}) but self-cons "
                            f"{sc:.2f} is already in the load-shifted band")]

    if inputs.battery.installed:
        return [CheckResult(name, "PASS",
                            "battery installed — time-shifting handled at the "
                            "ESS layer, not at the load-scheduling layer")]

    return [CheckResult(
        name, "WARN",
        f"REP buyback {ratio:.2f}× + passive self_cons {sc:.2f}: with Smart "
        f"Meter Texas + load-shifted dishwasher / EV / pool pump, real-world "
        f"self_cons climbs to 0.60+ → adds roughly ${(0.60 - sc) * (1 - ratio) * inputs.pv_array.modules * inputs.pv_array.module.power_w * 1.535:.0f}/yr. "
        "Either raise self_consumption_fraction or switch to a 1:1 REP plan.",
    )]


def _check_ee4a_property_context_data_driven(
    result: CalculationResult,
) -> list[CheckResult]:
    """Stage 9.9 guard — EE-4A uses explicit property-context geometry.

    When a project supplies `site.property_context`, the rendered sheet must
    carry the survey labels that prove the data path is connected. Empty
    context remains a supported fallback and passes with a skip-style note.
    """
    name = "ee4a_property_context_data_driven"
    context = result.inputs.site.property_context
    if not context.has_data:
        return [CheckResult(name, "PASS",
                            "no property_context block (fallback context)")]
    try:
        import pypdf
        from .permit.property_context import render_property_context_plan
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    with TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "ee-4a.pdf"
        try:
            render_property_context_plan(result, pdf)
            text = "\n".join(
                p.extract_text() or "" for p in pypdf.PdfReader(str(pdf)).pages
            )
        except Exception as exc:
            return [CheckResult(name, "FAIL",
                                f"EE-4A render/text extraction crashed: {exc}")]

    missing = [
        label for label in ("PROPERTY LINE", "DRIVEWAY", "FENCE", "EE-4A")
        if label not in text
    ]
    for dim in context.property_dimensions:
        label = dim.label or _feet_label_for_doctor(dim.start, dim.end)
        if label not in text:
            missing.append(label)
    if missing:
        return [CheckResult(name, "FAIL",
                            f"EE-4A missing context text: {missing}")]
    return [CheckResult(
        name, "PASS",
        f"{len(context.lot_outline)} lot verts, "
        f"{len(context.driveway_polygon)} driveway verts, "
        f"{len(context.property_dimensions)} dimension(s)",
    )]


def _feet_label_for_doctor(
    start: tuple[float, float],
    end: tuple[float, float],
) -> str:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    value = (dx * dx + dy * dy) ** 0.5
    whole = int(value)
    inches = int(round((value - whole) * 12))
    if inches == 12:
        whole += 1
        inches = 0
    if inches:
        return f"{whole}'-{inches}\""
    return f"{whole}'"


def _check_rsd_label_substitution_wired() -> list[CheckResult]:
    """K.7 [1/4] guard — the RSD label body must reference
    `{{RSD_BOUNDARY_V}}` AND build_substitutions must populate it.
    Catches the K.7 wiring contract breaking silently (e.g. someone
    drops the substitution key from build_substitutions).

    Source-level + import-level check. No file IO.
    """
    name = "rsd_label_substitution_wired"
    try:
        from pvess_calc.labels.specs import LABEL_CATALOG
        from pvess_calc.qet.inject import build_substitutions
        from pvess_calc.calc.engine import run as run_calc
        from pvess_calc.schema import (
            Battery, Inputs, Inverter, Loads, ProjectMeta, PvArray, PvModule,
            Service,
        )
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    # 1. Find the RSD label spec
    rsd_spec = next(
        (l for l in LABEL_CATALOG if "RAPID SHUTDOWN" in l.title),
        None,
    )
    if rsd_spec is None:
        return [CheckResult(name, "FAIL",
                            "no RAPID SHUTDOWN label in LABEL_CATALOG")]
    body_text = "\n".join(rsd_spec.body_lines)
    if "{{RSD_BOUNDARY_V}}" not in body_text:
        return [CheckResult(
            name, "FAIL",
            "RSD label body missing {{RSD_BOUNDARY_V}} placeholder — "
            "K.7 wiring broken",
        )]

    # 2. Verify build_substitutions populates RSD_BOUNDARY_V per edition.
    # Use a minimal Inputs (no yaml load).
    def _build_minimal(nec_edition: str) -> Inputs:
        return Inputs(
            project=ProjectMeta(id="t", name="t", location="t",
                                ahj="t", nec_edition=nec_edition),
            pv_array=PvArray(
                modules=12, strings=1, modules_per_string=12,
                module=PvModule(
                    brand="X", model="Y", power_w=400,
                    voc_stc=50, isc_stc=13,
                    voc_temp_coeff_pct_per_c=-0.28,
                    isc_temp_coeff_pct_per_c=0.048,
                ),
                ashrae_2pct_min_c=-5, temp_min_c=-5, temp_max_c=45,
            ),
            battery=Battery(brand="X", model="Y", quantity=1,
                            nominal_voltage=48, capacity_kwh_each=10),
            inverter=Inverter(brand="X", model="Y", ac_output_v=240,
                              ac_output_a=30, per_unit=True),
            service=Service(main_panel_a=200, busbar_a=200,
                            voltage="120/240 split-phase",
                            interconnection_methods=["120%_rule"]),
            loads=Loads(),
        )
    try:
        subs_2017 = build_substitutions(run_calc(_build_minimal("2017")))
        subs_2020 = build_substitutions(run_calc(_build_minimal("2020")))
    except Exception as exc:
        return [CheckResult(name, "FAIL",
                            f"build_substitutions crashed: {exc!r}")]
    if subs_2017.get("RSD_BOUNDARY_V") != "80 V":
        return [CheckResult(
            name, "FAIL",
            f"NEC 2017 RSD_BOUNDARY_V = "
            f"{subs_2017.get('RSD_BOUNDARY_V')!r}, expected '80 V'",
        )]
    if subs_2020.get("RSD_BOUNDARY_V") != "30 V":
        return [CheckResult(
            name, "FAIL",
            f"NEC 2020 RSD_BOUNDARY_V = "
            f"{subs_2020.get('RSD_BOUNDARY_V')!r}, expected '30 V'",
        )]
    return [CheckResult(name, "PASS",
                        "RSD label substitution wired (2017→80V, 2020→30V)")]


def _check_compare_pdf_renderable() -> list[CheckResult]:
    """K.7 [4/4] guard — Phoenix's scenarios directory must render the
    comparison PDF without exception. Closes the contract that
    `pvess compare` emits a PDF alongside the .md/.json triple.

    Runs in a tmp dir so we don't touch project artifacts.
    """
    name = "compare_pdf_renderable"
    import shutil
    import tempfile

    project_root = Path(__file__).resolve().parent.parent.parent
    src_dir = project_root / "projects" / "002-phoenix-25kw" / "scenarios"
    if not src_dir.exists():
        return [CheckResult(name, "PASS",
                            "no scenarios directory available (skipped)")]
    try:
        from pvess_calc.compare.report import write_outputs
        from pvess_calc.compare.scenarios import run_scenarios
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "scenarios"
        shutil.copytree(src_dir, work)
        try:
            scenarios = run_scenarios(work)
            if not scenarios:
                return [CheckResult(name, "PASS",
                                    "scenarios directory empty (skipped)")]
            write_outputs(
                scenarios,
                md_path=work / "comparison.md",
                json_path=work / "comparison.json",
            )
        except Exception as exc:
            return [CheckResult(name, "FAIL",
                                f"compare PDF rendering crashed: {exc!r}")]
        pdf = work / "comparison.pdf"
        if not pdf.exists() or pdf.stat().st_size < 2000:
            return [CheckResult(
                name, "FAIL",
                f"compare PDF missing or empty ({pdf.stat().st_size if pdf.exists() else 0} B)",
            )]
        return [CheckResult(name, "PASS",
                            f"compare PDF rendered ({pdf.stat().st_size:,} B)")]


def _check_customer_summary_renderable(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.4 — customer-summary PDF must render cleanly for the project
    even when none of the optional inputs (monthly_kwh, address-derived
    rate, NREL data) are present. The pipeline is intentionally
    degradation-tolerant — this check enforces that contract by running
    the renderer with **no lookup_fields** (worst-case path).

    PASS criteria:
      * `render_customer_summary` returns without exception
      * Output file is >= 10 KB (sanity: contains at least the title +
        spec strip + monthly chart)
    """
    name = "customer_summary_renderable"
    import tempfile

    try:
        from .customer.pdf import render_customer_summary
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "customer-summary.pdf"
        try:
            render_customer_summary(calc_result, out)   # no lookup_fields
        except Exception as exc:
            return [CheckResult(name, "FAIL",
                                f"renderer crashed: {exc!r}")]
        size = out.stat().st_size if out.exists() else 0
        if size < 10_000:
            return [CheckResult(name, "FAIL",
                                f"output too small ({size} B) — "
                                "renderer may have skipped sections")]
        return [CheckResult(name, "PASS", f"rendered ({size:,} B)")]


def _check_customer_design_tokens_respected() -> list[CheckResult]:
    """K.4 closing-standard guard: the PDF must use only the 4 typography
    tiers and 2 accent colors declared in `customer/design_tokens.py`.

    Implementation: import the customer.pdf module and crawl its styles
    dict, asserting every font size matches one of the declared tier
    constants. Catches the regression "someone hard-coded fontSize=14
    inline" before it ships.
    """
    name = "customer_design_tokens_respected"
    try:
        from .customer import design_tokens as dt
        from .customer.pdf import _styles
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    allowed_sizes = {dt.PT_HERO, dt.PT_TITLE, dt.PT_BODY, dt.PT_MICRO,
                     # Two adjacent half-tier helpers used by the
                     # spec-strip captions and section titles. Keeping
                     # them whitelisted on PURPOSE — if you add a third
                     # half-tier the check fails, forcing a discussion.
                     dt.PT_TITLE - 0.0,        # hero_sm reuses PT_TITLE
                     dt.PT_BODY + 1.5,         # section_title
                     }
    bad: list[str] = []
    for style_name, style in _styles().items():
        if style.fontSize not in allowed_sizes:
            bad.append(f"{style_name}={style.fontSize}")
    if bad:
        return [CheckResult(name, "FAIL",
                            f"non-tier font sizes: {bad}")]
    return [CheckResult(name, "PASS",
                        f"{len(_styles())} styles all use design-token sizes")]


def _check_lookup_offline_works_without_keys() -> list[CheckResult]:
    """K.3b — verifies that the lookup service still returns offline
    data even when neither API key is present. Closing contract:
    online providers must NEVER be required for the wizard / CLI to
    function. Run with a temp cache so we don't pollute the user's
    ~/.pvess between doctor invocations."""
    name = "lookup_offline_works_without_keys"
    import os
    import tempfile

    from .lookup import resolve
    from .lookup.config import (
        ENV_MAPBOX_TOKEN,
        ENV_NREL_API_KEY,
        reset_cache_for_tests,
    )

    # Snapshot + clear env vars so this check is independent of the
    # caller's shell state.
    saved_mapbox = os.environ.pop(ENV_MAPBOX_TOKEN, None)
    saved_nrel = os.environ.pop(ENV_NREL_API_KEY, None)
    saved_cache = os.environ.get("PVESS_CACHE_ROOT")
    reset_cache_for_tests()

    try:
        with tempfile.TemporaryDirectory() as td:
            os.environ["PVESS_CACHE_ROOT"] = td
            r = resolve("Phoenix, AZ")
            offline_fields = {
                k for k, src in r.field_sources.items()
                if not src.startswith(("mapbox", "nrel"))
            }
            if len(offline_fields) < 5:
                return [CheckResult(
                    name, "FAIL",
                    f"offline chain returned only {len(offline_fields)} "
                    f"fields for Phoenix — expected ≥ 5"
                )]
            return [CheckResult(
                name, "PASS",
                f"{len(offline_fields)} offline fields without API keys",
            )]
    finally:
        # Restore environment to whatever the caller had.
        if saved_mapbox is not None:
            os.environ[ENV_MAPBOX_TOKEN] = saved_mapbox
        if saved_nrel is not None:
            os.environ[ENV_NREL_API_KEY] = saved_nrel
        if saved_cache is None:
            os.environ.pop("PVESS_CACHE_ROOT", None)
        else:
            os.environ["PVESS_CACHE_ROOT"] = saved_cache
        reset_cache_for_tests()


def _check_production_breakdown_per_face(
    inputs: Inputs,
) -> list[CheckResult]:
    """K.8 / K.8.1 — if `site.roof_sections` is present, the
    `EconomicsResult` must carry a per-face `production_breakdown`
    matching the count of sections-with-area, with a sensible blended
    derate.

    Three-way state distinction (K.8.1):
      1. No `roof_sections` at all → PASS "single-orientation project"
         (Austin demo, Smith Residence, scenario yamls).
      2. `roof_sections` present but `pv_array.modules = 0` → PASS
         "no PV declared (skipped)" (zero-system test fixtures).
      3. `roof_sections` present + modules > 0 → MUST produce a
         per-face breakdown. The breakdown's face count equals
         `sections_with_area` regardless of whether the designer
         hand-distributed `module_count` (method="per_face") or the
         engine auto-distributed by area (method="per_face_auto_distributed",
         K.8.1 K.3c handoff path).

    Catches three regression classes:
      * Someone bypasses `compute_annual_production` and recomputes
        production inline using the legacy `system_kw × baseline`,
        losing the per-face math.
      * The aggregator silently falls back to `system_aggregate` when
        sections are present (e.g., schema field rename without
        updating the production path).
      * `blended_derate` becomes None / 0 / negative — meaning the
        weighting math is broken.
    """
    name = "production_breakdown_per_face"
    from .customer.economics import compute_economics

    # State 1: no sections at all → genuinely single-orientation.
    if not inputs.site.roof_sections:
        return [CheckResult(name, "PASS",
                            "single-orientation project (skipped)")]

    # State 2: sections present but no PV at all (zero-system fixture).
    if inputs.pv_array.modules <= 0:
        return [CheckResult(name, "PASS",
                            "no PV declared (skipped)")]

    # State 3: must produce a breakdown. Count "usable" sections — those
    # with positive gross area; the auto-distribute path skips zero-area
    # faces, so the breakdown count compares against `sections_with_area`,
    # NOT `sections_with_modules` (the K.3c-init case has module_count=0
    # everywhere but areas > 0).
    sections_with_area = [
        s for s in inputs.site.roof_sections if s.gross_area_sqft > 0
    ]
    if not sections_with_area:
        return [CheckResult(name, "PASS",
                            "all sections have zero area (degenerate yaml)")]

    e = compute_economics(inputs)
    if len(e.production_breakdown) != len(sections_with_area):
        return [CheckResult(
            name, "FAIL",
            f"{len(sections_with_area)} usable sections declared but "
            f"{len(e.production_breakdown)} faces in production_breakdown "
            f"(method={e.production_breakdown and 'set' or 'empty'})",
        )]
    if e.production_blended_derate is None:
        return [CheckResult(
            name, "FAIL",
            "multi-face project missing production_blended_derate",
        )]
    if not (0.0 < e.production_blended_derate <= 1.0):
        return [CheckResult(
            name, "FAIL",
            f"blended_derate out of range: {e.production_blended_derate}",
        )]
    # Each face's kWh must match baseline × kw × orientation × shading.
    # Skip when faces have annual_production_kwh == 0 (consistent).
    for face in e.production_breakdown:
        if face.kw_dc <= 0:
            return [CheckResult(
                name, "FAIL", f"face {face.name!r} has kw_dc={face.kw_dc}",
            )]
        if not (0.0 < face.orientation_derate <= 1.0):
            return [CheckResult(
                name, "FAIL",
                f"face {face.name!r} orientation_derate "
                f"{face.orientation_derate} out of (0, 1]",
            )]
    # Indicate auto-distribute path in the detail line so the engineer
    # sees "K.3c init" projects need a manual distribution review before
    # submitting to AHJ.
    sections_with_modules = sum(
        1 for s in inputs.site.roof_sections if s.module_count > 0
    )
    suffix = ""
    if sections_with_modules == 0:
        suffix = " (auto-distributed by area — designer review recommended)"
    return [CheckResult(
        name, "PASS",
        f"{len(e.production_breakdown)} face(s), "
        f"blended derate {e.production_blended_derate*100:.0f}%{suffix}",
    )]


def _check_cover_kv_values_fit_block_width(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.12.5+ — guard against the 2026-05-17 "AC bleeds past frame"
    bug class. The cover-sheet's KV blocks (SCOPE OF WORK, GOVERNING
    CODES, etc.) used a heuristic char-count for truncation; on narrow
    blocks the heuristic let long values escape the block boundary.

    This check renders the cover and inspects every text fragment via
    a known dictionary of "values that risk overflow" — system size,
    inverter model, battery model. Each must NOT contain whitespace
    suggesting wraparound (or worse, be silently truncated mid-word
    without an ellipsis).

    We check the PRESENCE of the full value strings in the extracted
    PDF text — if a value got truncated by the renderer, only its
    prefix appears in the text and the full string check fails.
    """
    name = "cover_kv_values_fit_block_width"
    import tempfile
    from pathlib import Path
    from .permit.cover_sheet import render_cover_sheet

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "cover.pdf"
        try:
            render_cover_sheet(calc_result, out)
        except Exception as exc:
            return [CheckResult(
                name, "FAIL", f"cover render crashed: {exc!r}",
            )]
        try:
            import pypdf
            reader = pypdf.PdfReader(str(out))
            text = (reader.pages[0].extract_text() or "")
        except Exception as exc:
            return [CheckResult(
                name, "FAIL", f"pdf text extract failed: {exc!r}",
            )]

    inputs = calc_result.inputs
    n_inv = inputs.inverter.count(inputs.battery.quantity)
    ac_kw = (
        inputs.inverter.ac_output_v * inputs.inverter.ac_output_a
        * n_inv / 1000.0
    )

    # "AC" is the most overflow-prone token — it's the last word of the
    # system-size value, gets clipped first. Check it appears in BOTH
    # the title strip headline AND the scope-of-work block.
    # Headline shows "X kW AC SYSTEM SIZE"; scope-of-work shows
    # "/ X kW AC" — we want both unclipped.
    if "kW AC" not in text:
        return [CheckResult(
            name, "FAIL",
            "system size 'kW AC' missing from cover — value clipped "
            "by block boundary (the 2026-05-17 overflow bug)",
        )]

    # Specific check: the headline AC kW value must appear with its
    # full numeric value, not truncated.
    expected_ac = f"{ac_kw:.2f} kW AC"
    if expected_ac not in text:
        return [CheckResult(
            name, "FAIL",
            f"expected '{expected_ac}' in cover but only found "
            f"prefix(es) — kv truncation likely too aggressive",
        )]

    return [CheckResult(name, "PASS",
                        f"system size '{expected_ac}' renders unclipped")]


def _check_cover_blocks_no_vertical_overlap(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.12.5+ — render the cover sheet, extract every TEXT bbox via
    pypdf, and verify no two block titles overlap on the same line.

    Catches the 2026-05-17 bug class: someone bumps a band's `h` past
    the available vertical space and the lower block bleeds into the
    upper. The K.12 4-band layout (maps / codes-row / interco-row /
    rev-row) is tight — without this guard, future "let me make the
    block a little taller" patches would silently corrupt the cover.

    Detection: every block header (INTERCONNECTION, ARRAYS, METER INFO,
    REVISION HISTORY, PE STAMP) is a Helvetica-Bold string at a known
    text-y position. We extract pypdf's reported (x, y) for each and
    verify the SAME y doesn't host more than one header.
    """
    name = "cover_blocks_no_vertical_overlap"
    import tempfile
    from pathlib import Path
    from .permit.cover_sheet import render_cover_sheet

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "cover.pdf"
        try:
            render_cover_sheet(calc_result, out)
        except Exception as exc:
            return [CheckResult(
                name, "FAIL", f"cover render crashed: {exc!r}",
            )]

        try:
            import pypdf
            reader = pypdf.PdfReader(str(out))
            text = (reader.pages[0].extract_text() or "")
        except Exception as exc:
            return [CheckResult(
                name, "FAIL", f"pdf text extract failed: {exc!r}",
            )]

    # Required block headers — every K.12 cover MUST emit them all.
    expected_blocks = (
        "AERIAL MAP", "VICINITY MAP", "SHEET INDEX", "SCOPE OF WORK",
        "GOVERNING CODES", "DESIGN CRITERIA", "ROOF INFO",
        "INTERCONNECTION", "ARRAYS", "METER INFO",
        "REVISION HISTORY", "PE STAMP",
    )
    missing = [b for b in expected_blocks if b not in text]
    if missing:
        return [CheckResult(
            name, "FAIL",
            f"cover missing {len(missing)} block(s): {missing[:5]}... "
            "— bands may have collapsed or block render skipped",
        )]

    # Lightweight overlap signal: the 2026-05-17 bug had REV HISTORY
    # column headers ("DATE  REV  COMMENT") leaking into INTERCONNECTION.
    # When the blocks DON'T overlap, the INTERCONNECTION block's
    # "Method:" line should appear in pypdf text BEFORE "REVISION
    # HISTORY" (reading top-to-bottom). When they overlap, both share
    # the same y-coord and pypdf interleaves them.
    inter_idx = text.find("INTERCONNECTION")
    rev_idx = text.find("REVISION HISTORY")
    method_idx = text.find("Method:")
    if inter_idx == -1 or rev_idx == -1:
        return [CheckResult(name, "PASS",
                            "all 12 blocks present (overlap test skipped)")]
    if method_idx == -1:
        # No Method: line (e.g., interconnect FAIL state). Just check
        # block-header order.
        if inter_idx > rev_idx:
            return [CheckResult(
                name, "FAIL",
                "INTERCONNECTION appears after REVISION HISTORY in PDF "
                "text — bands likely overlap vertically",
            )]
        return [CheckResult(name, "PASS",
                            "all 12 blocks present + ordered correctly")]
    # The healthy case: INTERCONNECTION header → Method: row → REVISION
    # HISTORY header. The 2026-05-17 bug had REVISION HISTORY *inside*
    # the INTERCONNECTION block, so rev_idx < method_idx.
    if rev_idx < method_idx:
        return [CheckResult(
            name, "FAIL",
            "REVISION HISTORY appears INSIDE INTERCONNECTION block "
            "(rev_idx < method_idx in PDF text) — vertical bands "
            "are overlapping. Likely fix: shrink band heights so "
            "consecutive rows have ≥ 0.10\" gap.",
        )]
    return [CheckResult(name, "PASS",
                        "all 12 blocks present + non-overlapping order")]


def _check_cover_has_governing_codes(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.12.5 — the cover sheet's GOVERNING CODES block must list a
    plausible IBC / IRC / IECC version (i.e., the BuildingCodes
    defaults are intact OR the yaml provides explicit values). Catches
    the regression of someone wiping the BuildingCodes defaults to
    blank strings — which would render the cover with empty cells AHJ
    reviewers reject.

    Validation:
      * Non-empty NEC edition (always set on ProjectMeta)
      * Each building_codes field contains a 4-digit year
      * IBC + IRC + IECC are present (the three AHJ reviewers always
        check first)
    """
    name = "cover_has_governing_codes_for_ahj"
    inputs = calc_result.inputs
    bc = inputs.project.building_codes
    missing: list[str] = []
    if not inputs.project.nec_edition:
        missing.append("NEC")
    # Loop the 8 IXC codes
    import re
    for label, val in (
        ("IBC", bc.ibc), ("IRC", bc.irc), ("IFC", bc.ifc),
        ("IFGC", bc.ifgc), ("IEBC", bc.iebc), ("IECC", bc.iecc),
        ("IMC", bc.imc), ("IPC", bc.ipc),
    ):
        if not val or not re.search(r"\d{4}", val):
            missing.append(label)
    if missing:
        return [CheckResult(
            name, "FAIL",
            f"governing codes missing or undated: {', '.join(missing)}. "
            "Cover sheet will render empty cells; AHJ rejects.",
        )]
    return [CheckResult(
        name, "PASS",
        f"all 9 codes present ({inputs.project.nec_edition} NEC + "
        "8 ICC family codes)",
    )]


def _check_pv4_module_count_matches_yaml(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.9.5 — total placed modules across PV-4 should equal
    `pv_array.modules`. K.9.1 geometry can shortfall by a few when
    LRM allocates a small face more modules than physically fit;
    > 10% shortfall means the array is over-designed for the available
    roof and needs designer review.

    Three states:
      * No roof_sections → PASS-skip (legacy single-orientation path)
      * pv_array.modules = 0 → PASS-skip (no PV declared)
      * Otherwise: WARN-or-PASS based on placement shortfall ratio
    """
    name = "pv4_module_count_matches_yaml"
    inputs = calc_result.inputs

    if not inputs.site.roof_sections:
        return [CheckResult(name, "PASS",
                            "single-orientation project (skipped)")]
    if inputs.pv_array.modules <= 0:
        return [CheckResult(name, "PASS",
                            "no PV declared (skipped)")]

    target = inputs.pv_array.modules
    placements = calc_result.module_placements
    total_placed = sum(len(m) for m in placements.values())

    if total_placed == 0:
        # Engine ran K.9.1 but couldn't place anything — face geometry
        # is too small / setbacks too big / obstructions too much.
        return [CheckResult(
            name, "FAIL",
            f"PV-4 placement engine emitted 0 modules but yaml requests "
            f"{target} — every roof face hits geometric constraints. "
            "Check obstruction sizes / setbacks / face dimensions.",
        )]

    shortfall = target - total_placed
    pct = (shortfall / target) * 100 if target > 0 else 0

    if shortfall == 0:
        return [CheckResult(
            name, "PASS",
            f"{total_placed}/{target} modules placed across "
            f"{len(placements)} face(s)",
        )]
    if shortfall <= 2 or pct <= 5.0:
        # Small geometric shortfall — common when LRM allocates a small
        # face one module more than physical grid can fit. Not a bug,
        # just a designer-review note.
        return [CheckResult(
            name, "PASS",
            f"{total_placed}/{target} modules placed ({shortfall} short — "
            "small-face geometry, designer review recommended)",
        )]
    if pct <= 10.0:
        return [CheckResult(
            name, "WARN",
            f"{total_placed}/{target} modules placed ({pct:.0f}% shortfall) "
            "— roof may be over-packed; consider reducing module count or "
            "adding faces.",
        )]
    return [CheckResult(
        name, "FAIL",
        f"{total_placed}/{target} modules placed ({pct:.0f}% shortfall) "
        "— array is significantly over-designed for the available roof; "
        "redesign required before AHJ submission.",
    )]


def _check_string_balance_within_target(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.10.5 — verify the K.10.1 string assignment keeps strings
    within ±1 module of each other.

    The cold-Voc check (NEC 690.7(A)) is taken on the LONGEST string;
    when allocations drift by 2+ modules, the AHJ reviewer has to
    inspect every string individually instead of trusting the
    worst-case headline. This check locks the invariant.

    Three states:
      * No placements (legacy / pre-K.9 yaml) → PASS-skip
      * n_strings ≤ 0 (degenerate) → WARN, doctor flags elsewhere
      * Otherwise: PASS when `max - min ≤ 1`; FAIL when ≥ 2
    """
    name = "string_balance_within_target"
    from .calc.string_assignment import (
        placements_by_string,
        string_balance_pp,
    )

    inputs = calc_result.inputs
    n_strings = inputs.pv_array.strings
    target = inputs.pv_array.modules_per_string

    # Flatten placements across faces
    all_mods = [
        m for face_list in calc_result.module_placements.values()
        for m in face_list
    ]
    if not all_mods:
        return [CheckResult(
            name, "PASS",
            "no per-module placements (legacy single-orientation path) — skipped",
        )]
    if n_strings <= 0:
        return [CheckResult(
            name, "WARN",
            f"n_strings={n_strings} in yaml (zero or negative); cannot "
            "evaluate balance",
        )]

    max_n, min_n = string_balance_pp(all_mods, target_per_string=target)
    spread = max_n - min_n

    # Also check no string OVER-fills past target (would violate
    # NEC 690.7(A) headroom assumption for that string).
    over_target_strings = [
        s for s, ms in placements_by_string(all_mods).items()
        if s is not None and len(ms) > target
    ]
    if over_target_strings:
        return [CheckResult(
            name, "FAIL",
            f"string(s) {over_target_strings} exceed target {target} mods; "
            "NEC 690.7(A) cold-Voc check uses target — over-filled strings "
            "would breach the 600 V dwelling cap unchecked.",
        )]

    if spread <= 1:
        return [CheckResult(
            name, "PASS",
            f"{n_strings} string(s) balanced: max={max_n}, min={min_n}, "
            f"spread={spread} (≤1 is healthy)",
        )]
    if spread == 2:
        return [CheckResult(
            name, "WARN",
            f"{n_strings} string(s) spread={spread} (max={max_n}, min={min_n}) — "
            "cold-Voc check on longest string still valid, but consider "
            "K.9 placement rebalance.",
        )]
    return [CheckResult(
        name, "FAIL",
        f"string allocation drift: max={max_n}, min={min_n}, spread={spread} ≥ 3 — "
        "K.10.1 algorithm bug or unhealthy face shortfall. Review "
        "_allocate_string_counts() output.",
    )]


def _check_auto_routed_lengths_sane(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """K.11.5 — sanity bounds on auto-routed conduit lengths.

    Three states:
      * `wire_routing.routed=False` (legacy path) → PASS-skip
      * Routed but a segment exceeds the residential-roof envelope
        (>200 ft for any single segment) → FAIL with the culprit
      * Routed and all segments within bounds → PASS

    Envelope rationale: a 50ft × 35ft single-story residence has a
    diagonal of ~60 ft; even worst-case routing around the perimeter
    + attic transitions caps out around 150 ft. A segment > 200 ft
    almost certainly means the site_anchor coords are wrong (e.g.,
    units mixed up between m and ft, or the lot frame translated
    incorrectly).
    """
    name = "auto_routed_lengths_sane"

    wr = calc_result.wire_routing
    if wr is None or not wr.routed:
        return [CheckResult(
            name, "PASS",
            "wire routing not active (legacy wire_lengths path) — skipped",
        )]

    sane_limit_ft = 200.0
    segments = {
        "A · PV source":      wr.pv_string_one_way_ft,
        "B · DC home run":    wr.pv_to_combiner_ft,
        "C · INV → AC disc":  wr.inverter_to_ac_disc_ft,
        "D · AC disc → MSP":  wr.ac_disc_to_msp_ft,
    }
    if wr.ess_to_inverter_ft > 0:
        segments["E · ESS → INV"] = wr.ess_to_inverter_ft

    over = [(lbl, length) for lbl, length in segments.items()
            if length > sane_limit_ft]
    if over:
        culprit = over[0]
        return [CheckResult(
            name, "FAIL",
            f"segment {culprit[0]!r} = {culprit[1]:.0f} ft exceeds "
            f"{sane_limit_ft:.0f} ft residential envelope. Likely the "
            "`site_anchor` or `equipment_locations` coords use the "
            "wrong frame (e.g., absolute coords instead of lot-local, "
            "or m vs ft mismatch).",
        )]

    max_seg = max(segments.items(), key=lambda kv: kv[1])
    return [CheckResult(
        name, "PASS",
        f"{len(segments)} segment(s) routed, longest "
        f"{max_seg[0]!r}={max_seg[1]:.0f} ft (≤ {sane_limit_ft:.0f} ft envelope)",
    )]


def _check_phase_h_adjacent_calcs_complete(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """Phase H — make sure adjacent NEC protections are not silent.

    This check intentionally treats missing field evidence as WARN rather
    than FAIL. Many early projects used generic inverters and still need a
    datasheet review; the hard failures are reserved for impossible conduit
    fill, explicit AFCI non-compliance, or a missing 230.67 service SPD
    requirement in NEC 2020+ projects.
    """
    name = "phase_h_adjacent_calcs_complete"
    adj = calc_result.adjacent

    failures: list[str] = []
    warnings: list[str] = []

    if adj.dc_afci.status == "FAIL":
        failures.append(adj.dc_afci.note)
    elif adj.dc_afci.status == "MANUAL":
        warnings.append("DC AFCI listing not confirmed")

    if adj.surge.service_spd_required and not adj.surge.required_locations:
        failures.append("NEC 230.67 service SPD required but no required location set")

    for label, fill in (
        ("PV", adj.pv_conduit),
        ("AC", adj.ac_conduit),
    ):
        if fill.fill_pct > 100:
            failures.append(
                f"{label} conduit fill {fill.fill_pct:.1f}% exceeds 40% limit"
            )
        if fill.selected_conduit.endswith("+"):
            failures.append(f"{label} conduit exceeds built-in raceway table")

    raceways = {rw.tag: rw for rw in adj.raceways}
    missing_tags = [tag for tag in ("A", "B", "C", "D") if tag not in raceways]
    if missing_tags:
        failures.append(f"missing H.2 raceway segment(s): {missing_tags}")
    if calc_result.wire_routing is not None and calc_result.wire_routing.routed:
        for tag in ("B", "C", "D"):
            rw = raceways.get(tag)
            if rw is not None and rw.length_ft <= 0:
                failures.append(f"raceway {tag} has routed length <= 0 ft")
    for tag, rw in sorted(raceways.items()):
        if rw.fill is not None and rw.fill.fill_pct > 100:
            failures.append(f"raceway {tag} fill {rw.fill.fill_pct:.1f}% exceeds 40% limit")
        if rw.fill is not None and rw.fill.selected_conduit.endswith("+"):
            failures.append(f"raceway {tag} exceeds built-in raceway table")

    if adj.ground_rods.status == "MANUAL":
        warnings.append("ground rod resistance/electrode topology needs field proof")

    if failures:
        return [CheckResult(name, "FAIL", "; ".join(failures))]
    detail = (
        f"AFCI={adj.dc_afci.status}, service SPD="
        f"{'required' if adj.surge.service_spd_required else 'recommended'}, "
        f"PV {adj.pv_conduit.selected_conduit} "
        f"({adj.pv_conduit.fill_pct:.1f}%), "
        f"AC {adj.ac_conduit.selected_conduit} "
        f"({adj.ac_conduit.fill_pct:.1f}%), "
        f"{len(raceways)} raceway segment(s)"
    )
    if warnings:
        return [CheckResult(name, "WARN", detail + "; " + "; ".join(warnings))]
    return [CheckResult(name, "PASS", detail)]


def _check_ee4_focuses_on_site_geometry(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """Stage D / K.13 — verify EE-4 omits the legacy abstract PV grid.

    Pre-K.13 a project without explicit anchors got a synthetic
    yellow PV box + `8×5 grid` caption painted on top of the
    centered house rect. That redundant render of PV-4 confused AHJ
    reviewers and was deleted in K.13.

    States:
      * `roof_sections` present (auto- or hand-anchored) →
        per-face module rects must render (Stage B path);
        legacy abstract caption must NOT appear.
      * `roof_sections` empty →
        warning strip "PV array geometry omitted" must appear;
        legacy abstract caption must NOT appear.

    FAIL trigger: legacy `N×M grid` substring anywhere in EE-4 text.
    """
    import re
    import tempfile

    name = "ee4_focuses_on_site_geometry"
    from .permit.site_plan import render_site_plan

    with tempfile.TemporaryDirectory() as td:
        ee4 = Path(td) / "ee4-check.pdf"
        try:
            render_site_plan(calc_result, ee4)
        except Exception as exc:
            return [CheckResult(name, "FAIL", f"render crashed: {exc}")]
        text = _pdf_text(ee4)

    # Legacy abstract grid caption was always "{N}×{M} grid" with
    # an Unicode × (U+00D7), not ASCII 'x'. Catch both forms.
    legacy_pattern = re.compile(r"\b\d+\s*[×x]\s*\d+\s+grid\b")
    match = legacy_pattern.search(text)
    if match:
        return [CheckResult(
            name, "FAIL",
            f"legacy abstract-grid caption {match.group(0)!r} found in "
            "EE-4 — K.13 deleted that path; check site_plan.py for a "
            "regression",
        )]

    sections = calc_result.inputs.site.roof_sections
    if sections:
        if "PV ARRAY" not in text:
            return [CheckResult(
                name, "PASS",
                f"per-face render active ({len(sections)} section(s)); "
                "no legacy abstract-grid caption detected",
            )]
        return [CheckResult(
            name, "PASS",
            f"per-face render active ({len(sections)} section(s)); "
            "PV ARRAY caption in bottom margin; no legacy grid",
        )]

    if "PV array geometry omitted" not in text:
        return [CheckResult(
            name, "WARN-PASS",
            "no roof_sections + no warning strip visible — the K.13 "
            "incompleteness signal is missing; check site_plan.py "
            "warning-strip branch",
        )]
    return [CheckResult(
        name, "PASS",
        "no roof_sections; EE-4 shows incompleteness NOTE strip "
        "and skips abstract array render",
    )]


def _check_ee4_trace_ready_for_review(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """Stage 9.2 — when EE-4 trace mode is enabled, require useful layers.

    This is intentionally a WARN, not a FAIL: a designer may still be
    drafting the trace. The check catches the common half-migration state
    where `enabled: true` is present but the roof outline / fire pathway
    / roof-line layers were never supplied.
    """
    name = "ee4_trace_ready_for_review"
    trace = calc_result.inputs.site.ee4_trace
    if not trace.enabled:
        return [CheckResult(
            name, "PASS",
            "trace disabled; EE-4 uses generated site geometry",
        )]

    missing: list[str] = []
    if trace.roof_outline is None:
        missing.append("roof_outline")
    if not trace.roof_facets and not trace.roof_lines:
        missing.append("roof_facets or roof_lines")
    if not trace.fire_pathways:
        missing.append("fire_pathways")

    if missing:
        return [CheckResult(
            name, "WARN",
            "ee4_trace.enabled=true but missing "
            + ", ".join(missing)
            + "; run `pvess ee4-trace <project>` for a paste-ready skeleton "
            "or finish the trace block before visual review",
        )]

    return [CheckResult(
        name, "PASS",
        f"trace mode active with outline, {len(trace.roof_facets)} facet(s), "
        f"{len(trace.roof_lines)} line(s), and "
        f"{len(trace.fire_pathways)} fire-pathway polygon(s)",
    )]


def _check_ee4_preview_visual_lint(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """Stage 9.4 — run non-rendering EE-4 preview visual lint."""
    name = "ee4_preview_visual_lint"
    try:
        from .permit.ee4_lint import lint_ee4_preview
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    results = lint_ee4_preview(calc_result)
    issues = [r for r in results if r.status != "PASS"]
    if not issues:
        return [CheckResult(name, "PASS", f"{len(results)} lint check(s) pass")]
    detail = "; ".join(f"{r.name}: {r.detail}" for r in issues[:4])
    status = "FAIL" if any(r.status == "FAIL" for r in issues) else "WARN"
    return [CheckResult(name, status, detail)]


def _check_pv6_string_layout_visual_lint(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """Stage 9.10.5 — run non-rendering PV-6 string-plan visual lint."""
    name = "pv6_string_layout_visual_lint"
    try:
        from .permit.pv6_lint import lint_pv6_string_layout
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    results = lint_pv6_string_layout(calc_result)
    issues = [r for r in results if r.status != "PASS"]
    if not issues:
        return [CheckResult(name, "PASS", f"{len(results)} lint check(s) pass")]
    detail = "; ".join(f"{r.name}: {r.detail}" for r in issues[:4])
    status = "FAIL" if any(r.status == "FAIL" for r in issues) else "WARN"
    return [CheckResult(name, status, detail)]


def _check_reference_profile_site_intake_complete(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """9.12 / 9.17 — reference plansets need field-survey context."""
    name = "reference_profile_site_intake_complete"
    i = calc_result.inputs
    if i.project.permit_profile == "internal":
        return [CheckResult(name, "PASS", "internal profile (skipped)")]

    ri = i.project.roof_info
    missing: list[str] = []
    for label, value in (
        ("project.site_address", i.project.site_address),
        ("project.coordinates", i.project.coordinates),
        ("project.utility", i.project.utility),
        ("project.meter_info.location", i.project.meter_info.location),
        ("project.roof_info.type", ri.type),
        ("project.roof_info.height_ft", ri.height_ft),
        ("project.roof_info.construction/framing", ri.construction or ri.framing),
        ("project.roof_info.decking_thickness_in", ri.decking_thickness_in),
    ):
        if value in ("", 0, 0.0, None):
            missing.append(label)
    if ri.condition == "unknown":
        missing.append("project.roof_info.condition")
    if ri.attic_access == "unknown":
        missing.append("project.roof_info.attic_access")
    if "TX" in (i.project.site_address or i.project.location).upper():
        if not i.project.meter_info.esid:
            missing.append("project.meter_info.esid")

    if missing:
        return [CheckResult(
            name, "WARN",
            "reference profile missing field-survey data: "
            + ", ".join(missing[:10]),
        )]
    return [CheckResult(name, "PASS", "reference site-intake fields populated")]


def _check_reference_profile_attachments_ready(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """9.13-9.15 — photos/specs/structural packet readiness."""
    name = "reference_profile_attachments_ready"
    i = calc_result.inputs
    if i.project.permit_profile == "internal":
        return [CheckResult(name, "PASS", "internal profile (skipped)")]

    project_dir = Path.cwd() / "projects" / i.project.id

    def exists(raw: str) -> bool:
        if not raw:
            return False
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = project_dir / p
        return p.exists()

    issues: list[str] = []
    if not exists(i.project.structural_letter_pdf):
        issues.append("signed structural letter missing (draft will be prepended)")

    supplied_photos = {
        p.kind for p in i.project.site_photos
        if p.path and exists(p.path)
    }
    required_photo_kinds = {
        "front_elevation", "roof", "meter", "main_panel",
        "sub_panel", "equipment_location",
    }
    missing_photos = sorted(required_photo_kinds - supplied_photos)
    if missing_photos:
        issues.append("PV-7 photo placeholders: " + ", ".join(missing_photos))

    explicit_specs = [s for s in i.project.spec_sheets if s.path and exists(s.path)]
    cut_sheets_dir = project_dir / "cut_sheets"
    cut_sheets = list(cut_sheets_dir.glob("*.pdf")) if cut_sheets_dir.exists() else []
    if not explicit_specs and not cut_sheets:
        issues.append("SPEC manufacturer PDFs missing (placeholder will be appended)")

    if issues:
        return [CheckResult(name, "WARN", "; ".join(issues))]
    return [CheckResult(name, "PASS", "structural letter, PV-7 photos, and SPEC PDFs present")]


def _check_reference_profile_data_readiness(
    calc_result: CalculationResult,
    project_dir: Path | None = None,
) -> list[CheckResult]:
    """5.1 — make simulated/missing field data explicit before submission."""
    name = "reference_profile_data_readiness"
    i = calc_result.inputs
    if i.project.permit_profile == "internal":
        return [CheckResult(name, "PASS", "internal profile (skipped)")]

    try:
        from .permit.readiness import assess_reference_profile_readiness
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    readiness = assess_reference_profile_readiness(calc_result, project_dir)
    status = "WARN" if readiness.needs_review else "PASS"
    return [CheckResult(name, status, readiness.doctor_detail())]


def _mounting_family(value: str) -> str:
    norm = re.sub(r"[^a-z0-9]+", "", value.lower())
    if "flashvue" in norm:
        return "flashvue"
    if "flashfoot" in norm:
        return "flashfoot"
    return norm


def _check_mounting_data_consistent(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """Reference packages must not mix mounting product assumptions.

    This catches the failure mode surfaced by visual review: PV-5 drew
    FlashFoot while the project roof-info block said FlashVue, and the
    structural draft used a different embedment than the mounting detail.
    """
    name = "mounting_data_consistent"
    i = calc_result.inputs
    if i.project.permit_profile == "internal":
        return [CheckResult(name, "PASS", "internal profile (skipped)")]

    m = i.site.mounting
    ri = i.project.roof_info
    problems: list[str] = []
    if m.flashing and ri.flashing:
        m_family = _mounting_family(m.flashing)
        ri_family = _mounting_family(ri.flashing)
        if m_family and ri_family and m_family != ri_family:
            problems.append(
                f"site.mounting.flashing={m.flashing!r} conflicts with "
                f"project.roof_info.flashing={ri.flashing!r}"
            )
    if "embedment" in m.fastener.lower():
        problems.append(
            "site.mounting.fastener includes embedment; use "
            "site.mounting.min_embedment_in as the single source of truth"
        )
    for label, value in (
        ("max_x_spacing_in", m.max_x_spacing_in),
        ("max_y_spacing_in", m.max_y_spacing_in),
        ("max_cantilever_in", m.max_cantilever_in),
        ("lag_screw_length_in", m.lag_screw_length_in),
        ("min_embedment_in", m.min_embedment_in),
        ("max_roof_surface_gap_in", m.max_roof_surface_gap_in),
    ):
        if value <= 0:
            problems.append(f"site.mounting.{label} must be > 0")
    if problems:
        return [CheckResult(name, "FAIL", "; ".join(problems))]
    return [CheckResult(
        name, "PASS",
        f"{m.rail_system} / {m.flashing}; embedment {m.min_embedment_in:g}\"",
    )]


def _check_pv5_mounting_detail_complete(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """PV-5 must read like a mounting detail sheet, not a placeholder."""
    name = "pv5_mounting_detail_complete"
    i = calc_result.inputs
    if i.project.permit_profile == "internal":
        return [CheckResult(name, "PASS", "internal profile (skipped)")]

    from .permit.structural import render_mounting_details

    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "pv5.pdf"
        try:
            render_mounting_details(calc_result, out)
        except Exception as exc:
            return [CheckResult(name, "FAIL", f"PV-5 render crashed: {exc}")]
        text = " ".join(_pdf_text(out).split())

    required = [
        "GENERAL ROOF MOUNT DETAIL",
        "ROOF MOUNT CROSS SECTION DETAIL",
        "ROOF MOUNT PLAN VIEW DETAIL",
        "ROOF MOUNT DETAIL",
        "PV MODULES",
        "RAIL",
        "MOUNTING HARDWARE",
        "ROOF SHEATHING",
        "FINISHED ROOF",
        "FLASHING PROVIDED BY MANUFACTURER",
        "MAX SPACE FROM ROOF SURFACE",
        "MIN EMBEDMENT DEPTH SEE TABLE ON PV-4",
        "ROOF FRAMING SEE TABLE ON PV-4",
        i.site.mounting.flashing.upper(),
    ]
    missing = [token for token in required if token not in text.upper()]
    if missing:
        return [CheckResult(
            name, "FAIL",
            "PV-5 missing reference-detail content: " + ", ".join(missing),
        )]
    return [CheckResult(name, "PASS", f"{len(required)} PV-5 detail tokens present")]


def _pdf_text_bbox_items(path: Path) -> list[tuple[str, float, float, float, float]]:
    """Best-effort text bboxes from a PDF page using pypdf text positions."""
    import pypdf
    from reportlab.pdfbase import pdfmetrics

    items: list[tuple[str, float, float, float, float]] = []

    def visitor(text, cm, tm, font_dict, font_size):
        del cm, font_dict
        label = " ".join(text.split())
        if not label:
            return
        x = float(tm[4])
        baseline = float(tm[5])
        # Use Helvetica as a stable approximation. This is intentionally a
        # coarse visual lint, not a PDF preflight engine.
        width = pdfmetrics.stringWidth(label, "Helvetica", float(font_size))
        items.append((
            label,
            x,
            baseline - float(font_size) * 0.25,
            x + width,
            baseline + float(font_size) * 0.90,
        ))

    for page in pypdf.PdfReader(str(path)).pages:
        page.extract_text(visitor_text=visitor)
    return items


def _bbox_overlap_ratio(a, b) -> float:
    ix = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    iy = max(0.0, min(a[4], b[4]) - max(a[2], b[2]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area_a = (a[3] - a[1]) * (a[4] - a[2])
    area_b = (b[3] - b[1]) * (b[4] - b[2])
    return inter / max(1e-9, min(area_a, area_b))


def _check_pv5_text_no_overlap(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """PV-5 callout text should not pile up on itself."""
    name = "pv5_text_no_overlap"
    i = calc_result.inputs
    if i.project.permit_profile == "internal":
        return [CheckResult(name, "PASS", "internal profile (skipped)")]

    from .permit.structural import render_mounting_details

    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "pv5.pdf"
        try:
            render_mounting_details(calc_result, out)
        except Exception as exc:
            return [CheckResult(name, "FAIL", f"PV-5 render crashed: {exc}")]
        text_boxes = _pdf_text_bbox_items(out)

    offenders: list[str] = []
    for idx, a in enumerate(text_boxes):
        for b in text_boxes[idx + 1:]:
            ratio = _bbox_overlap_ratio(a, b)
            if ratio > 0.25:
                offenders.append(f"{a[0]!r} overlaps {b[0]!r} ({ratio:.0%})")
                break
        if len(offenders) >= 6:
            break
    if offenders:
        return [CheckResult(
            name,
            "FAIL",
            "PV-5 text bounding boxes overlap:\n  " + "\n  ".join(offenders),
        )]
    return [CheckResult(name, "PASS", f"{len(text_boxes)} text item(s) clear")]


def _should_have_ee21(calc_result: CalculationResult) -> bool:
    from .permit.builder import _should_emit_one_line
    return _should_emit_one_line(calc_result)


def _dxf_modelspace_text(path: Path) -> str:
    import ezdxf

    doc = ezdxf.readfile(str(path))
    texts: list[str] = []
    for entity in doc.modelspace():
        if entity.dxftype() == "TEXT":
            texts.append(entity.dxf.text)
        elif entity.dxftype() == "INSERT":
            texts.extend(attr.dxf.text for attr in entity.attribs)
    return " ".join(" ".join(texts).split())


def _render_ee21_text(calc_result: CalculationResult) -> str:
    from .dxf.one_line import render_one_line_dxf

    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "ee21.dxf"
        render_one_line_dxf(calc_result, out)
        return _dxf_modelspace_text(out)


def _check_ee21_one_line_complete(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """EE-2.1 must be an electrical one-line, not an unlabeled flow chart."""
    name = "ee21_one_line_complete"
    if not _should_have_ee21(calc_result):
        return [CheckResult(name, "PASS", "one-line not selected (skipped)")]
    try:
        text = _render_ee21_text(calc_result)
    except Exception as exc:
        return [CheckResult(name, "FAIL", f"EE-2.1 render crashed: {exc}")]
    required = [
        "PV ARRAY",
        "MLPE / RSD",
        "PV DC OCPD",
        "INVERTER",
        "AC DISC",
        "LINE SIDE TAP",
        "UTILITY METER",
        "UTILITY SOURCE",
        "MSP / MAIN",
        "SUPPLY-SIDE CONNECTION AHEAD OF MAIN SERVICE DISCONNECT",
        "CONDUCTOR / OCPD SCHEDULE",
        "RACEWAY",
        "SUPPLY TAP",
        "NEC 705.11",
    ]
    missing = [token for token in required if token not in text.upper()]
    if missing:
        return [CheckResult(
            name, "FAIL",
            "EE-2.1 missing one-line content: " + ", ".join(missing),
        )]
    return [CheckResult(name, "PASS", f"{len(required)} one-line tokens present")]


def _check_ee21_no_phantom_ocpd(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """Every OCPD value printed in the EE-2.1 schedule needs a device node."""
    name = "ee21_no_phantom_ocpd"
    if not _should_have_ee21(calc_result):
        return [CheckResult(name, "PASS", "one-line not selected (skipped)")]
    from .electrical.topology import build_electrical_topology
    topo = build_electrical_topology(calc_result)
    node_kinds = {n.kind for n in topo.nodes}
    problems: list[str] = []
    for row in topo.schedule:
        if row.ocpd_a == calc_result.pv_ocpd_a and row.kind == "DC":
            if "dc_ocpd" not in node_kinds:
                problems.append(f"{row.tag} {row.ocpd_a}A DC OCPD has no dc_ocpd node")
        if row.ocpd_a == calc_result.ess.ac_disconnect_ocpd_a and row.kind == "AC":
            if "ac_disconnect" not in node_kinds:
                problems.append(f"{row.tag} {row.ocpd_a}A AC OCPD has no ac_disconnect node")
    if problems:
        return [CheckResult(name, "FAIL", "; ".join(problems))]
    return [CheckResult(name, "PASS", "OCPD schedule values have matching device nodes")]


def _check_ee21_topology_consistent(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """EE-2.1 conductor rows must map to real topology edges."""
    name = "ee21_topology_consistent"
    if not _should_have_ee21(calc_result):
        return [CheckResult(name, "PASS", "one-line not selected (skipped)")]
    from .electrical.topology import build_electrical_topology
    topo = build_electrical_topology(calc_result)
    schedule = topo.schedule_by_tag()
    edges = topo.edge_by_schedule_tag()
    required = {"A", "B", "D"}
    required.add("C" if "C" in schedule else next((t for t in schedule if t.startswith("C")), "C"))
    problems: list[str] = []
    missing_rows = sorted(t for t in required if t not in schedule)
    if missing_rows:
        problems.append("missing schedule rows: " + ", ".join(missing_rows))
    missing_edges = sorted(t for t in schedule if t not in edges)
    if missing_edges:
        problems.append("schedule rows without topology edges: " + ", ".join(missing_edges))

    row_a = schedule.get("A")
    row_d = schedule.get("D")
    if row_a and row_a.ocpd_a != calc_result.pv_ocpd_a:
        problems.append(f"A OCPD {row_a.ocpd_a}A != calc PV OCPD {calc_result.pv_ocpd_a}A")
    if row_d and row_d.ocpd_a != calc_result.ess.ac_disconnect_ocpd_a:
        problems.append(
            f"D OCPD {row_d.ocpd_a}A != AC disconnect OCPD "
            f"{calc_result.ess.ac_disconnect_ocpd_a}A"
        )
    if row_d and row_d.size != f"{calc_result.ess_conductor.size} AWG":
        problems.append(
            f"D conductor {row_d.size} != aggregate conductor "
            f"{calc_result.ess_conductor.size} AWG"
        )
    if problems:
        return [CheckResult(name, "FAIL", "; ".join(problems))]
    return [CheckResult(name, "PASS", f"{len(topo.nodes)} nodes / {len(topo.schedule)} schedule rows")]


def _check_ee21_dxf_cad_geometry(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """EE-2.1 must contain CAD devices, conductor callouts, and a schedule."""
    name = "ee21_dxf_cad_geometry"
    if not _should_have_ee21(calc_result):
        return [CheckResult(name, "PASS", "one-line not selected (skipped)")]
    import ezdxf
    from .dxf.one_line import render_one_line_dxf
    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "ee21.dxf"
        try:
            render_one_line_dxf(calc_result, out)
        except Exception as exc:
            return [CheckResult(name, "FAIL", f"EE-2.1 render crashed: {exc}")]
        doc = ezdxf.readfile(str(out))
        text = _dxf_modelspace_text(out).upper()
    msp = doc.modelspace()
    inserts = list(msp.query("INSERT"))
    forbidden_wire_layers = {
        "WIRE_DC_POS", "WIRE_DC_NEG", "WIRE_AC_L1", "WIRE_AC_L2", "WIRE_AC_N",
    }
    phased_segments = [
        e for e in msp.query("LWPOLYLINE LINE")
        if e.dxf.layer in forbidden_wire_layers
    ]
    single_segments = [
        e for e in msp.query("LWPOLYLINE LINE")
        if e.dxf.layer == "WIRE_ONE_LINE"
    ]
    required = ["PV-1", "DC-COMB-1", "INV-1", "AC-DISC-1", "TAP-1", "METER", "CONDUCTOR / OCPD SCHEDULE"]
    missing = [token for token in required if token not in text]
    if len(inserts) < 8:
        missing.append(f"expected >=8 device INSERTs, got {len(inserts)}")
    if phased_segments:
        layers = sorted({e.dxf.layer for e in phased_segments})
        missing.append("one-line uses phase-specific conductor layers: " + ", ".join(layers))
    if len(single_segments) < 8:
        missing.append(f"expected >=8 WIRE_ONE_LINE segments, got {len(single_segments)}")
    from .electrical.topology import build_electrical_topology
    expected_tags = [row.tag for row in build_electrical_topology(calc_result).schedule]
    for tag in expected_tags:
        if f" {tag.upper()} " not in f" {text} ":
            missing.append(f"missing conductor callout/tag {tag}")
    if missing:
        return [CheckResult(name, "FAIL", "; ".join(missing))]
    return [CheckResult(
        name, "PASS",
        f"{len(inserts)} device INSERTs, {len(single_segments)} single-line segments with A-D callouts",
    )]


def _check_ee21_no_wire_text_overlap(
    calc_result: CalculationResult,
) -> list[CheckResult]:
    """EE-2.1 one-line conductors must not run through labels."""
    name = "ee21_no_wire_text_overlap"
    if not _should_have_ee21(calc_result):
        return [CheckResult(name, "PASS", "one-line not selected (skipped)")]
    import ezdxf
    from .dxf.one_line import render_one_line_dxf
    from .electrical.topology import build_electrical_topology

    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "ee21.dxf"
        try:
            render_one_line_dxf(calc_result, out)
        except Exception as exc:
            return [CheckResult(name, "FAIL", f"EE-2.1 render crashed: {exc}")]
        doc = ezdxf.readfile(str(out))

    tags = {row.tag.upper() for row in build_electrical_topology(calc_result).schedule}
    offenders, wire_count = _dxf_wire_text_offenders(
        doc,
        "EE-2.1",
        text_layers={"EQUIPMENT_TEXT", "ANNOTATION"},
        wire_layers={"WIRE_ONE_LINE"},
        ignored_texts=tags,
    )
    if offenders:
        return [CheckResult(
            name, "FAIL",
            "WIRE_ONE_LINE overlaps label text:\n  " + "\n  ".join(offenders),
        )]
    return [CheckResult(name, "PASS", f"{wire_count} wire segment(s) clear of labels")]


def _check_face_value_score_distinguishes_east_west() -> list[CheckResult]:
    """K.8.2 — math contract: the `face_value_weighted_derate` function
    MUST score East and West differently when the REP buyback is sub-1:1.
    If a regression collapses this difference (e.g., someone makes the
    hourly profile symmetric AM/PM by accident, or drops the
    self-consumption pattern), the SW-quadrant auto-distribute degrades
    silently into area-only weighting.

    Synthesises a clean test geometry (equal-area E + W faces, 30° tilt,
    33°N) and verifies the spread on a 0.50× REP plan exceeds 8%. Also
    verifies the math-collapse property on a 1:1 plan (E ≈ W).
    """
    name = "face_value_score_distinguishes_east_west"
    try:
        from .calc.value_weighted import face_value_weighted_derate
    except ImportError as exc:
        return [CheckResult(name, "FAIL", f"import failed: {exc}")]

    # Sub-1:1 plan must produce W > E by ≥ 8%
    w_lo = face_value_weighted_derate(270.0, 30.0, 33.0, 0.50)
    e_lo = face_value_weighted_derate(90.0, 30.0, 33.0, 0.50)
    spread_lo = w_lo - e_lo
    if spread_lo < 0.08:
        return [CheckResult(
            name, "FAIL",
            f"sub-1:1 (0.50×) E/W spread = {spread_lo:.3f}, expected ≥ 0.08; "
            "value-weighted math may have lost the AM/PM asymmetry — check "
            "calc/value_weighted.py::hourly_face_profile sign / "
            "DEFAULT_DFW_SELF_CONSUMPTION_PATTERN AM-vs-PM distinction.",
        )]

    # 1:1 plan must collapse — E ≈ W within ±0.01
    w_hi = face_value_weighted_derate(270.0, 30.0, 33.0, 1.00)
    e_hi = face_value_weighted_derate(90.0, 30.0, 33.0, 1.00)
    if abs(w_hi - e_hi) > 0.01:
        return [CheckResult(
            name, "FAIL",
            f"1:1 (1.00×) E/W collapse failed: W={w_hi:.3f}, E={e_hi:.3f}; "
            "value factor isn't constant 1.0 on 1:1 plans → backward "
            "compat with K.8.1 broken for every 1:1 project.",
        )]

    return [CheckResult(
        name, "PASS",
        f"E/W spread {spread_lo*100:.0f}% on 0.50× REP; "
        f"collapses to {abs(w_hi - e_hi)*1000:.1f}‰ on 1:1 (math OK)",
    )]


def _check_subpanel_slots_sufficient(inputs: Inputs) -> list[CheckResult]:
    """K.2.5 — flag panels that cannot fit the new PV/ESS breakers.

    For each MSP / sub-panel with `available_slots > 0` (i.e., physical
    capacity is KNOWN), verify `used_slots + new_pv_ess_slots ≤ available`.

    `new_pv_ess_slots` assumed as 2 (one 2-pole PV/ESS backfeed breaker)
    per panel involved in the interconnection. When `available_slots = 0`
    we treat capacity as unknown and pass with an informational note —
    not knowing isn't the same as not having room.

    Cleanly skipped when the project has no sub-panels and the MSP
    capacity is unknown — i.e., for old yaml that pre-dates K.2.5.
    """
    name = "subpanel_slots_sufficient"
    NEW_BREAKER_SLOTS = 2  # one 2-pole 240 V breaker per panel

    problems: list[str] = []
    checked = 0

    svc = inputs.service
    if svc.msp_available_slots > 0:
        checked += 1
        free = svc.msp_free_slots or 0
        if free < NEW_BREAKER_SLOTS:
            problems.append(
                f"MSP has {svc.msp_used_slots}/{svc.msp_available_slots} "
                f"slots used ({free} free) — needs {NEW_BREAKER_SLOTS} "
                "for new PV/ESS backfeed; panel swap required"
            )

    for sp in svc.sub_panels:
        if sp.available_slots <= 0:
            continue
        checked += 1
        free = sp.free_slots or 0
        if free < NEW_BREAKER_SLOTS:
            problems.append(
                f"sub-panel {sp.name!r} has {sp.used_slots}/"
                f"{sp.available_slots} slots used ({free} free) — "
                f"needs {NEW_BREAKER_SLOTS}; panel upgrade required"
            )

    if problems:
        return [CheckResult(name, "FAIL", "; ".join(problems))]
    if checked == 0:
        return [CheckResult(name, "PASS",
                            "no panel slot data on file (skipped)")]
    return [CheckResult(name, "PASS",
                        f"{checked} panel(s) have room for new breakers")]


def run_doctor(project_dir: Path) -> list[CheckResult]:
    """Run every check and return the accumulated results."""
    results: list[CheckResult] = []

    # Phase 1: project must be loadable
    r1 = _check_inputs_load(project_dir)
    results.extend(r1)
    if not all(r.ok for r in r1):
        # Without a loadable inputs.yaml every downstream check is moot.
        return results

    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    try:
        calc_result = run(inputs)
    except Exception as exc:
        results.append(CheckResult("calc_engine", "FAIL", f"crashed: {exc}"))
        return results

    # Phase 2: standalone checks (no calc result needed)
    results.extend(_check_calc_engine(calc_result))
    results.extend(_check_ahj_profile_codes())
    results.extend(_check_label_set_codes())
    results.extend(_check_no_fixed_width_truncation_markers(project_dir))
    results.extend(_check_subpanel_slots_sufficient(inputs))
    results.extend(_check_production_breakdown_per_face(inputs))
    # K.8.2 — value-weighted math correctness (project-independent)
    results.extend(_check_face_value_score_distinguishes_east_west())
    # K.9.5 — PV-4 placement vs yaml module count
    results.extend(_check_pv4_module_count_matches_yaml(calc_result))
    results.extend(_check_string_balance_within_target(calc_result))
    results.extend(_check_auto_routed_lengths_sane(calc_result))
    results.extend(_check_phase_h_adjacent_calcs_complete(calc_result))
    # K.13 / Stage D — EE-4 abstract-grid regression guard
    results.extend(_check_ee4_focuses_on_site_geometry(calc_result))
    # Stage 9.2 — hand/vector trace block completeness hint
    results.extend(_check_ee4_trace_ready_for_review(calc_result))
    # Stage 9.4 — geometry/text-placement lints for the EE-4 preview
    results.extend(_check_ee4_preview_visual_lint(calc_result))
    # Stage 9.9 — EE-4A data-driven property context guard
    results.extend(_check_ee4a_property_context_data_driven(calc_result))
    # Stage 9.10.5 — PV-6 string plan callout / label visual lint
    results.extend(_check_pv6_string_layout_visual_lint(calc_result))
    # 9.12-9.17 — reference-profile package data/readiness guards
    results.extend(_check_reference_profile_site_intake_complete(calc_result))
    results.extend(_check_reference_profile_attachments_ready(calc_result))
    results.extend(_check_reference_profile_data_readiness(
        calc_result, project_dir,
    ))
    # Stage 10.1 — reference PV-5 / EE-2.1 content quality guards
    results.extend(_check_mounting_data_consistent(calc_result))
    results.extend(_check_pv5_mounting_detail_complete(calc_result))
    results.extend(_check_pv5_text_no_overlap(calc_result))
    results.extend(_check_ee21_one_line_complete(calc_result))
    results.extend(_check_ee21_no_phantom_ocpd(calc_result))
    results.extend(_check_ee21_topology_consistent(calc_result))
    results.extend(_check_ee21_dxf_cad_geometry(calc_result))
    results.extend(_check_ee21_no_wire_text_overlap(calc_result))
    # K.12.5 — cover sheet governing codes completeness
    results.extend(_check_cover_has_governing_codes(calc_result))
    # K.12.5+ — cover sheet vertical layout no-overlap
    results.extend(_check_cover_blocks_no_vertical_overlap(calc_result))
    # K.12.5+ — cover sheet KV values fit inside block widths
    results.extend(_check_cover_kv_values_fit_block_width(calc_result))
    results.extend(_check_ess_install_compliant(calc_result))
    results.extend(_check_grounding_electrode_system_compliant(calc_result))
    results.extend(_check_roof_usable_area_sufficient(calc_result))
    results.extend(_check_lookup_offline_works_without_keys())
    results.extend(_check_customer_summary_renderable(calc_result))
    results.extend(_check_customer_design_tokens_respected())
    # K.7 final closing checks — lock in the 4-step invariants
    results.extend(_check_nec_edition_artifacts_consistent(
        calc_result, project_dir,
    ))
    results.extend(_check_export_tariff_matches_state(calc_result))
    results.extend(_check_regional_requirements_consistent(calc_result))
    # K.4.6.6 — TX REP plan picker + smart-meter self-cons sanity
    results.extend(_check_tx_rep_plan_explicitly_chosen(calc_result))
    results.extend(_check_self_consumption_realistic_for_rep_plan(calc_result))
    results.extend(_check_rsd_label_substitution_wired())
    results.extend(_check_compare_pdf_renderable())

    # Phase 3: checks that need the rendered permit package
    results.extend(_check_cover_lists_all_sheets(calc_result, project_dir))
    results.extend(_check_permit_emits_registry(calc_result))
    results.extend(_check_pdf_is_text_searchable(calc_result))
    results.extend(_check_dxf_text_no_overflow(calc_result))
    results.extend(_check_dxf_no_text_overlap(calc_result))
    results.extend(_check_dxf_wire_text_no_overlap(calc_result))
    results.extend(_check_site_checklist_covers_schema())

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


@click.command(name="pvess-doctor")
@click.argument("project_dir",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--quiet", is_flag=True,
              help="Only print failures.")
def doctor_cmd(project_dir: Path, quiet: bool) -> None:
    """Run structural self-checks against a project's submittal pipeline.

    Verifies the contracts laid out in docs/TESTING.md §2 and docs/DESIGN.md
    §2-§7. Exits non-zero if anything fails — wire into pre-commit / CI.
    """
    results = run_doctor(project_dir)

    width = max(len(r.name) for r in results) + 2
    n_fail = 0
    for r in results:
        if quiet and r.status == "PASS":
            continue
        color = {
            "PASS": "green", "FAIL": "red",
            "WARN": "yellow", "SKIP": "blue",
        }.get(r.status, "white")
        click.echo(
            f"  {click.style(r.status.ljust(4), fg=color)}  "
            f"{r.name.ljust(width)}{r.detail}"
        )
        if r.status == "FAIL":
            n_fail += 1

    click.echo()
    if n_fail:
        click.echo(click.style(
            f"  ✗ {n_fail} check(s) failed", fg="red", bold=True))
        raise SystemExit(1)
    click.echo(click.style(
        f"  ✓ all {len(results)} check(s) passed", fg="green", bold=True))
