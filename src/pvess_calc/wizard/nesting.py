"""Flat-path → nested-dict converter for the wizard.

The wizard collects answers as `{yaml_path: value}` (flat). Pydantic
schema parsing needs nested dicts. This module bridges them.

Examples:

    >>> set_path({}, "project.id", "abc-001")
    {'project': {'id': 'abc-001'}}

    >>> set_list_item({}, "service.sub_panels", 0, "name", "Sub Panel #1")
    {'service': {'sub_panels': [{'name': 'Sub Panel #1'}]}}
"""
from __future__ import annotations

from typing import Any


def set_path(out: dict[str, Any], dotted: str, value: Any) -> dict[str, Any]:
    """Set `value` at `dotted` path inside `out`, creating intermediate
    dicts as needed. Returns `out` for chaining."""
    parts = dotted.split(".")
    cur: dict = out
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
        if not isinstance(cur, dict):
            raise ValueError(
                f"path collision at {dotted!r}: {p} is not a dict")
    cur[parts[-1]] = value
    return out


def set_list_item(
    out: dict[str, Any], list_prefix: str, index: int,
    leaf_field: str, value: Any,
) -> dict[str, Any]:
    """Set `value` at `<list_prefix>[index].<leaf_field>` inside `out`.

    `list_prefix` is the path UP TO (not including) the list (e.g.
    `service.sub_panels`). The list is created if missing, extended to
    cover `index` if needed, and the indexed entry's `leaf_field` is
    assigned.
    """
    parts = list_prefix.split(".")
    cur: dict = out
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    list_name = parts[-1]
    lst = cur.setdefault(list_name, [])
    while len(lst) <= index:
        lst.append({})
    if not isinstance(lst[index], dict):
        raise ValueError(
            f"list[{index}] is not a dict: cannot set {leaf_field}")
    # leaf_field may itself be dotted (rare); use set_path on the row.
    set_path(lst[index], leaf_field, value)
    return out
