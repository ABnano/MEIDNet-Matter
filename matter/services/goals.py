"""From a goal to the engine's generation settings, and the checks before anything runs.

    translate(goal, artefacts)           -> the generation section + the sentences that explain each translation
    validate(goal, services)             -> ValidatedGoal (config, family, notes) or GoalInvalid with field messages
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from matter.api.errors import ApiError
from matter.schemas.goal import Goal
from matter.services import families as F
from matter.services.support import effective_stats, fmt

WEIGHTS = {"primary": (10000.0, 1.0), "secondary": (6000.0, 0.4), "tertiary": (3000.0, 0.2)}
PUBLIC_LIMITS = {"per_target": 6, "population": 32, "rounds": 6, "steps": 400, "targets": 2}
LOCAL_MAX_TARGETS = 8
PUBLIC_RULE_PARAMS = ("min", "max", "low", "high", "cutoff")
PUBLIC_MAX_CUTOFF = 8.0
MAX_WINDOWS = 4


class GoalInvalid(ApiError):
    def __init__(self, fields: list[dict], message: str = "the goal cannot run as written"):
        super().__init__("validation_error", message, status=422, fields=fields)


@dataclass
class Translation:
    generation: dict
    explained: list[str] = field(default_factory=list)
    windows: list[dict] = field(default_factory=list)
    targets_per_property: dict = field(default_factory=dict)


@dataclass
class ValidatedGoal:
    goal: Goal
    generation: dict
    config: object                 # meidnet MEIDNetConfig
    family: object                 # meidnet Family with the goal's filters applied
    notes: list[str]
    explained: list[str]
    windows: list[dict]
    estimated_seconds: float


def estimated_seconds(gen: dict) -> float:
    """The Studio's estimate for a CPU search: 3 + rounds * (steps * 0.0022 * population + 0.04 * population) per target."""
    per_target = 3 + gen["rounds"] * (gen["steps"] * 0.0022 * gen["population"] + 0.04 * gen["population"])
    return round(per_target * max(1, len(gen["targets"])), 1)


def translate(goal: Goal, artefacts) -> Translation:
    objectives, windows, explained, per_prop = [], [], [], {}
    for o in goal.objectives:
        p = artefacts.property(o.property)
        label, unit = p["label"], p["unit"]
        w, sw = WEIGHTS[o.priority]
        loss = o.loss or "l2"
        basis, s = effective_stats(p)
        if o.kind == "value":
            objectives.append({"property": o.property, "loss": loss, "weight": w, "select_weight": sw})
            per_prop[o.property] = [o.value]
            if o.tolerance:
                windows.append({"name": "property_window", "property": o.property, "min": o.value - o.tolerance, "max": o.value + o.tolerance})
                explained.append(f"{label}: search for {fmt(o.value, unit)}; keep candidates predicted within ± {fmt(o.tolerance, unit)}.")
            else:
                explained.append(f"{label}: search for {fmt(o.value, unit)}.")
        elif o.kind == "values":
            objectives.append({"property": o.property, "loss": loss, "weight": w, "select_weight": sw})
            per_prop[o.property] = list(o.values)
            explained.append(f"{label}: one search target per value ({', '.join(fmt(v) for v in o.values)} {unit}).")
            if o.tolerance:
                explained.append(f"{label}: the accepted window ± {fmt(o.tolerance, unit)} is applied per target after the search.")
        elif o.kind == "range":
            mid = (o.low + o.high) / 2
            objectives.append({"property": o.property, "loss": loss, "weight": w, "select_weight": sw})
            per_prop[o.property] = [mid]
            windows.append({"name": "property_window", "property": o.property, "min": o.low, "max": o.high})
            explained.append(f"{label}: search for the middle of {fmt(o.low)}–{fmt(o.high, unit)} ({fmt(mid, unit)}); keep candidates predicted inside the range.")
        elif o.kind in ("at_least", "at_most"):
            objectives.append({"property": o.property, "loss": o.kind, "weight": w, "select_weight": sw})
            per_prop[o.property] = [o.value]
            bound = {"min": o.value} if o.kind == "at_least" else {"max": o.value}
            windows.append({"name": "property_window", "property": o.property, **bound})
            explained.append(f"{label}: {'at least' if o.kind == 'at_least' else 'at most'} {fmt(o.value, unit)}; candidates predicted beyond it are dropped.")
        else:                                   # maximize / minimize: a bound at the edge of the training distribution
            edge = s["percentiles"]["p99"] if o.kind == "maximize" else s["percentiles"]["p1"]
            kind = "at_least" if o.kind == "maximize" else "at_most"
            objectives.append({"property": o.property, "loss": kind, "weight": w, "select_weight": sw})
            per_prop[o.property] = [edge]
            windows.append({"name": "property_window", "property": o.property, **({"min": edge} if kind == "at_least" else {"max": edge})})
            which = "99th" if o.kind == "maximize" else "1st"
            explained.append(f"{label}: '{o.kind}' is run as '{kind.replace('_', ' ')} {fmt(edge, unit)}', the {which} percentile of "
                             f"the training values{' (non-zero values)' if basis == 'nonzero' else ''}.")
    # one search target per combination of the listed values
    props = [o.property for o in goal.objectives]
    targets = [dict(zip(props, combo)) for combo in itertools.product(*(per_prop[p] for p in props))]
    exclude = list(dict.fromkeys(goal.elements.exclude + [e for k in goal.elements.presets for e in F.PRESETS.get(k, {}).get("elements", [])]))
    b = goal.budget
    gen = {"family": goal.family, "variant": goal.variant, "objectives": objectives, "targets": targets,
           "per_target": b.per_target, "population": b.population, "rounds": b.rounds, "steps": b.steps, "seed": b.seed,
           "min_cosine_sep": b.min_cosine_sep, "exclude_elements": exclude, "only_elements": dict(goal.elements.only),
           "overrides": {k: dict(v) for k, v in goal.rule_overrides.items()}, "extra_constraints": windows,
           "disabled_rules": list(goal.disabled_rules), "output_prefix": goal.variant or goal.family}
    if goal.diverse_set:
        gen["per_target"] = max(gen["per_target"], 3)
        gen["min_cosine_sep"] = min(gen["min_cosine_sep"], 0.98)
        explained.append("A diverse set is requested: at least 3 candidates per target, kept at least 2 % apart in the latent space.")
    if exclude:
        explained.append(f"Excluded elements: {', '.join(exclude)}.")
    return Translation(gen, explained, windows, per_prop)


def apply_limits(gen: dict, public: bool, notes: list[str]) -> dict:
    """On a shared host: the Studio's caps, with a note for every value that was changed."""
    cap_targets = PUBLIC_LIMITS["targets"] if public else LOCAL_MAX_TARGETS
    if len(gen["targets"]) > cap_targets:
        notes.append(f"targets: {len(gen['targets'])} → {cap_targets} (limit {'on this shared server' if public else 'per run'})")
        gen["targets"] = gen["targets"][:cap_targets]
    if not public:
        return gen
    for k in ("per_target", "population", "rounds", "steps"):
        if gen[k] > PUBLIC_LIMITS[k]:
            notes.append(f"{k}: {gen[k]} → {PUBLIC_LIMITS[k]} (limit on this shared server)")
            gen[k] = PUBLIC_LIMITS[k]
    kept = {}
    for rule, params in gen["overrides"].items():
        limits = {p: v for p, v in params.items() if p in PUBLIC_RULE_PARAMS}
        if len(limits) != len(params):
            notes.append(f"overrides of {rule}: only the limits {', '.join(PUBLIC_RULE_PARAMS)} can be changed on this shared server")
        if limits.get("cutoff") is not None:
            limits["cutoff"] = max(1.0, min(float(limits["cutoff"]), PUBLIC_MAX_CUTOFF))
        if limits:
            kept[rule] = limits
    gen["overrides"] = kept
    if len(gen["extra_constraints"]) > MAX_WINDOWS:
        notes.append(f"only {MAX_WINDOWS} predicted-property windows are applied on this shared server")
        gen["extra_constraints"] = gen["extra_constraints"][:MAX_WINDOWS]
    return gen


def _loc_map(loc: str) -> str:
    """A pydantic location inside the generation section, written as the goal field it came from."""
    parts = loc.split(".")
    if parts and parts[0] == "generation":
        parts = parts[1:]
    head = parts[0] if parts else ""
    if head == "objectives" and len(parts) >= 2:
        return f"objectives.{parts[1]}" + (f".{parts[2]}" if len(parts) > 2 else "")
    return {"exclude_elements": "elements.exclude", "only_elements": "elements.only", "overrides": "rule_overrides",
            "extra_constraints": "objectives", "targets": "objectives", "per_target": "budget.per_target", "population": "budget.population",
            "rounds": "budget.rounds", "steps": "budget.steps", "seed": "budget.seed", "min_cosine_sep": "budget.min_cosine_sep"}.get(head, head)


def validate(goal: Goal, services, run_dir: str | None = None) -> ValidatedGoal:
    from pydantic import ValidationError
    from meidnet.config import config_from_dict
    from meidnet.pipeline import family_for

    artefacts, registry, settings = services.artefacts, services.registry, services.settings
    fields = []
    model_id = goal.model_id or artefacts.project["default_model"]
    if model_id not in registry.ids():
        raise GoalInvalid([{"loc": "model_id", "msg": f"unknown model '{model_id}'; this project has {', '.join(registry.ids())}"}])
    entry = registry.entry(model_id)
    columns = [p["column"] for p in entry["properties"]]
    for i, o in enumerate(goal.objectives):
        if o.property not in columns:
            fields.append({"loc": f"objectives.{i}.property", "msg": f"'{o.property}' is not predicted by this model (it predicts {', '.join(columns)})"})
    if fields:
        raise GoalInvalid(fields)
    if goal.elements.presets:
        unknown = [k for k in goal.elements.presets if k not in F.PRESETS]
        if unknown:
            raise GoalInvalid([{"loc": "elements.presets", "msg": f"unknown preset {', '.join(unknown)}; available: {', '.join(F.PRESETS)}"}])
    t = translate(goal, artefacts)
    notes: list[str] = []
    gen = apply_limits(t.generation, settings.public, notes)
    raw = {"name": "matter", "output_dir": run_dir or settings.run_root, "model_path": registry.path(model_id), "generation": gen}
    try:
        cfg = config_from_dict(raw, base_dir=settings.run_root)
    except ValidationError as e:
        raise GoalInvalid([{"loc": _loc_map(".".join(str(x) for x in err["loc"])), "msg": err["msg"]} for err in e.errors()]) from None
    try:
        fam = family_for(cfg, need_variant=True)
    except SystemExit as e:
        msg = str(e.code if e.code is not None else e)
        loc = "elements.exclude" if "no element" in msg.lower() or "empty" in msg.lower() else ("disabled_rules" if "disabled_rules" in msg else "variant")
        raise GoalInvalid([{"loc": loc, "msg": msg}]) from None
    if goal.max_elements is not None and goal.max_elements < len(fam.groups):
        raise GoalInvalid([{"loc": "max_elements", "msg": f"the {fam.title} always has {len(fam.groups)} elements"}])
    if fam.n_sites > entry["max_sites"]:
        raise GoalInvalid([{"loc": "family", "msg": f"{fam.title} has {fam.n_sites} sites; this model handles up to {entry['max_sites']}"}])
    named = {c.get("property") for c in fam.constraints if c["name"] == "property_window"}
    unknown = sorted(str(p) for p in named if p not in columns)
    if unknown:
        raise GoalInvalid([{"loc": "objectives", "msg": f"{', '.join(unknown)}: not predicted by this model"}])
    return ValidatedGoal(goal, gen, cfg, fam, notes, t.explained, t.windows, estimated_seconds(gen))


def summary_text(goal: Goal, artefacts) -> str:
    """The one-line query text: 'Eg 2 ± 0.3 eV · Ef ≤ 1 eV/atom · Pb-free · oxide perovskite'."""
    parts = []
    for o in goal.objectives:
        p = artefacts.dataset["properties"].get(o.property) or {"label": o.property, "unit": ""}
        short, unit = short_label(p["label"]), p["unit"]
        if o.kind == "value":
            parts.append(f"{short} {fmt(o.value)}" + (f" ± {fmt(o.tolerance)}" if o.tolerance else "") + f" {unit}")
        elif o.kind == "values":
            parts.append(f"{short} " + "/".join(fmt(v) for v in o.values) + f" {unit}")
        elif o.kind == "range":
            parts.append(f"{short} {fmt(o.low)}–{fmt(o.high)} {unit}")
        elif o.kind == "at_least":
            parts.append(f"{short} ≥ {fmt(o.value)} {unit}")
        elif o.kind == "at_most":
            parts.append(f"{short} ≤ {fmt(o.value)} {unit}")
        else:
            parts.append(f"{o.kind} {short}")
    exclude = list(dict.fromkeys(goal.elements.exclude + [e for k in goal.elements.presets for e in F.PRESETS.get(k, {}).get("elements", [])]))
    if exclude == ["Pb"]:
        parts.append("Pb-free")
    elif exclude:
        parts.append("no " + ", ".join(exclude))
    for g, els in goal.elements.only.items():
        parts.append(f"{g} in {', '.join(els)}")
    fam = {"perovskite_abx3": "perovskite", "double_perovskite_a2bbx6": "double perovskite"}.get(goal.family, goal.family)
    parts.append(f"{goal.variant + ' ' if goal.variant else ''}{fam}")
    return " · ".join(p.strip() for p in parts)


def short_label(label: str) -> str:
    low = label.lower()
    if "gap" in low:
        return "Eg"
    if "formation" in low or "enthalpy" in low:
        return "ΔHf"
    return label
