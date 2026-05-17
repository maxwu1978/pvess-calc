"""Regression tests for the Phase 1 element/conductor generator.

These lock down schema quirks that took an afternoon of QET log-diving to find.
Each assertion ties back to a real failure mode in QET 0.90 — see CLAUDE.md.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from pvess_calc.qet.elements import (
    _inst_x,
    build_demo_project,
    build_sld_template,
    hybrid_inverter_def,
    pv_array_def,
)


@pytest.fixture
def demo_xml(tmp_path: Path) -> etree._ElementTree:
    out = tmp_path / "demo.qet"
    build_demo_project(out)
    return etree.parse(str(out))


def test_terminal_x_inset_matches_qet_binding_rule():
    """QET binds element-instance terminals to .elmt terminals by *position*.
    The instance x is the raw .elmt x inset by 4 toward center; if we emit the
    raw value, QET drops the terminal with 'Diagram::fromXml: terminal id N
    not found' and any conductor referencing it silently disappears."""
    assert _inst_x(25) == 21
    assert _inst_x(-25) == -21
    assert _inst_x(0) == 0


def test_project_version_is_0_90(demo_xml: etree._ElementTree):
    """QET 0.90 rejects (or silently fails to load the project tree) when the
    `<project version>` attribute reads "0.80" instead of "0.90"."""
    root = demo_xml.getroot()
    assert root.tag == "project"
    assert root.get("version") == "0.90"


def test_no_xml_declaration_at_top(tmp_path: Path):
    """QET-saved files start directly with `<project ...>` (no `<?xml ...?>`).
    Adding the declaration didn't break loading in our case but kept us from
    being byte-identical to QET output, which delayed root-cause analysis."""
    out = tmp_path / "demo.qet"
    build_demo_project(out)
    first_line = out.read_text().splitlines()[0]
    assert first_line.startswith("<project ")


def test_elements_sorted_right_to_left(demo_xml: etree._ElementTree):
    """QET serializes diagram elements by descending x so terminal IDs map
    consistently across reload. Match that order so the conductor in our
    generator can pre-compute the right IDs."""
    elements = demo_xml.findall(".//diagram/elements/element")
    xs = [int(e.get("x")) for e in elements]
    assert xs == sorted(xs, reverse=True)


def test_conductor_has_sequential_numbers_child(demo_xml: etree._ElementTree):
    """A self-closing `<conductor ... />` is silently dropped by QET; the
    element must contain `<sequentialNumbers/>`."""
    conductor = demo_xml.find(".//conductors/conductor")
    assert conductor is not None
    child_tags = [c.tag for c in conductor]
    assert "sequentialNumbers" in child_tags


def test_conductor_terminals_resolve_to_real_ids(demo_xml: etree._ElementTree):
    """terminal1/terminal2 on the conductor must reference terminal `id`
    attributes that exist somewhere in the diagram."""
    conductor = demo_xml.find(".//conductors/conductor")
    t1, t2 = conductor.get("terminal1"), conductor.get("terminal2")

    all_ids = {
        t.get("id")
        for t in demo_xml.findall(".//elements/element/terminals/terminal")
    }
    assert t1 in all_ids, f"conductor terminal1={t1} not in element terminals"
    assert t2 in all_ids, f"conductor terminal2={t2} not in element terminals"


def test_instance_terminals_omit_unwanted_attrs(demo_xml: etree._ElementTree):
    """QET-saved instance terminals carry only x/y/orientation/id. Emitting
    name="", number="", nameHidden="0" doesn't break parsing per se but
    diverges from QET output and risks future schema brittleness."""
    for term in demo_xml.findall(".//elements/element/terminals/terminal"):
        attrs = set(term.attrib.keys())
        # Required:
        assert {"x", "y", "orientation", "id"}.issubset(attrs)
        # Should-not-have:
        assert "name" not in attrs
        assert "number" not in attrs
        assert "nameHidden" not in attrs


def test_elmt_definitions_keep_terminal_names(demo_xml: etree._ElementTree):
    """The `.elmt` definitions in <collection> *should* keep the original
    terminal `name` (OUT, DC_IN, ...) — those are reference identifiers for
    humans and don't conflict with QET's positional binding."""
    coll_terminals = demo_xml.findall(
        ".//collection//element/definition/description/terminal"
    )
    names = [t.get("name") for t in coll_terminals]
    # SLD-style demo uses simplified terminal names.
    assert "OUT" in names
    assert "DC_IN" in names


@pytest.fixture
def sld_xml(tmp_path: Path) -> etree._ElementTree:
    out = tmp_path / "sld.qet"
    build_sld_template(out)
    return etree.parse(str(out))


def test_sld_has_seven_elements_six_conductors(sld_xml: etree._ElementTree):
    """The Phase 1 SLD contains 7 device instances + 6 conductors."""
    elements = sld_xml.findall(".//diagram/elements/element")
    conductors = sld_xml.findall(".//diagram/conductors/conductor")
    assert len(elements) == 7
    assert len(conductors) == 6


def test_sld_every_placeholder_appears_in_substitutions(sld_xml: etree._ElementTree):
    """Every `{{KEY}}` placeholder in the generated SLD template must be one
    of the keys produced by `build_substitutions`, so injection clears them all."""
    import re

    from pvess_calc.calc.engine import run
    from pvess_calc.qet.inject import build_substitutions
    from pvess_calc.schema import Inputs
    from tests.conftest import make_inputs

    template_text = etree.tostring(sld_xml, encoding="unicode")
    keys_in_template = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", template_text))
    result = run(make_inputs())
    keys_available = set(build_substitutions(result).keys())

    missing = keys_in_template - keys_available
    assert not missing, f"SLD template uses unknown keys: {missing}"


def test_sld_conductor_endpoints_resolve(sld_xml: etree._ElementTree):
    """Every conductor's terminal1/terminal2 must reference real instance
    terminal IDs in the diagram."""
    all_ids = {
        t.get("id")
        for t in sld_xml.findall(".//elements/element/terminals/terminal")
    }
    for c in sld_xml.findall(".//conductors/conductor"):
        assert c.get("terminal1") in all_ids, f"dangling terminal1={c.get('terminal1')}"
        assert c.get("terminal2") in all_ids, f"dangling terminal2={c.get('terminal2')}"
