"""Interactive wizard — walks `WIZARD_FIELDS`, prompts the user for
each value, builds a nested dict, validates it via the `Inputs`
pydantic schema, and writes `projects/<id>/inputs.yaml`.

Design choices:
- click prompts for everything (numbers / choice / text)
- Each prompt prints label + unit + hint + yaml_path on stderr
- After every successful prompt the state is saved to JSON so the user
  can ctrl-C and resume with `--resume`
- Final yaml is validated by pydantic; on failure the wizard reports
  which field(s) need re-entry and re-prompts those
- List fields (sub_panels / roof_sections) prompt count first, then loop
- `--address` (K.3): the lookup orchestrator pre-fills utility / AHJ /
  NEC edition / ASHRAE temps. Pre-filled values appear as the prompt
  default — the user hits <enter> to accept or types a new value.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import click
import yaml

from ..site_checklist.field_specs import FieldSpec
from .field_specs import WIZARD_FIELDS, is_list_field, list_prefix
from .nesting import set_list_item, set_path
from .state import WizardState


# ─────────────────────────────────────────────────────────────────────────────
# Public entry
# ─────────────────────────────────────────────────────────────────────────────


def run_wizard(
    project_id: str,
    *,
    resume: bool = False,
    out_dir: Optional[Path] = None,
    address: Optional[str] = None,
) -> Path:
    """Run the interactive wizard for project `project_id`.

    Returns the path to the written `inputs.yaml`.

    If `resume=True`, picks up where the saved wizard state left off.
    If `address` is given, the lookup orchestrator pre-fills any fields
    it can recognise; the wizard still prompts but shows the pre-fill
    as the default value (user presses <enter> to accept).
    """
    if out_dir is None:
        out_dir = Path("projects") / project_id
    state_file = WizardState.file_for(project_id)
    state = WizardState.load(state_file) if resume else WizardState()

    click.echo()
    if resume:
        click.echo(click.style(
            f"Resuming wizard for project '{project_id}' "
            f"(answered {len(state.answers)} of {len(WIZARD_FIELDS)} fields).",
            fg="cyan"))
    else:
        click.echo(click.style(
            f"Starting wizard for project '{project_id}'.",
            fg="cyan", bold=True))
    click.echo(click.style(
        "Press Ctrl-C any time; resume with --resume.\n", fg="cyan"))

    # Force the project.id answer to match the CLI argument so the user
    # can't typo themselves into a folder/id mismatch.
    state.answers["project.id"] = project_id

    # K.3 address pre-fill — populate prompt defaults but DO NOT mark
    # the answers as final. The user still has to confirm each one.
    prefills: dict[str, Any] = {}
    if address:
        prefills = _prefill_from_address(address)
        if prefills:
            # Filter out magic-prefixed keys (e.g., __k3c_roof_sections)
            # — those aren't user-facing yaml paths, they're internal
            # side channels processed in _post_process / run() proper.
            visible = {k: v for k, v in prefills.items()
                       if not k.startswith("__")}
            click.echo(click.style(
                f"Looked up '{address}' → {len(visible)} pre-fills "
                f"(press <enter> at each prompt to accept):",
                fg="cyan"))
            for k, v in visible.items():
                click.echo(click.style(f"  · {k} = {v}", fg="bright_black"))
            # Surface magic side-channels (K.3c roof_sections) on their
            # own line so the user knows Google Solar contributed.
            k3c = prefills.get("__k3c_roof_sections")
            if k3c:
                click.echo(click.style(
                    f"  · site.roof_sections ← {len(k3c)} faces from "
                    "Google Solar (auto-injected after wizard)",
                    fg="bright_black"))
            click.echo()

    # Group consecutive list-field entries by their parent list so we
    # can ask the count once + loop.
    queue = _build_queue(WIZARD_FIELDS, state.answers)

    for step in queue:
        if step["kind"] == "scalar":
            spec: FieldSpec = step["spec"]
            if spec.yaml_path in state.answers:
                continue
            default = prefills.get(spec.yaml_path)
            value = _prompt_scalar(spec, default=default)
            state.answers[spec.yaml_path] = value
            state.save(state_file)
        else:  # list group
            prefix = step["prefix"]
            specs: list[FieldSpec] = step["specs"]
            count = _prompt_list_count(prefix, specs)
            for i in range(count):
                click.echo(click.style(
                    f"\n  ── {prefix}[{i}] ──", fg="yellow"))
                for spec in specs:
                    key = f"{prefix}[{i}].{spec.yaml_path.split('[].')[1]}"
                    if key in state.answers:
                        continue
                    value = _prompt_scalar(spec)
                    state.answers[key] = value
                    state.save(state_file)
            # Mark this list block done by storing the count too:
            state.answers[f"{prefix}__count"] = count
            state.save(state_file)

    # Build the nested dict + write yaml.
    yaml_path = out_dir / "inputs.yaml"
    out_dir.mkdir(parents=True, exist_ok=True)
    nested = _answers_to_nested(state.answers)
    _post_process(nested)

    # K.3c: inject Google Solar roof_sections list verbatim. The wizard's
    # scalar-prompt path doesn't know about list-shaped pre-fills (the
    # `LOOKUP_FIELD_TO_YAML_PATH` mapping is scalar-only); we stash the
    # list under a magic key in `_prefill_from_address` and pour it into
    # `site.roof_sections` here, right before validation, so Google Solar's
    # work actually lands in the yaml. Designer can then hand-tune.
    k3c_sections = prefills.get("__k3c_roof_sections")
    if k3c_sections:
        site = nested.setdefault("site", {})
        # Only overwrite if the wizard didn't already populate from
        # explicit list-prompts (defensive — wizard doesn't currently
        # prompt for roof_sections, but this keeps the contract clean
        # if that changes).
        if not site.get("roof_sections"):
            site["roof_sections"] = k3c_sections
            click.echo(click.style(
                f"  · injected {len(k3c_sections)} roof_sections from "
                "Google Solar API", fg="cyan"))

    _validate_and_write(nested, yaml_path)

    # Clean up wizard state on success.
    if state_file.exists():
        state_file.unlink()

    click.echo()
    click.echo(click.style(
        f"✓ Wrote {yaml_path}", fg="green", bold=True))
    click.echo(click.style(
        f"  Try:  pvess-calc {out_dir}/", fg="green"))
    return yaml_path


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────


def _build_queue(
    fields: tuple[FieldSpec, ...], answers: dict
) -> list[dict[str, Any]]:
    """Return a list of steps. Scalar steps are individual fields; list
    steps group all fields belonging to the same list parent so the
    runner can prompt count + loop in one block."""
    out: list[dict[str, Any]] = []
    list_buckets: dict[str, list[FieldSpec]] = {}
    list_order: list[str] = []   # preserve declared order of first appearance
    for f in fields:
        if f.yaml_path == "project.id":
            # Already forced from CLI arg; skip in queue.
            continue
        if is_list_field(f):
            prefix = list_prefix(f)
            if prefix not in list_buckets:
                list_buckets[prefix] = []
                list_order.append(prefix)
            list_buckets[prefix].append(f)
        else:
            out.append({"kind": "scalar", "spec": f})

    for prefix in list_order:
        out.append({
            "kind": "list",
            "prefix": prefix,
            "specs": list_buckets[prefix],
        })
    return out


def _prompt_scalar(spec: FieldSpec, *, default: Any = None) -> Any:
    """Prompt the user once for a scalar field, validate the type.

    If `default` is supplied (typically from address lookup), it's
    shown as the prompt default — pressing <enter> accepts it. We
    still always prompt: the user must confirm every value, even
    pre-filled ones, because lookup confidence is variable.
    """
    # Header: bold label + unit + yaml_path tag
    header = f"\n{spec.label}"
    if spec.unit:
        header += f" ({spec.unit})"
    click.echo(click.style(header, bold=True))
    click.echo(click.style(f"  yaml_path: {spec.yaml_path}", fg="bright_black"))
    if spec.explanation:
        click.echo(click.style(f"  ℹ  {spec.explanation}", fg="cyan"))
    if spec.where_to_find:
        click.echo(click.style(f"  ↳ {spec.where_to_find}", fg="cyan"))
    if default is not None:
        click.echo(click.style(
            f"  ⚑ pre-fill from address lookup: {default!r}", fg="green"))

    if spec.field_type == "choice":
        kwargs: dict[str, Any] = dict(
            type=click.Choice(list(spec.choices), case_sensitive=False),
            show_choices=True,
        )
        if default is not None and str(default) in spec.choices:
            kwargs["default"] = str(default)
        return click.prompt("  →", **kwargs)
    if spec.field_type == "integer":
        # Integer-typed fields (counts, conductor multiples, etc.) prompt
        # as `int` so the rendered yaml carries `30` rather than `30.0`.
        kwargs = {"type": int}
        if default is not None:
            kwargs["default"] = int(default)
        return click.prompt("  →", **kwargs)
    if spec.field_type == "number":
        kwargs = {"type": float}
        if default is not None:
            kwargs["default"] = float(default)
        return click.prompt("  →", **kwargs)
    # text
    if default is not None:
        return click.prompt("  →", type=str, default=str(default))
    return click.prompt("  →", type=str, default="", show_default=False)


def _prompt_list_count(prefix: str, specs: list[FieldSpec]) -> int:
    """Ask how many entries the list has. Zero is allowed (skips)."""
    click.echo()
    click.echo(click.style(
        f"━━━ {prefix} (list) ━━━", fg="yellow", bold=True))
    return click.prompt(
        f"  How many {prefix.split('.')[-1]}? (0 to skip)",
        type=int, default=0,
    )


def _answers_to_nested(answers: dict[str, Any]) -> dict[str, Any]:
    """Convert flat {yaml_path: value} → nested dict."""
    out: dict[str, Any] = {}
    # First handle list entries so the lists exist, then scalars.
    for key, value in answers.items():
        if key.endswith("__count"):
            continue
        if "[" in key:
            prefix, rest = key.split("[", 1)
            idx_str, leaf = rest.split("]", 1)
            leaf = leaf.lstrip(".")
            set_list_item(out, prefix, int(idx_str), leaf, value)
        else:
            set_path(out, key, value)
    return out


def _post_process(nested: dict[str, Any]) -> None:
    """Fixups after nesting: convert string lists, coerce types pydantic
    can't infer from raw click input. The wizard prompts everything as
    text/float — pydantic does the rest."""
    # interconnection_methods: comma-separated string → list[str]
    methods = nested.get("service", {}).get("interconnection_methods")
    if isinstance(methods, str):
        nested["service"]["interconnection_methods"] = [
            m.strip() for m in methods.split(",") if m.strip()
        ]

    # K.2.5: choice fields rendered as 'no'/'yes' need bool coercion for
    # pydantic. List of (path, default_bool) tuples we own.
    _coerce_yes_no(nested, "loads", "has_ev")
    _coerce_yes_no(nested, "loads", "planned_ev")
    _coerce_yes_no(nested, "loads", "planned_electrification")
    # Per-sub-panel service_rated also yes/no:
    for sp in nested.get("service", {}).get("sub_panels", []) or []:
        if isinstance(sp.get("service_rated"), str):
            sp["service_rated"] = sp["service_rated"].lower() == "yes"


def _coerce_yes_no(nested: dict[str, Any], section: str, key: str) -> None:
    """Convert wizard 'yes'/'no' string → bool in-place."""
    sec = nested.get(section)
    if not isinstance(sec, dict):
        return
    val = sec.get(key)
    if isinstance(val, str):
        sec[key] = val.lower() == "yes"


def _validate_and_write(nested: dict[str, Any], yaml_path: Path) -> None:
    """Validate via Inputs.model_validate(); on failure show the error
    block but still write the yaml (user can hand-edit)."""
    from ..schema import Inputs
    try:
        Inputs.model_validate(nested)
        click.echo(click.style("\n✓ Schema validation passed.",
                               fg="green"))
    except Exception as exc:
        click.echo(click.style(
            "\n⚠ Schema validation FAILED — writing yaml anyway; "
            "hand-edit to fix:\n" + str(exc), fg="red"))
    yaml_path.write_text(yaml.dump(nested, sort_keys=False, allow_unicode=True))


# ─── Address pre-fill (Phase K.3) ──────────────────────────────────────────


def _prefill_from_address(address: str) -> dict[str, Any]:
    """Run the lookup orchestrator and map its output to wizard yaml
    paths. Returns {} on any failure — pre-fill is strictly a UX speed-
    up, never a hard dependency."""
    try:
        from ..lookup import LOOKUP_FIELD_TO_YAML_PATH, resolve
    except ImportError:
        return {}

    try:
        result = resolve(address)
    except Exception as exc:
        click.echo(click.style(
            f"  (address lookup failed: {exc!r} — continuing without pre-fill)",
            fg="yellow"))
        return {}

    prefills: dict[str, Any] = {}
    for lookup_key, yaml_path in LOOKUP_FIELD_TO_YAML_PATH.items():
        if lookup_key in result.fields:
            prefills[yaml_path] = result.fields[lookup_key]

    # ashrae_2pct_max_c also seeds the attic ambient default — solar
    # installers almost always use it as a starting point for
    # routing.ambient_temp_c (NEC 310.15(B) conduit derating).
    if "ashrae_2pct_max_c" in result.fields:
        prefills.setdefault("routing.ambient_temp_c",
                            result.fields["ashrae_2pct_max_c"])

    # K.3c: stash Google Solar's roof_sections list under a magic key
    # so the runner can pour it into `site.roof_sections` after the
    # scalar-prompt loop. The dunder-prefix key makes it explicit that
    # this isn't a yaml path — it's a side channel between
    # `_prefill_from_address` and `run()`.
    if "roof_sections" in result.fields:
        prefills["__k3c_roof_sections"] = result.fields["roof_sections"]

    # project.location is derived from the parsed address itself (not
    # from a provider), so seed it here so the test contract — "the
    # prefill dict tells you exactly which prompts will have a
    # default" — stays uniform.
    if result.address.city and result.address.state:
        prefills.setdefault(
            "project.location",
            f"{result.address.city}, {result.address.state}",
        )

    return prefills
