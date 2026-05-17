"""Read .qet (QElectroTech project) XML files.

QET files are valid XML. We use lxml so that parse → modify → serialize keeps
the original structure intact and editable in the QET GUI afterwards.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from lxml import etree


def parse(path: Path) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=False)
    return etree.parse(str(path), parser)


def write(tree: etree._ElementTree, path: Path) -> None:
    tree.write(
        str(path),
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )


def iter_text_elements(tree: etree._ElementTree) -> Iterator[etree._Element]:
    """Yield every QET element that holds editable text.

    QET stores free text annotations as `<input>` elements, structured
    element-info text as `<dynamic_text>` / `<elementInformation>`, and the
    cached display text of an element's `<dynamic_elmt_text>` as a `<text>`
    child. We yield each node that may carry a `{{...}}` placeholder so the
    injector can substitute it.
    """
    root = tree.getroot()
    for tag in ("input", "dynamic_text", "elementInformation", "text"):
        for el in root.iter(tag):
            yield el
