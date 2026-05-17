"""Generate a QET v0.90 project with real elements + conductors for the SLD.

This is the Phase 1 deliverable: a parameter-driven single-line diagram with
7 device boxes (PV array, DC combiner, RSD, hybrid inverter, ESS unit,
AC disconnect, MSP) connected by 6 conductors. Each device displays multiple
NEC calculation values via `{{KEY}}` placeholders that the existing
`pvess_calc.qet.inject` machinery fills in from a CalculationResult.

Schema quirks worth knowing (locked in tests/test_qet_elements.py):
  - `<project version="0.90">` not "0.80"; no `<?xml ... ?>` declaration.
  - `<conductor>` must contain `<sequentialNumbers/>` (self-closing tag drops).
  - Element-instance terminals must inset x by 4px (`_inst_x`); otherwise QET
    rejects them with `Diagram::fromXml: terminal id N not found` and the
    conductor referencing them silently disappears.
  - Elements must be serialized in descending x order to match QET's own
    output / terminal-ID assignment.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path


# --- Geometry primitives for .elmt <description> ---------------------------

def _rect(x: int, y: int, w: int, h: int) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
        'style="line-style:normal;line-weight:normal;filling:none;color:black" '
        'antialias="false"/>'
    )


def _line(x1: int, y1: int, x2: int, y2: int) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        'style="line-style:normal;line-weight:normal;filling:none;color:black" '
        'length1="1.5" length2="1.5" end1="none" end2="none" antialias="false"/>'
    )


def _text(x: int, y: int, text: str, size: int = 9) -> str:
    return f'<input x="{x}" y="{y}" size="{size}" text="{text}" tagg="none"/>'


# --- Data model ------------------------------------------------------------

@dataclass
class Terminal:
    """Terminal definition shared between .elmt and diagram element."""
    name: str
    x: int
    y: int
    orientation_char: str       # 'n' | 'e' | 's' | 'w' (elmt format)
    orientation_int: int        # 0=N, 1=E, 2=S, 3=W (diagram format)


@dataclass
class DynTextSlot:
    """A piece of text on the element that the inject step fills from NEC calc.

    `info_name` is the elementInformation key (must be unique within element).
    `placeholder` is what we emit in both elementInformation value and the
    dynamic_elmt_text's <text> child — e.g. "{{PV_LABEL}}". The injector
    substitutes it from build_substitutions(result).
    """
    info_name: str
    x: int              # position relative to element hotspot
    y: int
    placeholder: str
    size_pt: int = 9


@dataclass
class ElementDef:
    """A single embedded .elmt definition + its terminals + its text slots."""
    file_name: str              # e.g. "pv_array.elmt"
    display_name: str
    width: int
    height: int
    hotspot_x: int
    hotspot_y: int
    description_body: str       # XML string of rect/line/text icons
    terminals: list[Terminal]
    text_slots: list[DynTextSlot] = field(default_factory=list)


# --- 7 SLD device definitions ----------------------------------------------
#
# Geometry kept deliberately simple (rect + tiny icon text). Phase 2 will
# prettify into real US-style symbols. Terminals follow single-line-diagram
# convention: one "in"/"out" per device side, abstracting DC+/DC-/N.

def pv_array_def() -> ElementDef:
    body = "\n            ".join([
        _rect(-25, -20, 50, 40),
        _line(-25, -20, 25, 20),     # diagonals = solar panel cue
        _line(25, -20, -25, 20),
        _text(-9, 4, "PV", size=10),
    ])
    return ElementDef(
        file_name="pv_array.elmt",
        display_name="PV Array",
        width=50, height=40, hotspot_x=25, hotspot_y=20,
        description_body=body,
        terminals=[Terminal("OUT", 25, 0, "e", 1)],
        text_slots=[
            DynTextSlot("label", -25, 25, "{{PV_LABEL}}", size_pt=10),
            DynTextSlot("array", -25, 42, "{{PV_STRINGS}}×{{PV_MODULES_PER_STRING}} = {{PV_MODULE_COUNT}}"),
            DynTextSlot("voc",   -25, 58, "Voc(cold): {{PV_VOC_COLD}}"),
            DynTextSlot("isc",   -25, 74, "Isc(max): {{PV_ISC_MAX}}"),
        ],
    )


def dc_combiner_def() -> ElementDef:
    body = "\n            ".join([
        _rect(-25, -20, 50, 40),
        _text(-18, 4, "COMB", size=9),
    ])
    return ElementDef(
        file_name="dc_combiner.elmt",
        display_name="DC Combiner / Disconnect",
        width=50, height=40, hotspot_x=25, hotspot_y=20,
        description_body=body,
        terminals=[
            Terminal("IN",  -25, 0, "w", 3),
            Terminal("OUT",  25, 0, "e", 1),
        ],
        text_slots=[
            DynTextSlot("label", -25, 25, "{{DC_COMBINER_LABEL}}", size_pt=10),
            DynTextSlot("ocpd",  -25, 42, "OCPD: {{PV_OCPD}}"),
            DynTextSlot("cond",  -25, 58, "{{PV_CONDUCTOR}}"),
            DynTextSlot("vd",    -25, 74, "VD: {{PV_VOLTAGE_DROP}}"),
        ],
    )


def rsd_def() -> ElementDef:
    body = "\n            ".join([
        _rect(-25, -20, 50, 40),
        _text(-12, 4, "RSD", size=10),
    ])
    return ElementDef(
        file_name="rsd.elmt",
        display_name="Rapid Shutdown Device",
        width=50, height=40, hotspot_x=25, hotspot_y=20,
        description_body=body,
        terminals=[
            Terminal("IN",  -25, 0, "w", 3),
            Terminal("OUT",  25, 0, "e", 1),
        ],
        text_slots=[
            DynTextSlot("label", -25, 25, "{{RSD_LABEL}}", size_pt=10),
            DynTextSlot("model", -25, 42, "{{RSD_MODEL}}"),
        ],
    )


def hybrid_inverter_def() -> ElementDef:
    body = "\n            ".join([
        _rect(-30, -30, 60, 60),
        _text(-9, -6, "INV", size=11),
        _text(-22, 10, "DC↔AC", size=8),
    ])
    return ElementDef(
        file_name="hybrid_inverter.elmt",
        display_name="Hybrid Inverter",
        width=60, height=60, hotspot_x=30, hotspot_y=30,
        description_body=body,
        terminals=[
            Terminal("DC_IN", -30,   0, "w", 3),
            Terminal("AC_OUT", 30,   0, "e", 1),
            Terminal("BATT",   0,  30, "s", 2),
        ],
        text_slots=[
            DynTextSlot("label", -30, 35, "{{INVERTER_LABEL}}", size_pt=10),
            DynTextSlot("model", -30, 52, "{{INVERTER_MODEL}}"),
            DynTextSlot("ac",    -30, 68, "{{INVERTER_AC}}"),
        ],
    )


def ess_unit_def() -> ElementDef:
    body = "\n            ".join([
        _rect(-25, -20, 50, 40),
        _text(-9, -2, "ESS", size=10),
        _text(-3, 12, "+", size=9),
    ])
    return ElementDef(
        file_name="ess_unit.elmt",
        display_name="ESS Unit",
        width=50, height=40, hotspot_x=25, hotspot_y=20,
        description_body=body,
        terminals=[Terminal("BATT", 0, -20, "n", 0)],
        text_slots=[
            DynTextSlot("label", -25, 25, "{{ESS_LABEL}}", size_pt=10),
            DynTextSlot("model", -25, 42, "{{ESS_MODEL}}"),
            DynTextSlot("kwh",   -25, 58, "Qty {{ESS_QTY}} — {{ESS_KWH}}"),
        ],
    )


def ac_disconnect_def() -> ElementDef:
    body = "\n            ".join([
        _rect(-25, -20, 50, 40),
        _line(-12, -5, 12, -15),    # opening switch cue
        _text(-9, 12, "AC", size=10),
    ])
    return ElementDef(
        file_name="ac_disconnect.elmt",
        display_name="AC Disconnect",
        width=50, height=40, hotspot_x=25, hotspot_y=20,
        description_body=body,
        terminals=[
            Terminal("IN",  -25, 0, "w", 3),
            Terminal("OUT",  25, 0, "e", 1),
        ],
        text_slots=[
            DynTextSlot("label", -25, 25, "{{AC_DISC_LABEL}}", size_pt=10),
            DynTextSlot("ocpd",  -25, 42, "OCPD: {{AC_DISC_OCPD}}"),
            DynTextSlot("cond",  -25, 58, "{{ESS_AC_CONDUCTOR}}"),
        ],
    )


def msp_def() -> ElementDef:
    body = "\n            ".join([
        _rect(-25, -25, 50, 50),
        _text(-12, -3, "MSP", size=10),
        _line(-20, 8, 20, 8),
        _line(-20, 14, 20, 14),
    ])
    return ElementDef(
        file_name="msp.elmt",
        display_name="Main Service Panel",
        width=50, height=50, hotspot_x=25, hotspot_y=25,
        description_body=body,
        terminals=[Terminal("IN", -25, 0, "w", 3)],
        text_slots=[
            DynTextSlot("label",  -25, 30, "{{MSP_LABEL}}", size_pt=10),
            DynTextSlot("rating", -25, 47, "{{MSP_RATING}}"),
            DynTextSlot("bus",    -25, 63, "Bus: {{BUSBAR_RATING}}"),
        ],
    )


# --- Builders for project XML ----------------------------------------------

def _new_uuid() -> str:
    return "{" + str(_uuid.uuid4()) + "}"


def build_elmt_xml(d: ElementDef, elmt_uuid: str) -> str:
    """The <element name="..."><definition>...</definition></element> block
    that lives inside <collection><category name="import">."""
    terminals_xml = "\n            ".join(
        f'<terminal x="{t.x}" y="{t.y}" name="{t.name}" orientation="{t.orientation_char}"/>'
        for t in d.terminals
    )
    return (
        f'      <element name="{d.file_name}">\n'
        f'        <definition width="{d.width}" height="{d.height}" '
        f'version="0.3" hotspot_x="{d.hotspot_x}" hotspot_y="{d.hotspot_y}" '
        f'type="element">\n'
        f'          <uuid uuid="{elmt_uuid}"/>\n'
        f'          <names><name lang="en">{d.display_name}</name></names>\n'
        f'          <description>\n'
        f'            {d.description_body}\n'
        f'            {terminals_xml}\n'
        f'          </description>\n'
        f'        </definition>\n'
        f'      </element>'
    )


@dataclass
class ElementInstance:
    """An <element> placement in the diagram."""
    elmt_def: ElementDef
    x: int
    y: int
    orientation: int = 0
    instance_uuid: str = field(default_factory=_new_uuid)
    terminal_base_id: int = 0   # assigned during diagram assembly


def _inst_x(raw: int) -> int:
    """QET shifts horizontal terminal positions inward by 4px when loading a
    diagram. If we don't pre-apply the same shift, QET's parser fails to bind
    the terminal ('Diagram::fromXml: terminal id N not found') and conductors
    referencing it silently disappear.
    """
    if raw > 0:
        return raw - 4
    if raw < 0:
        return raw + 4
    return raw


def _inst_y(raw: int) -> int:
    """Same inset rule applies to vertical-oriented terminals."""
    if raw > 0:
        return raw - 4
    if raw < 0:
        return raw + 4
    return raw


def build_diagram_element_xml(inst: ElementInstance) -> str:
    """The <element> instance block inside <diagram><elements>."""
    terms = "\n                ".join(
        f'<terminal x="{_inst_x(t.x)}" y="{_inst_y(t.y)}" '
        f'orientation="{t.orientation_int}" id="{inst.terminal_base_id + i}"/>'
        for i, t in enumerate(inst.elmt_def.terminals)
    )

    if not inst.elmt_def.text_slots:
        # Pure-geometry element with no dynamic text; emit an empty
        # elementInformations + dynamic_texts block so the structure is valid.
        infos_xml = ""
        dyns_xml = ""
    else:
        infos_xml = "\n                    ".join(
            f'<elementInformation show="1" name="{s.info_name}">{s.placeholder}</elementInformation>'
            for s in inst.elmt_def.text_slots
        )
        dyns_xml = "\n                    ".join(
            (
                f'<dynamic_elmt_text x="{s.x}" y="{s.y}" rotation="0" '
                f'Halignment="AlignLeft" Valignment="AlignTop" '
                f'font="MS Shell Dlg 2,{s.size_pt},-1,5,75,0,0,0,0,0,Normal" '
                f'text_width="-1" keep_visual_rotation="true" frame="false" '
                f'uuid="{_new_uuid()}" text_from="ElementInfo">\n'
                f'                        <text>{s.placeholder}</text>\n'
                f'                        <info_name>{s.info_name}</info_name>\n'
                f'                    </dynamic_elmt_text>'
            )
            for s in inst.elmt_def.text_slots
        )

    return f"""            <element x="{inst.x}" y="{inst.y}" z="10" orientation="{inst.orientation}" \
type="embed://import/{inst.elmt_def.file_name}" \
prefix="" freezeLabel="false" uuid="{inst.instance_uuid}">
                <terminals>
                    {terms}
                </terminals>
                <inputs/>
                <elementInformations>
                    {infos_xml}
                </elementInformations>
                <dynamic_texts>
                    {dyns_xml}
                </dynamic_texts>
                <texts_groups/>
            </element>"""


@dataclass
class ConductorLink:
    src_inst: ElementInstance
    src_terminal_name: str   # e.g. "OUT"
    dst_inst: ElementInstance
    dst_terminal_name: str


def _terminal_id(inst: ElementInstance, name: str) -> int:
    for i, t in enumerate(inst.elmt_def.terminals):
        if t.name == name:
            return inst.terminal_base_id + i
    raise KeyError(f"terminal {name} not on {inst.elmt_def.file_name}")


def build_conductor_xml(link: ConductorLink) -> str:
    t1 = _terminal_id(link.src_inst, link.src_terminal_name)
    t2 = _terminal_id(link.dst_inst, link.dst_terminal_name)
    return (
        f'            <conductor x="0" y="0" terminal1="{t1}" terminal2="{t2}" '
        'type="multi" condsize="1" cable="" onetextperfolio="0" '
        'vertical-alignment="AlignRight" horizrotatetext="0" bicolor="false" '
        'bus="" dash-size="1" numsize="9" horizontal-alignment="AlignBottom" '
        'function="" conductor_color="" text_color="#000000" conductor_section="" '
        'color2="#000000" tension_protocol="" displaytext="0" formula="" '
        'vertirotatetext="0" freezeLabel="false" num="">\n'
        '                <sequentialNumbers/>\n'
        '            </conductor>'
    )


# --- Whole-project assembly ------------------------------------------------

PROJECT_SKELETON = """\
<project title="__TITLE__" version="0.90">
    <properties>
        <property show="1" name="savedfilename">__FILENAME__</property>
    </properties>
    <newdiagrams>
        <border rowsize="80" rows="12" displaycols="true" cols="22" colsize="60" displayrows="true"/>
        <inset displayAt="bottom" folio="%id/%total" indexrev="" plant="" date="null" filename="" author="" locmach="" title="" version="" auto_page_num=""/>
        <conductors condsize="1" cable="" onetextperfolio="0" vertical-alignment="AlignRight" horizrotatetext="0" bicolor="false" bus="" dash-size="1" numsize="9" horizontal-alignment="AlignBottom" function="" conductor_color="" conductor_section="" text_color="#000000" color2="#000000" tension_protocol="" displaytext="0" formula="" vertirotatetext="0" num="" type="multi"/>
        <report label="%f-%l%c"/>
        <xrefs>
            <xref slave_label="(%f-%l%c)" displayhas="contacts" offset="0" delayprefix="" showpowerctc="false" snapto="bottom" powerprefix="" xrefpos="AlignBottom" type="coil" master_label="%f-%l%c" switchprefix=""/>
            <xref slave_label="(%f-%l%c)" displayhas="contacts" offset="0" delayprefix="" showpowerctc="false" snapto="label" powerprefix="" xrefpos="AlignBottom" type="protection" master_label="%f-%l%c" switchprefix=""/>
            <xref slave_label="(%f-%l%c)" displayhas="contacts" offset="0" delayprefix="" showpowerctc="false" snapto="label" powerprefix="" xrefpos="AlignBottom" type="commutator" master_label="%f-%l%c" switchprefix=""/>
        </xrefs>
        <conductors_autonums freeze_new_conductors="false" current_autonum=""/>
        <folio_autonums/>
        <element_autonums freeze_new_elements="false" current_autonum=""/>
    </newdiagrams>
    <diagram freezeNewElement="false" cols="22" folio="%id/%total" version="0.90" indexrev="" date="null" author="pvess-calc" height="960" freezeNewConductor="false" title="__DIAGRAM_TITLE__" auto_page_num="" displaycols="true" filename="__FILENAME__" colsize="60" order="1" displayrows="true" locmach="" rows="12" plant="" rowsize="80" displayAt="bottom">
        <defaultconductor condsize="1" cable="" onetextperfolio="0" vertical-alignment="AlignRight" horizrotatetext="0" bicolor="false" bus="" dash-size="1" numsize="9" horizontal-alignment="AlignBottom" function="" conductor_color="" conductor_section="" text_color="#000000" color2="#000000" tension_protocol="" displaytext="0" formula="" vertirotatetext="0" num="" type="multi"/>
        <elements>
__ELEMENTS__
        </elements>
        <conductors>
__CONDUCTORS__
        </conductors>
        <inputs>
__INPUTS__
        </inputs>
    </diagram>
    <collection>
        <category name="import">
            <names>
                <name lang="en">Imported elements</name>
            </names>
__EMBEDDED_ELMTS__
        </category>
    </collection>
</project>
"""


def _assemble_project(
    *,
    title: str,
    filename: str,
    instances: list[ElementInstance],
    links: list[ConductorLink],
    extra_inputs_xml: str = "",
) -> str:
    """Common assembly path: sort elements right-to-left, assign terminal IDs,
    emit element/conductor/embedded-collection XML, plug into the skeleton."""
    # QET serializes elements right-to-left (largest x first) and assigns
    # terminal IDs sequentially across that order. Mirror that so our
    # conductors reference the right IDs.
    ordered = sorted(instances, key=lambda e: e.x, reverse=True)
    cursor = 0
    for e in ordered:
        e.terminal_base_id = cursor
        cursor += len(e.elmt_def.terminals)

    elements_xml = "\n".join(build_diagram_element_xml(e) for e in ordered)
    conductors_xml = "\n".join(build_conductor_xml(l) for l in links)

    # One <element> entry per unique ElementDef goes into the <collection>.
    seen: dict[str, ElementDef] = {}
    for inst in instances:
        seen.setdefault(inst.elmt_def.file_name, inst.elmt_def)
    embedded_xml = "\n".join(build_elmt_xml(d, _new_uuid()) for d in seen.values())

    return (
        PROJECT_SKELETON
        .replace("__TITLE__", title)
        .replace("__DIAGRAM_TITLE__", title)
        .replace("__FILENAME__", filename)
        .replace("__ELEMENTS__", elements_xml)
        .replace("__CONDUCTORS__", conductors_xml)
        .replace("__INPUTS__", extra_inputs_xml)
        .replace("__EMBEDDED_ELMTS__", embedded_xml)
    )


# --- Phase-1 SLD layout ----------------------------------------------------

# Single-line-diagram layout (horizontal flow with ESS branching south):
#
#   [PV-1] ─── [DC-COMB-1] ─── [RSD-1] ─── [INV-1] ─── [AC-DISC-1] ─── [MSP]
#                                              │
#                                          [ESS-1]
#
# Positions are pixel-space on the QET canvas. y=240 for the main row keeps
# everything centered in a 960-tall diagram; ESS at y=420 drops below INV.

_SLD_LAYOUT = [
    ("PV-1",        pv_array_def,        140,  240),
    ("DC-COMB-1",   dc_combiner_def,     320,  240),
    ("RSD-1",       rsd_def,             500,  240),
    ("INV-1",       hybrid_inverter_def, 680,  240),
    ("AC-DISC-1",   ac_disconnect_def,   860,  240),
    ("MSP",         msp_def,            1040,  240),
    ("ESS-1",       ess_unit_def,        680,  420),
]


def build_sld_template(out_path: Path) -> None:
    """Phase 1 deliverable: 7-device residential PV+ESS single-line diagram
    with `{{KEY}}` placeholders ready for inject_from_result()."""
    defs = {lbl: factory() for lbl, factory, _, _ in _SLD_LAYOUT}
    insts = {
        lbl: ElementInstance(elmt_def=defs[lbl], x=x, y=y)
        for lbl, _, x, y in _SLD_LAYOUT
    }
    links = [
        ConductorLink(insts["PV-1"],      "OUT",    insts["DC-COMB-1"], "IN"),
        ConductorLink(insts["DC-COMB-1"], "OUT",    insts["RSD-1"],     "IN"),
        ConductorLink(insts["RSD-1"],     "OUT",    insts["INV-1"],     "DC_IN"),
        ConductorLink(insts["INV-1"],     "AC_OUT", insts["AC-DISC-1"], "IN"),
        ConductorLink(insts["AC-DISC-1"], "OUT",    insts["MSP"],       "IN"),
        ConductorLink(insts["ESS-1"],     "BATT",   insts["INV-1"],     "BATT"),
    ]

    # A title strip + the interconnection-method summary as diagram-level text
    # (rich-HTML, same trick as Phase 0's template.py).
    from xml.sax.saxutils import quoteattr

    from .template import wrap_html
    extra = []
    for x, y, text, size in [
        (60, 30, "{{PROJECT_NAME}} — {{PROJECT_ID}} ({{NEC_EDITION}})", 12),
        (60, 55, "Location: {{PROJECT_LOCATION}}", 9),
        (60, 75, "Total backfeed: {{TOTAL_BACKFEED}} · Method: {{INTERCONNECT_METHOD}} · Status: {{INTERCONNECT_STATUS}}", 9),
    ]:
        html = wrap_html(text, size_pt=size)
        extra.append(
            f'            <input rotation="0" y="{y}" x="{x}" '
            f'font="MS Shell Dlg 2,8,-1,5,50,0,0,0,0,0,Normal" text={quoteattr(html)}/>'
        )

    xml = _assemble_project(
        title="Residential PV+ESS SLD",
        filename="residential-ess-v1",
        instances=list(insts.values()),
        links=links,
        extra_inputs_xml="\n".join(extra),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(xml, encoding="utf-8")


# --- Phase-1 spike (kept for tests/regression) -----------------------------

def build_demo_project(out_path: Path) -> None:
    """Two elements (PV → Inverter) wired by one conductor. Locked in tests
    to defend the schema quirks we paid an afternoon to find."""
    pv_def = pv_array_def()
    inv_def = hybrid_inverter_def()

    pv = ElementInstance(elmt_def=pv_def, x=200, y=200)
    inv = ElementInstance(elmt_def=inv_def, x=400, y=200)

    xml = _assemble_project(
        title="Phase 1 Element Demo",
        filename="demo-elements",
        instances=[pv, inv],
        links=[ConductorLink(pv, "OUT", inv, "DC_IN")],
    )
    out_path.write_text(xml, encoding="utf-8")


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parents[3]
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        target = root / "library" / "templates" / "demo-elements.qet"
        build_demo_project(target)
    else:
        target = root / "library" / "templates" / "residential-ess-v1.qet"
        build_sld_template(target)
    print(f"wrote {target}")
