"""
The ``meidnet`` command.

    meidnet init            write a starter meidnet.yaml next to your data
    meidnet check  CONFIG   is my data usable?            → check_report.html
    meidnet train  CONFIG   learn the latent space        → model.pt, training_report.html
    meidnet generate CONFIG design candidates             → CIFs, generation_report.html
    meidnet studio CONFIG   interactive design workbench in your browser
    meidnet demo            5-minute demo with the published perovskite model
    meidnet screen DIR      stability screening of CIFs with MACE (optional extra)
    meidnet info MODEL      describe a checkpoint
    meidnet families        list material families
    meidnet schema          JSON Schema of the config (for editors and the Studio)
    meidnet download-data   fetch the Perov-5 dataset used in the paper
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap

from meidnet import __version__

PEROV5_URL = "https://raw.githubusercontent.com/txie-93/cdvae/main/data/perov_5/{split}.csv"
CKPT_URL = "https://github.com/ABnano/MEIDNet/raw/main/checkpoints/dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth"
CKPT_NAME = "dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth"


def _cfg(path):
    from meidnet.config import load_config
    from meidnet.pipeline import load_plugins
    cfg = load_config(path)
    load_plugins(cfg.plugins, cfg.resolve)
    return cfg


def published_checkpoint() -> str:
    """Path to the published Perov-5 checkpoint; downloads it to ~/.meidnet if needed."""
    for cand in (os.path.join("checkpoints", CKPT_NAME),
                 os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "checkpoints", CKPT_NAME)):
        if os.path.exists(cand):
            return cand
    cache = os.path.join(os.path.expanduser("~"), ".meidnet", CKPT_NAME)
    if not os.path.exists(cache):
        import urllib.request
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        print(f"downloading the published MEIDNet model (2.8 MB) to {cache} ...")
        urllib.request.urlretrieve(CKPT_URL, cache)
    return cache


# ───────────────────────── init ─────────────────────────
TEMPLATE_CUSTOM = """\
# MEIDNet configuration — edit the values, keep the structure.
# Every setting is explained at https://babu09-meidnet.hf.space/docs/reference/config.html
name: {name}
description: ""
output_dir: runs/{{name}}

data:
  table: {table}                 # CSV/Excel with one row per material
  id_column: {id_column}
  cif_column: {cif_column}       # column holding CIF text ... or use structures_dir
  # structures_dir: structures/  # folder of <id>.cif files (set cif_column: null)
  properties:
{properties}
  val_fraction: 0.1
  max_sites: 20
  align_to_prototype: true       # re-order atoms to the family prototype (needed for generation)

model:
  latent_dim: 128

training:
  epochs: 200
  batch_size: 16
  device: auto

generation:
  family: {family}
  variant: {variant}
  objectives:
{objectives}
  targets:
{targets}
  per_target: 4
  population: 48
  rounds: 20
  steps: 800
  exclude_elements: []           # e.g. [Pb, Cd]
  # only_elements: {{B: [Ti, Zr, Hf]}}
  # overrides: {{tolerance_factor: {{min: 0.8, max: 1.0}}}}
"""

TEMPLATE_PEROV5 = """\
# MEIDNet configuration reproducing the published Perov-5 experiment.
# Data: `meidnet download-data` fetches the CDVAE Perov-5 split into data/perov5/.
name: perov5
description: Cubic ABX3 perovskites, band gap + formation enthalpy (Perov-5)
output_dir: runs/{name}

data:
  table: data/perov5/train.csv
  id_column: material_id
  cif_column: cif
  properties:
    - {column: heat_all, label: Formation enthalpy, unit: eV/atom, normalize: false}
    - {column: dir_gap,  label: Direct band gap,    unit: eV,      normalize: false}
  val_table: data/perov5/val.csv
  max_sites: 20
  align_to_prototype: false      # the published model used atoms in file order

training:
  epochs: 200
  batch_size: 16
  contrastive_warmup_epochs: 1200
  device: auto

generation:
  family: perovskite_abx3
  variant: halide
  objectives:
    - {property: dir_gap,  loss: l2, weight: 10000, select_weight: 1.0}
    - {property: heat_all, loss: l1, weight: 6000,  select_weight: 0.4}
  targets:
    - {dir_gap: 1.5, heat_all: -0.10}
    - {dir_gap: 2.5, heat_all: -0.10}
    - {dir_gap: 3.5, heat_all: -0.10}
  per_target: 4
  population: 48
  rounds: 20
  steps: 800
"""


def cmd_init(a):
    path = a.output
    if os.path.exists(path) and not a.force:
        sys.exit(f"{path} already exists (use --force to overwrite)")
    if a.template == "perov5":
        text = TEMPLATE_PEROV5
    else:
        props = a.properties or ["band_gap"]
        pl = "\n".join(f"    - {{column: {p}, unit: \"\"}}" for p in props)
        ol = "\n".join(f"    - {{property: {p}, loss: l2, weight: 10000}}" for p in props)
        tl = ("    - {" + ", ".join(f"{p}: 0.0" for p in props) + "}"
              "   # ← set your target values (check_report.html shows the training range)")
        text = TEMPLATE_CUSTOM.format(name=a.name, table=a.table, id_column=a.id_column, cif_column=a.cif_column,
                                      properties=pl, family=a.family, variant=a.variant or "null",
                                      objectives=ol, targets=tl)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {path}\nnext: meidnet check {path}")


def cmd_check(a):
    from meidnet.pipeline import check
    cfg = _cfg(a.config)
    info = check(cfg)
    rep = info["report"]
    print(f"\n{rep.kept} of {rep.rows} materials usable.")
    for reason, n in rep.skipped.most_common():
        print(f"  skipped {n:>6}  {reason}   e.g. {', '.join(rep.examples.get(reason, []))}")
    print(f"report: {info['report_path']}")


def cmd_train(a):
    from meidnet.pipeline import train
    train(_cfg(a.config), epochs=a.epochs)


def cmd_generate(a):
    from meidnet.pipeline import generate
    cfg = _cfg(a.config)
    if a.model:
        cfg.model_path = os.path.abspath(a.model)
    if a.quick:
        g = cfg.generation
        g.rounds, g.steps, g.population = min(g.rounds, 3), min(g.steps, 150), min(g.population, 24)
    generate(cfg)


def cmd_info(a):
    from meidnet.checkpoint import describe, load_checkpoint
    print(describe(load_checkpoint(a.model)))


def cmd_families(a):
    from meidnet.family import list_families, load_family
    if a.name:
        fam = load_family(a.name, variant=a.variant, default_variant=True)
        print(fam.describe())
        print("\nvariants:", ", ".join(f"{k} ({v})" for k, v in fam.variants.items()) or "none")
        print("\nconstraints:")
        from meidnet.constraints import explain
        for c in fam.constraints:
            t, text = explain(c["name"], c)
            print(f"  - {t}: {text}")
        print(f"\nfile: {fam.source}")
    else:
        for n in list_families():
            print(n)


def cmd_schema(a):
    from meidnet.config import json_schema
    text = json_schema()
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {a.output}")
    else:
        print(text)


def cmd_download_data(a):
    import urllib.request
    os.makedirs(a.dir, exist_ok=True)
    for split in ("train", "val", "test"):
        dst = os.path.join(a.dir, f"{split}.csv")
        if os.path.exists(dst) and not a.force:
            print(f"{dst} exists")
            continue
        print(f"downloading {split}.csv ...")
        urllib.request.urlretrieve(PEROV5_URL.format(split=split), dst)
    print(f"Perov-5 (CDVAE split, Xie et al. 2022) is in {a.dir}")


def cmd_demo(a):
    """Generate a few perovskites with the published model and open the report."""
    from meidnet.config import config_from_dict
    from meidnet.pipeline import generate
    ckpt = published_checkpoint()
    raw = {
        "name": "demo", "output_dir": a.out, "model_path": os.path.abspath(ckpt),
        "description": "MEIDNet demo: published Perov-5 model",
        "generation": {
            "family": "perovskite_abx3", "variant": a.family,
            "objectives": [{"property": "dir_gap", "loss": "l2", "weight": 10000, "select_weight": 1.0},
                           {"property": "heat_all", "loss": "l1", "weight": 6000, "select_weight": 0.4}],
            "targets": [{"dir_gap": a.band_gap, "heat_all": a.enthalpy}],
            "per_target": a.n, "population": 24, "rounds": a.rounds, "steps": a.steps,
            "min_cosine_sep": 0.98,
        },
    }
    cfg = config_from_dict(raw, base_dir=os.getcwd())
    cfg.training.device = a.device
    res = generate(cfg)
    rep = os.path.join(cfg.out_dir, "generation_report.html")
    print(f"\n{len(res.saved)} candidates. Report: {rep}")
    if not a.no_open:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(rep))


def cmd_studio(a):
    from meidnet.studio.server import export_static, serve
    cfg = _cfg(a.config) if a.config else None
    if a.export_static:
        export_static(cfg, a.export_static, model_path=a.model)
        return
    serve(cfg, model_path=a.model, port=a.port, open_browser=not a.no_open, host=a.host, public=a.public,
          run_root=a.run_root, docs_dir=a.docs_dir)


def cmd_space(a):
    from meidnet.checkpoint import load_checkpoint
    from meidnet.designspace import enumerate_space, space_to_csv
    from meidnet.pipeline import family_for
    cfg = _cfg(a.config)
    lm = load_checkpoint(a.model or cfg.checkpoint_path)
    fam = family_for(cfg, need_variant=True)
    space = enumerate_space(fam, lm, max_compositions=a.max)
    out = a.output or os.path.join(cfg.out_dir, "design_space.csv")
    space_to_csv(space, out)
    n_ok = sum(all(r["ok"].values()) for r in space["rows"])
    print(f"{len(space['rows'])} compositions ({n_ok} pass every rule) -> {out}")
    if a.chemiscope:
        import json
        from meidnet.studio.chemiscope import space_dataset
        with open(a.chemiscope, "w", encoding="utf-8") as f:
            json.dump(space_dataset(fam, space, lm), f)
        print(f"chemiscope dataset -> {a.chemiscope}  (open it at https://chemiscope.org)")


def cmd_screen(a):
    from meidnet.screen import screen
    screen(a.dir, train_csv=a.train_csv, threshold=a.threshold, device=a.device, model_path=a.model)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # print ✓ / ⚠ safely on legacy Windows consoles
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
    p = argparse.ArgumentParser(prog="meidnet", description=textwrap.dedent(__doc__),
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"meidnet {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="write a starter meidnet.yaml")
    s.add_argument("-o", "--output", default="meidnet.yaml")
    s.add_argument("--template", choices=["custom", "perov5"], default="custom")
    s.add_argument("--name", default="my_materials")
    s.add_argument("--table", default="materials.csv")
    s.add_argument("--id-column", default="material_id")
    s.add_argument("--cif-column", default="cif")
    s.add_argument("--properties", nargs="*", help="property column names")
    s.add_argument("--family", default="perovskite_abx3")
    s.add_argument("--variant", default=None)
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    for name, fn, h in (("check", cmd_check, "read the data and write check_report.html"),
                        ("train", cmd_train, "train the model and write training_report.html"),
                        ("generate", cmd_generate, "design candidates and write generation_report.html")):
        s = sub.add_parser(name, help=h)
        s.add_argument("config", nargs="?", default="meidnet.yaml")
        if name == "train":
            s.add_argument("--epochs", type=int, default=None, help="override training.epochs")
        if name == "generate":
            s.add_argument("--model", default=None, help="checkpoint to use instead of the config's model_path")
            s.add_argument("--quick", action="store_true", help="few rounds/steps - a smoke test")
        s.set_defaults(fn=fn)

    s = sub.add_parser("studio", help="interactive design workbench (local web page)")
    s.add_argument("config", nargs="?", default=None, help="meidnet.yaml (optional: defaults to the published model)")
    s.add_argument("--model", default=None)
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-open", action="store_true")
    s.add_argument("--export-static", metavar="FILE.html", default=None,
                   help="write a self-contained copy of the Studio (no server; search disabled)")
    s.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to accept connections from other machines")
    s.add_argument("--public", action="store_true", help="multi-user hosting mode: per-visitor sessions, capped budgets")
    s.add_argument("--run-root", default=None, help="folder for search outputs (default runs/studio)")
    s.add_argument("--docs-dir", default=None, help="serve a built MkDocs site at /docs/")
    s.set_defaults(fn=cmd_studio)

    s = sub.add_parser("space", help="every composition of the family with rule values and predictions → CSV")
    s.add_argument("config", nargs="?", default="meidnet.yaml")
    s.add_argument("--model", default=None)
    s.add_argument("-o", "--output", default=None)
    s.add_argument("--max", type=int, default=60000)
    s.add_argument("--chemiscope", metavar="FILE.json", default=None,
                   help="also write a chemiscope.org dataset (property map + 3D structures)")
    s.set_defaults(fn=cmd_space)

    s = sub.add_parser("demo", help="generate perovskites with the published model")
    s.add_argument("--family", choices=["halide", "oxide", "chalcogenide", "nitride"], default="halide")
    s.add_argument("--band-gap", type=float, default=2.0)
    s.add_argument("--enthalpy", type=float, default=-0.10)
    s.add_argument("-n", type=int, default=3)
    s.add_argument("--rounds", type=int, default=5)
    s.add_argument("--steps", type=int, default=300)
    s.add_argument("--out", default="runs/demo")
    s.add_argument("--device", default="auto")
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("screen", help="MACE stability screening (pip install meidnet[stability])")
    s.add_argument("dir", help="folder with CIF files (searched recursively)")
    s.add_argument("--train-csv", default=None, help="table with a formula column, for novelty")
    s.add_argument("--threshold", type=float, default=0.10)
    s.add_argument("--device", default="auto")
    s.add_argument("--model", default="medium")
    s.set_defaults(fn=cmd_screen)

    s = sub.add_parser("info", help="describe a checkpoint")
    s.add_argument("model")
    s.set_defaults(fn=cmd_info)

    s = sub.add_parser("families", help="list / describe material families")
    s.add_argument("name", nargs="?")
    s.add_argument("--variant", default=None)
    s.set_defaults(fn=cmd_families)

    s = sub.add_parser("schema", help="JSON Schema of meidnet.yaml")
    s.add_argument("-o", "--output", default=None)
    s.set_defaults(fn=cmd_schema)

    s = sub.add_parser("download-data", help="fetch the Perov-5 dataset")
    s.add_argument("--dir", default="data/perov5")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_download_data)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
