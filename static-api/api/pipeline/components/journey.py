"""Record every stage of a discovery run as a STAGE CARD, the unit the MEIDNet Matter interface will be designed from.

A card says, in the user's terms, what the stage is for, what the user had to provide or decide, the numbers they should
see, a PASS / WARN / FAIL verdict with its reason in plain language, how long it took, and which concept of the Matter
0.2.0 app (reference/matter_0.2.0_space_source/api) it belongs to -- or that the app has nothing for it yet.
Cards are written twice, so the run can be rendered by a UI later and read by people now:
  <run_dir>/cards/<NN>_<key>.json               machine-readable, one per stage
  <run_dir>/UI_JOURNEY.md and meidnet_journey/UI_JOURNEY.md   human-readable, appended stage by stage
"""
import datetime, json, os

JOURNEY = os.environ.get("MEIDNET_JOURNEY_FILE")   # optional: the human-readable journey document to append to
VERDICT_ICON = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL", "INFO": "INFO"}


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.3g}"
    if isinstance(v, (list, tuple)):
        return ", ".join(_fmt(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_fmt(x)}" for k, x in v.items())
    return str(v)


def card_markdown(c, run_tag):
    lines = [f"### {c['nn']:02d} {c['title']} — **{c['verdict']}** ({run_tag})", "",
             f"*Purpose:* {c['purpose']}  ", f"*Verdict:* {c['reason']}  ",
             f"*Matter:* {c['matter']}" + (" — **not in the app yet**" if c.get("matter_new") else "") + "  ",
             f"*Time:* {c['seconds']:.0f} s" if c.get("seconds") is not None else "*Time:* n/a", ""]
    if c.get("inputs"):
        lines += ["*Inputs:* " + _fmt(c["inputs"]), ""]
    for d in c.get("decisions") or []:
        lines += [f"*Decision — {d['question']}* options: {_fmt(d.get('options', []))}; default **{d.get('default')}**; "
                  f"chosen **{d.get('chosen')}**. {d.get('why', '')}", ""]
    if c.get("metrics"):
        lines += ["| shown to the user | value |", "|---|---|"] + [f"| {k} | {_fmt(v)} |" for k, v in c["metrics"].items()] + [""]
    for w in c.get("warnings") or []:
        lines += [f"- warning: {w}"]
    if c.get("ui_notes"):
        lines += ["", f"*UI note:* {c['ui_notes']}"]
    lines += [""]
    return "\n".join(lines)


def write_card(run_dir, nn, key, title, purpose, matter, verdict, reason, metrics=None, decisions=None, inputs=None,
               warnings=None, artefacts=None, seconds=None, ui_notes=None, matter_new=False, run_tag=None):
    """Write one stage card (JSON) and append its human-readable form to the run and the project journey."""
    assert verdict in VERDICT_ICON, verdict
    c = dict(nn=nn, key=key, title=title, purpose=purpose, matter=matter, matter_new=matter_new, verdict=verdict,
             reason=reason, metrics=metrics or {}, decisions=decisions or [], inputs=inputs or {}, warnings=warnings or [],
             artefacts=artefacts or [], seconds=seconds, ui_notes=ui_notes,
             written=datetime.datetime.now().isoformat(timespec="seconds"))
    os.makedirs(os.path.join(run_dir, "cards"), exist_ok=True)
    path = os.path.join(run_dir, "cards", f"{nn:02d}_{key}.json")
    json.dump(c, open(path, "w"), indent=1, default=str)
    tag = run_tag or os.path.basename(os.path.normpath(run_dir))
    md = card_markdown(c, tag)
    for target in (os.path.join(run_dir, "UI_JOURNEY.md"), JOURNEY):
        if not target:                      # the project-wide journey file is optional (MEIDNET_JOURNEY_FILE)
            continue
        with open(target, "a", encoding="utf-8") as f:
            f.write(md + "\n")
    return path
