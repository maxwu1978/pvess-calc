"""Single source of truth for every sheet emitted by the permit pipeline.

DESIGN.md §2: cover index, builder pipeline, and AHJ profile validation all
read from this list. Adding a sheet = one entry here; the doctor verifies the
three readers stay consistent.

Each entry is intentionally a pure data class with no rendering imports, so
this module can be loaded by the doctor / tests without dragging in reportlab
or matplotlib. Renderers are referenced by dotted-path string and resolved
lazily.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SheetSpec:
    """One sheet in the permit submittal package.

    code:        AHJ-facing identifier (also used by AHJ profile
                 `required_sheets`) — lowercase, hyphenated.
    display:     SHEET INDEX block on the cover page uses this verbatim.
                 First column = `display_code`, second column = `title`.
    title:       Long-form title that also appears as the sheet header.
    renderer:    Dotted path "module:callable" — resolved lazily so this
                 module has no rendering dependencies.
    output_kind: "pdf" for native reportlab pages, "dxf" for DXF rendered to
                 PDF via the matplotlib backend, "labels" for the existing
                 labels.pdf reuse path. The builder dispatches on this.
    """
    code: str
    display_code: str
    title: str
    renderer: str
    output_kind: str = "pdf"


# Order here is the order pages appear in the permit PDF when an AHJ does
# not override. Changing the order changes the page sequence; that's by design.
SHEET_REGISTRY: tuple[SheetSpec, ...] = (
    SheetSpec(
        code="cover",
        display_code="EE-0",
        title="Cover Sheet",
        renderer="pvess_calc.permit.cover_sheet:render_cover_sheet",
        output_kind="pdf",
    ),
    SheetSpec(
        code="ee-1",
        display_code="EE-1",
        title="Three-Line Diagram",
        renderer="pvess_calc.dxf.render:render_dxf",
        output_kind="dxf",
    ),
    SheetSpec(
        code="ee-2",
        display_code="EE-2",
        title="Grounding & Bonding",
        renderer="pvess_calc.dxf.grounding_sheet:render_grounding_dxf",
        output_kind="dxf",
    ),
    SheetSpec(
        code="ee-3",
        display_code="EE-3",
        title="Panel Schedules",
        renderer="pvess_calc.permit.panel_schedule:render_panel_schedule",
        output_kind="pdf",
    ),
    SheetSpec(
        code="ee-4",
        display_code="EE-4",
        title="Site Plan",
        renderer="pvess_calc.permit.site_plan:render_site_plan",
        output_kind="pdf",
    ),
    SheetSpec(
        code="ee-4a",
        display_code="EE-4A",
        title="Property Context Plan",
        renderer="pvess_calc.permit.property_context:render_property_context_plan",
        output_kind="pdf",
    ),
    SheetSpec(
        code="pv-4",
        display_code="PV-4",
        title="Attachment Plan",
        renderer="pvess_calc.permit.structural:render_attachment_plan",
        output_kind="pdf",
    ),
    SheetSpec(
        code="pv-5",
        display_code="PV-5",
        title="Mounting Details",
        renderer="pvess_calc.permit.structural:render_mounting_details",
        output_kind="pdf",
    ),
    SheetSpec(
        code="pv-6",
        display_code="PV-6",
        title="String Layout Plan",
        renderer="pvess_calc.permit.structural:render_string_plan",
        output_kind="pdf",
    ),
    SheetSpec(
        code="ee-5",
        display_code="EE-5",
        title="NEC Compliance Checklist",
        renderer="pvess_calc.permit.compliance:render_compliance_checklist",
        output_kind="pdf",
    ),
    SheetSpec(
        code="notes",
        display_code="PV-N",
        title="General Notes",
        renderer="pvess_calc.permit.general_notes:render_general_notes",
        output_kind="pdf",
    ),
    SheetSpec(
        code="labels",
        display_code="EE-6",
        title="NEC Equipment Labels",
        renderer="pvess_calc.labels.render:render_for_result",
        output_kind="labels",
    ),
)


REFERENCE_SHEET_REGISTRY: tuple[SheetSpec, ...] = (
    SheetSpec(
        code="cover",
        display_code="PV-1",
        title="Cover Page",
        renderer="pvess_calc.permit.cover_sheet:render_cover_sheet",
        output_kind="pdf",
    ),
    SheetSpec(
        code="ee-4",
        display_code="PV-2",
        title="Site Plan",
        renderer="pvess_calc.permit.site_plan:render_site_plan",
        output_kind="pdf",
    ),
    SheetSpec(
        code="ee-4a",
        display_code="PV-3",
        title="Property Plan",
        renderer="pvess_calc.permit.property_context:render_property_context_plan",
        output_kind="pdf",
    ),
    SheetSpec(
        code="pv-4",
        display_code="PV-4",
        title="Attachment Plan",
        renderer="pvess_calc.permit.structural:render_attachment_plan",
        output_kind="pdf",
    ),
    SheetSpec(
        code="pv-5",
        display_code="PV-5",
        title="Mounting Details",
        renderer="pvess_calc.permit.structural:render_mounting_details",
        output_kind="pdf",
    ),
    SheetSpec(
        code="pv-6",
        display_code="EE-1",
        title="String Plan",
        renderer="pvess_calc.permit.structural:render_string_plan",
        output_kind="pdf",
    ),
    SheetSpec(
        code="ee-1",
        display_code="EE-2",
        title="Three Line Diagram",
        renderer="pvess_calc.dxf.render:render_dxf",
        output_kind="dxf",
    ),
    SheetSpec(
        code="one-line",
        display_code="EE-2.1",
        title="One Line Diagram",
        renderer="pvess_calc.dxf.one_line:render_one_line_dxf",
        output_kind="dxf",
    ),
    SheetSpec(
        code="notes",
        display_code="EE-3",
        title="Electrical Notes",
        renderer="pvess_calc.permit.general_notes:render_general_notes",
        output_kind="pdf",
    ),
    SheetSpec(
        code="labels",
        display_code="EE-4",
        title="Labels",
        renderer="pvess_calc.labels.render:render_for_result",
        output_kind="labels",
    ),
    SheetSpec(
        code="placard",
        display_code="EE-5",
        title="Placard",
        renderer="pvess_calc.permit.placard:render_placard_sheet",
        output_kind="pdf",
    ),
    SheetSpec(
        code="design-notes",
        display_code="PV-6",
        title="Design Notes",
        renderer="pvess_calc.permit.design_notes:render_design_notes",
        output_kind="pdf",
    ),
    SheetSpec(
        code="site-photos",
        display_code="PV-7",
        title="Site Photos",
        renderer="pvess_calc.permit.site_photos:render_site_photos",
        output_kind="pdf",
    ),
    SheetSpec(
        code="spec",
        display_code="SPEC",
        title="Specification Sheets",
        renderer="pvess_calc.permit.spec_sheets:render_spec_placeholder",
        output_kind="pdf",
    ),
)


PACKAGE_PROFILES: dict[str, tuple[SheetSpec, ...]] = {
    "internal": SHEET_REGISTRY,
    "tx_residential_pv": REFERENCE_SHEET_REGISTRY,
    "wyssling_like": REFERENCE_SHEET_REGISTRY,
}


def normalize_profile(profile: str | None) -> str:
    if not profile:
        return "internal"
    if profile not in PACKAGE_PROFILES:
        raise KeyError(
            f"Unknown permit package profile {profile!r}. "
            f"Available: {sorted(PACKAGE_PROFILES)}"
        )
    return profile


def registry_for_profile(profile: str | None = None) -> tuple[SheetSpec, ...]:
    return PACKAGE_PROFILES[normalize_profile(profile)]


def codes(profile: str | None = None) -> tuple[str, ...]:
    """All registered sheet codes, in pipeline order."""
    return tuple(s.code for s in registry_for_profile(profile))


def by_code(code: str, profile: str | None = None) -> SheetSpec:
    """Look up a sheet by code; raises KeyError if not registered."""
    for s in registry_for_profile(profile):
        if s.code == code:
            return s
    raise KeyError(f"Sheet code {code!r} not in {normalize_profile(profile)} registry")


def cover_index_rows(profile: str | None = None) -> list[tuple[str, str]]:
    """Rows for the cover sheet's SHEET INDEX block.

    Returns (display_code, title) pairs in pipeline order. The cover renderer
    iterates this directly so the index can't drift from what the builder
    actually emits.
    """
    return [(s.display_code, s.title) for s in registry_for_profile(profile)]
