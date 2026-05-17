from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from pvess_calc.calc.engine import run
from pvess_calc.qet.inject import (
    PLACEHOLDER_RE,
    build_substitutions,
    inject,
    inject_from_result,
)
from tests.conftest import make_inputs


def test_placeholder_pattern_matches_expected_keys():
    assert PLACEHOLDER_RE.findall("hello {{FOO}} {{BAR_BAZ}}") == ["FOO", "BAR_BAZ"]
    assert PLACEHOLDER_RE.findall("no placeholders here") == []
    # Lower-case keys are not matched (we enforce SCREAMING_SNAKE).
    assert PLACEHOLDER_RE.findall("{{lower}}") == []


def test_inject_replaces_placeholders_in_input_text(tmp_path: Path):
    template = tmp_path / "tpl.qet"
    template.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project version="0.8" title="t" projectstate="0">
  <diagrams>
    <diagram>
      <inputs>
        <input text="Hello {{NAME}}" x="0" y="0"/>
        <input text="OCPD: {{RATING}}" x="0" y="10"/>
      </inputs>
    </diagram>
  </diagrams>
</project>
""",
        encoding="utf-8",
    )
    out = tmp_path / "out.qet"
    report = inject(template, out, {"NAME": "World", "RATING": "25 A"})

    assert report.substitutions_applied == 2
    tree = etree.parse(str(out))
    texts = [el.get("text") for el in tree.iter("input")]
    assert "Hello World" in texts
    assert "OCPD: 25 A" in texts


def test_inject_strict_mode_raises_on_unresolved(tmp_path: Path):
    template = tmp_path / "tpl.qet"
    template.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project version="0.8"><diagrams><diagram><inputs>
<input text="{{MISSING_KEY}}" x="0" y="0"/>
</inputs></diagram></diagrams></project>""",
        encoding="utf-8",
    )
    out = tmp_path / "out.qet"
    with pytest.raises(KeyError, match="MISSING_KEY"):
        inject(template, out, {"OTHER": "x"}, strict=True)


def test_inject_does_not_modify_geometry(tmp_path: Path):
    template = tmp_path / "tpl.qet"
    template.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project version="0.8"><diagrams><diagram><inputs>
<input text="{{K}}" x="123" y="456" rotation="90" size="11"/>
</inputs></diagram></diagrams></project>""",
        encoding="utf-8",
    )
    out = tmp_path / "out.qet"
    inject(template, out, {"K": "value"})

    el = etree.parse(str(out)).find(".//input")
    assert el.get("x") == "123"
    assert el.get("y") == "456"
    assert el.get("rotation") == "90"
    assert el.get("size") == "11"
    assert el.get("text") == "value"


def test_build_substitutions_covers_every_template_key(repo_root: Path):
    """Every {{KEY}} in the shipped template must be filled by build_substitutions."""
    template = repo_root / "library" / "templates" / "residential-ess-v0.qet"
    text = template.read_text(encoding="utf-8")
    template_keys = set(PLACEHOLDER_RE.findall(text))

    result = run(make_inputs())
    sub_keys = set(build_substitutions(result).keys())

    missing = template_keys - sub_keys
    assert not missing, f"Template uses keys not in substitutions: {missing}"


def test_end_to_end_inject_real_template(repo_root: Path, tmp_path: Path):
    template = repo_root / "library" / "templates" / "residential-ess-v0.qet"
    out = tmp_path / "system.qet"
    result = run(make_inputs())
    report = inject_from_result(result, template, out, strict=True)

    assert out.exists()
    assert report.substitutions_applied > 20  # 26+ keys in our template

    # No unresolved {{...}} placeholders should remain.
    rendered = out.read_text(encoding="utf-8")
    assert "{{" not in rendered
