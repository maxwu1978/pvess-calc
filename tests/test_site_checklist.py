"""Tests for the site survey checklist (Phase K.1).

Three layers of guard:

1. SITE_FIELDS list itself is well-formed (no empty labels, unique paths)
2. Every yaml_path resolves to a real Inputs-schema field — so a typo
   in a path is caught before a technician fills in the wrong value
3. The rendered PDF contains every declared label — so a renderer bug
   that silently drops a row is caught
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.site_checklist.builder import render_checklist
from pvess_calc.site_checklist.field_specs import SITE_FIELDS


# ─── Data integrity ────────────────────────────────────────────────────────


def test_site_fields_have_unique_yaml_paths():
    paths = [f.yaml_path for f in SITE_FIELDS]
    assert len(paths) == len(set(paths)), \
        f"duplicate yaml_path in SITE_FIELDS: {paths}"


def test_site_fields_have_non_empty_labels():
    for spec in SITE_FIELDS:
        assert spec.label, f"empty label on field {spec.yaml_path}"


def test_site_fields_have_non_empty_yaml_paths():
    for spec in SITE_FIELDS:
        assert spec.yaml_path, f"empty yaml_path on field {spec.label}"


def test_site_fields_choice_type_has_choices():
    """If field_type == 'choice', `choices` must be non-empty."""
    for spec in SITE_FIELDS:
        if spec.field_type == "choice":
            assert spec.choices, \
                f"choice field {spec.yaml_path} has no choices listed"


def test_site_fields_known_sections():
    valid = {"admin", "electrical", "roof", "routing", "climate"}
    for spec in SITE_FIELDS:
        assert spec.section in valid, \
            f"field {spec.yaml_path} has unknown section {spec.section!r}"


# ─── Schema cross-reference ────────────────────────────────────────────────


def test_every_yaml_path_resolves_to_inputs_schema():
    """Doctor-equivalent test: every declared yaml_path must point at a
    real field on the `Inputs` pydantic model. Catches typos."""
    from pvess_calc.doctor import _collect_pydantic_paths
    from pvess_calc.schema import Inputs

    schema_paths = _collect_pydantic_paths(Inputs)
    bad = []
    for spec in SITE_FIELDS:
        normalized = spec.yaml_path.replace("[]", "")
        if normalized not in schema_paths:
            bad.append(spec.yaml_path)
    assert not bad, \
        f"yaml_path doesn't resolve in Inputs schema: {bad}\n" \
        f"available paths sample: {sorted(list(schema_paths))[:20]}"


# ─── PDF rendering ─────────────────────────────────────────────────────────


@pytest.fixture
def rendered_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "site-checklist.pdf"
    render_checklist(pdf)
    assert pdf.exists() and pdf.stat().st_size > 1000
    return pdf


def test_pdf_renders_without_error(rendered_pdf: Path):
    """Simplest test: render_checklist() produces a non-trivial PDF."""
    assert rendered_pdf.stat().st_size > 1000


def _pdf_normalized(pdf_path: Path) -> str:
    """Extract PDF text and collapse all whitespace to single spaces.
    Necessary because narrow table cells wrap long labels across two
    lines, but the full text is still present once we ignore newlines."""
    from pypdf import PdfReader
    raw = "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf_path)).pages)
    return " ".join(raw.split())


def test_pdf_contains_every_label(rendered_pdf: Path):
    """Every SITE_FIELDS.label must appear in the extracted PDF text
    (after whitespace normalization)."""
    text = _pdf_normalized(rendered_pdf)
    missing = [
        spec.label for spec in SITE_FIELDS
        if " ".join(spec.label.split()) not in text
    ]
    assert not missing, f"labels missing from rendered PDF: {missing}"


def test_pdf_contains_section_banners(rendered_pdf: Path):
    """Each of the 5 section banners must render."""
    from pvess_calc.site_checklist.field_specs import SECTION_TITLES

    text = _pdf_normalized(rendered_pdf)
    for title in SECTION_TITLES.values():
        normalized_title = " ".join(title.split())
        assert normalized_title in text, f"section banner missing: {title!r}"


def test_pdf_contains_yaml_paths(rendered_pdf: Path):
    """Each row's yaml_path tag should be visible in the PDF — that's
    the 回填指南 promised by the closing standard."""
    text = _pdf_normalized(rendered_pdf)
    missing = [
        spec.yaml_path for spec in SITE_FIELDS
        if spec.yaml_path not in text
    ]
    assert not missing, f"yaml_path tag missing from PDF: {missing}"


# ─── Doctor integration ────────────────────────────────────────────────────


def test_doctor_site_checklist_check_passes():
    """The doctor's wrapper around the same checks must PASS on the
    canonical SITE_FIELDS list."""
    from pvess_calc.doctor import _check_site_checklist_covers_schema
    [r] = _check_site_checklist_covers_schema()
    assert r.status == "PASS", r.detail


def test_doctor_site_checklist_catches_bogus_path(monkeypatch):
    """Regression bait: inject a bogus yaml_path into SITE_FIELDS, verify
    the doctor flags it. Proves the schema cross-reference logic works."""
    from pvess_calc.site_checklist import field_specs
    from pvess_calc.doctor import _check_site_checklist_covers_schema

    bogus = field_specs.FieldSpec(
        yaml_path="service.this_field_definitely_does_not_exist",
        label="Bogus",
        section="admin",
    )
    monkeypatch.setattr(
        field_specs, "SITE_FIELDS",
        field_specs.SITE_FIELDS + (bogus,),
    )

    [r] = _check_site_checklist_covers_schema()
    assert r.status == "FAIL"
    assert "this_field_definitely_does_not_exist" in r.detail
