"""Generate the QET v0.90 SLD template.

QET diagram-level text annotations live in `<inputs><input>` whose `text`
attribute holds a Qt rich-text HTML blob. The visible string is the inner
`<span>` content; we put `{{KEY}}` placeholders there so the injector's regex
finds them. The outer HTML is boilerplate that QET emits verbatim.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr


HTML_WRAPPER = (
    '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" '
    '"http://www.w3.org/TR/REC-html40/strict.dtd">\n'
    '<html><head><meta name="qrichtext" content="1" /><style type="text/css">\n'
    'p, li { white-space: pre-wrap; }\n'
    '</style></head><body style=" font-family:\'MS Shell Dlg 2\'; '
    'font-size:8pt; font-weight:400; font-style:normal;">\n'
    '<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; '
    'margin-right:0px; -qt-block-indent:0; text-indent:0px;">'
    '<span style=" font-family:\'Sans Serif\'; font-size:__SIZE__pt;">__TEXT__</span>'
    '</p></body></html>'
)

INPUT_FONT = "MS Shell Dlg 2,8,-1,5,50,0,0,0,0,0,Normal"


@dataclass
class TextLabel:
    x: int
    y: int
    text: str           # plain text, may contain {{KEY}} placeholders
    size_pt: int = 9    # display point size of the inner span
    rotation: int = 0


def wrap_html(text: str, size_pt: int = 9) -> str:
    """Wrap a plain string in the Qt rich-text HTML envelope.

    Escapes XML-special chars in the visible text. `{{KEY}}` placeholders pass
    through unescaped (they contain only safe chars).
    """
    return HTML_WRAPPER.replace("__SIZE__", str(size_pt)).replace(
        "__TEXT__", escape(text)
    )


def _input_xml(label: TextLabel) -> str:
    html = wrap_html(label.text, size_pt=label.size_pt)
    return (
        f'            <input rotation="{label.rotation}" y="{label.y}" '
        f'x="{label.x}" font="{INPUT_FONT}" text={quoteattr(html)}/>'
    )


# SLD layout: left-to-right power flow with ESS branch joining at the inverter.
DEFAULT_LABELS: list[TextLabel] = [
    # Title strip
    TextLabel(60, 30, "{{PROJECT_NAME}} — {{PROJECT_ID}} ({{NEC_EDITION}})", size_pt=12),
    TextLabel(60, 55, "Location: {{PROJECT_LOCATION}}", size_pt=9),
    # PV array column
    TextLabel(60, 130, "{{PV_LABEL}}", size_pt=11),
    TextLabel(60, 155, "{{PV_MODULE}}"),
    TextLabel(60, 175, "Array: {{PV_STRINGS}}×{{PV_MODULES_PER_STRING}} = {{PV_MODULE_COUNT}}"),
    TextLabel(60, 195, "Voc(cold): {{PV_VOC_COLD}}"),
    TextLabel(60, 215, "Isc(max): {{PV_ISC_MAX}}"),
    # DC combiner / OCPD / conductor
    TextLabel(280, 130, "{{DC_COMBINER_LABEL}}", size_pt=11),
    TextLabel(280, 155, "OCPD: {{PV_OCPD}}"),
    TextLabel(280, 175, "Cond: {{PV_CONDUCTOR}}"),
    TextLabel(280, 195, "DC drop est: {{PV_VOLTAGE_DROP}}"),
    # RSD
    TextLabel(480, 130, "{{RSD_LABEL}}", size_pt=11),
    TextLabel(480, 155, "{{RSD_MODEL}}"),
    # Inverter
    TextLabel(660, 130, "{{INVERTER_LABEL}}", size_pt=11),
    TextLabel(660, 155, "{{INVERTER_MODEL}}"),
    TextLabel(660, 175, "{{INVERTER_AC}}"),
    # ESS unit (branch joining at inverter)
    TextLabel(660, 290, "{{ESS_LABEL}}", size_pt=11),
    TextLabel(660, 315, "Model: {{ESS_MODEL}}"),
    TextLabel(660, 335, "Qty {{ESS_QTY}} — {{ESS_KWH}}"),
    # AC disconnect
    TextLabel(840, 130, "{{AC_DISC_LABEL}}", size_pt=11),
    TextLabel(840, 155, "OCPD: {{AC_DISC_OCPD}}"),
    TextLabel(840, 175, "AC cond: {{ESS_AC_CONDUCTOR}}"),
    # Service / MSP
    TextLabel(1020, 130, "{{MSP_LABEL}}", size_pt=11),
    TextLabel(1020, 155, "{{MSP_RATING}}"),
    TextLabel(1020, 175, "Busbar: {{BUSBAR_RATING}}"),
    # Interconnection summary
    TextLabel(1020, 290, "Backfeed: {{TOTAL_BACKFEED}}"),
    TextLabel(1020, 310, "Method: {{INTERCONNECT_METHOD}}", size_pt=10),
    TextLabel(1020, 330, "Status: {{INTERCONNECT_STATUS}}", size_pt=10),
    # Section markers between devices
    TextLabel(200, 110, "── PV string ──", size_pt=8),
    TextLabel(400, 110, "── home run ──", size_pt=8),
    TextLabel(580, 110, "── post-RSD ──", size_pt=8),
    TextLabel(760, 110, "── inv AC ──", size_pt=8),
    TextLabel(940, 110, "── to MSP ──", size_pt=8),
    TextLabel(780, 250, "── battery DC ──", size_pt=8),
]


PROJECT_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<project title="Residential PV+ESS Template v0" version="0.80">
    <properties>
        <property show="1" name="savedfilename">residential-ess-v0</property>
        <property show="1" name="saveddate-us">2026-05-12</property>
    </properties>
    <newdiagrams>
        <border rowsize="80" rows="10" displaycols="true" cols="20" colsize="60" displayrows="true"/>
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
    <diagram freezeNewElement="false" cols="20" folio="%id/%total" version="0.80" indexrev="" date="null" author="pvess-calc" height="800" freezeNewConductor="false" title="Single Line Diagram" auto_page_num="" displaycols="true" filename="residential-ess-v0" colsize="60" order="1" displayrows="true" locmach="" rows="10" plant="" rowsize="80" displayAt="bottom">
        <defaultconductor condsize="1" cable="" onetextperfolio="0" vertical-alignment="AlignRight" horizrotatetext="0" bicolor="false" bus="" dash-size="1" numsize="9" horizontal-alignment="AlignBottom" function="" conductor_color="" conductor_section="" text_color="#000000" color2="#000000" tension_protocol="" displaytext="0" formula="" vertirotatetext="0" num="" type="multi"/>
        <elements/>
        <conductors/>
        <inputs>
{INPUTS}
        </inputs>
    </diagram>
</project>
"""


def build_v0_template(out_path: Path, labels: list[TextLabel] | None = None) -> None:
    used = labels if labels is not None else DEFAULT_LABELS
    inputs_xml = "\n".join(_input_xml(l) for l in used)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        PROJECT_TEMPLATE.format(INPUTS=inputs_xml),
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        __file__
    ).resolve().parents[3] / "library" / "templates" / "residential-ess-v0.qet"
    build_v0_template(target)
    print(f"wrote {target}")
