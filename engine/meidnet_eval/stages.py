"""THE central definition of MEIDNet's staged evaluation: ten blocks, their metrics, their reference bands.

Everything else imports from here — `pipeline_checkup.py` for its thresholds, `discover.py` for its stage cards,
`final_report.py` and the Matter app for what to show, `STAGE_EVALUATION.md` is GENERATED from here.  So a band exists in
exactly one place and the document cannot drift from the code.

A band is only legitimate if it separates configurations whose quality is already known, so the measured Perov-5 values are
stored next to each metric (`reference`) together with what each configuration is (`CONFIGS`) and what the bands must say
about it (`EXPECTATIONS`).  `python stages.py --validate` re-grades those stored values and fails if a known-broken
configuration passes a block it broke, or a known-good one fails a block without a documented reason.  That is what keeps the
bands consistent when someone edits them: the validation is executable, not a paragraph.

  python stages.py --validate     re-grade the stored Perov-5 references against the bands (exit 1 on a contradiction)
  python stages.py --markdown     regenerate meidnet_journey/STAGE_EVALUATION.md from this file
  python stages.py --show S3      print one block
"""
from __future__ import annotations

import argparse
import sys
import os
from dataclasses import dataclass, field

GRADES = ("PASS", "WARN", "FAIL", "INFO")

# the configurations the bands were validated against; "known" is what we independently know about each
CONFIGS = {
    "published": dict(label="published app (broken)", checkup="A0_v1search",
                      known="the original MEIDNet Matter app: 8 root causes found in the X-ray"),
    "control": dict(label="control: structure losses off", checkup="control_v1search",
                    known="ablation, broken in a different way: the property head was never trained on structure latents"),
    "fixed": dict(label="fixed model + fixed search", checkup="grounded_grounded", known="known good"),
    "final": dict(label="final (descriptors + on-manifold search)", checkup="desc_full_optA",
                  known="known good, best configuration"),
    "mp": dict(label="second dataset (919 MP perovskites)", checkup="MP_checkup",
               known="transfer test; its decoder is data-starved (12 compositions per element)"),
}


@dataclass
class Metric:
    id: str
    name: str
    definition: str
    unit: str
    better: str                      # "higher" | "lower"
    pass_at: float | None            # PASS when the value is at least / at most this
    warn_at: float | None            # otherwise WARN while at least / at most this, else FAIL
    meaning_good: str
    meaning_bad: str
    remedy: str
    computed_by: str
    info_only: bool = False          # context, never graded
    conditional_on: tuple | None = None   # (metric_id, "gt"|"lt", threshold): graded only when that holds, else INFO
    dataset_agnostic: bool = True
    new_dataset_note: str = ""
    cap: str = ""                    # worst grade this metric may give (a scope limit must not read as a defect)
    superseded_by: str = ""          # when THIS metric is only a proxy and that one is measured, report it as context
    recalibrated: str = ""           # why the band differs from the original pipeline_checkup threshold
    reference: dict = field(default_factory=dict)   # config key -> measured value
    reference_note: str = ""

    def grade(self, value, context: dict | None = None) -> str:
        """PASS/WARN/FAIL for one value; INFO when the metric is context-only or its condition does not apply."""
        if self.info_only or value is None:
            return "INFO"
        if self.superseded_by and (context or {}).get(self.superseded_by) is not None:
            return "INFO"            # the quantity this only predicts has been measured directly; that measurement rules
        if self.conditional_on:
            mid, op, thr = self.conditional_on
            other = (context or {}).get(mid)
            if other is None:
                return "INFO"
            if (op == "gt" and not other > thr) or (op == "lt" and not other < thr):
                return "INFO"            # the hazard this metric measures cannot arise in this configuration
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "INFO"
        if v != v:                       # NaN: not measured
            return "INFO"
        if self.pass_at is None:
            return "INFO"
        if self.better == "higher":
            g = "PASS" if v >= self.pass_at else ("WARN" if self.warn_at is not None and v >= self.warn_at else "FAIL")
        else:
            g = "PASS" if v <= self.pass_at else ("WARN" if self.warn_at is not None and v <= self.warn_at else "FAIL")
        if self.cap and g == "FAIL":
            return self.cap
        return g

    def band_text(self) -> tuple[str, str, str]:
        if self.info_only or self.pass_at is None:
            return ("context only", "", "")
        s = "≥" if self.better == "higher" else "≤"
        inv = "<" if self.better == "higher" else ">"
        p = f"{s} {self.pass_at:g}"
        w = f"{s} {self.warn_at:g}" if self.warn_at is not None else ""
        f = f"{inv} {self.warn_at:g}" if self.warn_at is not None else f"{inv} {self.pass_at:g}"
        return (p, w, f)


@dataclass
class Stage:
    id: str
    name: str
    question: str
    purpose: str
    metrics: list
    when: str                        # "preview" (no model needed) | "after training" | "after a run"
    verdict_rule: str = "the worst grade of its graded metrics"
    caveats: list = field(default_factory=list)
    scripts: list = field(default_factory=list)      # the components that implement this block

    def by_id(self, mid):
        return next((m for m in self.metrics if m.id == mid), None)

    def verdict(self, values: dict, context: dict | None = None) -> tuple[str, dict]:
        grades = {m.id: m.grade(values.get(m.id), context) for m in self.metrics}
        real = [g for g in grades.values() if g != "INFO"]
        order = {"FAIL": 3, "WARN": 2, "PASS": 1}
        worst = max(real, key=lambda g: order[g]) if real else "INFO"
        return worst, grades


# ───────────────────────────── S0 data (no model needed: the preview gate) ─────────────────────────────
S0 = Stage(
    "S0", "Data", "Is my data usable for property to structure design?",
    "Check the uploaded data before any training: how well posed the inverse problem is, whether each target has support, "
    "and whether anything new can be reached at all.",
    when="preview",
    metrics=[
        Metric("shared_profile", "Materials sharing a property profile",
               "Share of materials whose rounded property vector is shared by at least 9 others.",
               "share of materials", "lower", 0.20, 0.50,
               "Properties mostly identify a material, so a target has few possible answers.",
               "Many different materials have the same properties: property to structure has no unique answer, only a "
               "distribution of answers.",
               "Add another property column (more properties separate more materials), or accept a set of candidates "
               "rather than one.",
               "intake.py (audit 'materials_sharing_profile_with_>=10')",
               reference=dict(published=0.93, control=0.93, fixed=0.93, final=0.93, mp=0.00),
               recalibrated="Was bundled with the zero share into one 'zero-inflation' check, which warned on the MP "
                            "dataset for having 53% zero gaps even though its inverse problem is well posed (0% shared "
                            "profiles). Zero share is now context; this is the graded part."),
        Metric("zero_share", "Zero share of the target property",
               "Share of training materials whose target property is exactly zero.", "share", "lower", None, None,
               "", "", "Context for the metal/non-metal metric in S1 and for how many targets are reachable.",
               "intake.py (audit 'properties.<target>.zero_share')", info_only=True,
               reference=dict(published=0.96, control=0.96, fixed=0.96, final=0.96, mp=0.53)),
        Metric("target_support", "Training support at a target",
               "Number of training materials within +-0.25 of the requested target value.", "materials", "higher", 100, 30,
               "Enough neighbours for the model to have learned this region.",
               "Almost nothing in the data resembles the request, so labels there are extrapolation.",
               "Drop the target, or add data in that range.", "reliability_map.py",
               reference_note="Perov-5: 10936 at 0 eV; 56 at 2 eV; 22 at 4 eV; 8 at 5 eV (the last two FAIL)."),
        Metric("density", "Distinct compositions per element",
               "Mean number of distinct compositions each element appears in, across the training split.",
               "compositions/element", "higher", 200, 80,
               "Each element is seen in enough different compounds for the decoder to learn it.",
               "The decoder cannot learn a reliable latent to element mapping; generation will not work and the run must "
               "use screening.",
               "Use screening mode (the pipeline switches automatically), or add data.",
               "measured in the density experiment; computed by intake.py in the preview",
               reference=dict(fixed=218, final=218, mp=12),
               reference_note="Trained identically on Perov-5 subsets: 12 -> 0.1%, 30 -> 0.7%, 80 -> 5.4%, 218 -> 64% "
                              "composition recovery (journal Entry 44), so this predicts S3 before training."),
        Metric("novelty_frontier", "Share of the design space absent from the data",
               "Fraction of the charge-balanced design space built from the data's own chemistry that the data does not "
               "already contain.", "share", "higher", 0.10, 0.01,
               "There is unexplored space to search.",
               "The dataset has already explored its own design space, so anything 'novel' requires chemistry the model "
               "has never seen.",
               "Enlarge the design space (more prototypes, more anion sets), not the element list.",
               "auto_family.py + discover.py stage 04",
               reference=dict(fixed=0.0, mp=0.63),
               reference_note="Perov-5 is a complete 52x52x7 grid: 0 of 148 novel candidates avoided unseen elements "
                              "(journal Entry 40). The MP set leaves 63% of its space unexplored."),
    ],
    caveats=["S0 FAILs on Perov-5 for all configurations. That is a property of the dataset, not of the pipeline: it is a "
             "complete grid with 96% zero gaps. It is reported, not hidden."])

# ───────────────────────────── S1 encoder ─────────────────────────────
S1 = Stage(
    "S1", "Encoder (structure to property)", "Does the model read properties from structures correctly?",
    "The label of every candidate, read from the returned structure, comes from this block, so its error is the floor on how precisely any target can "
    "be hit.",
    when="after training",
    metrics=[
        Metric("gap_rel_mae", "Target error relative to its spread",
               "Mean absolute error on materials with a non-zero target, divided by the standard deviation of that subset.",
               "spreads", "lower", 0.70, 1.00,
               "Labels are accurate enough to aim with: the fixed pipeline at 0.53 supports rho 0.98 end to end.",
               "The label error is comparable to the whole spread of the property, so a target cannot be aimed at.",
               "More data, more epochs, or inspect label outliers.", "pipeline_checkup.py / model_metrics.py",
               reference=dict(published=1.072, control=1.989, fixed=0.527, final=0.528, mp=0.643),
               recalibrated="The original band (0.25 / 0.50) graded every configuration FAIL, including the one that "
                            "delivers rho 0.98, so it could not tell a working encoder from a broken one. Set from what "
                            "is achievable and demonstrably sufficient, while still failing published (1.07) and "
                            "control (1.99)."),
        Metric("gap_r", "Target rank correlation", "Pearson r between predicted and true target on non-zero materials.",
               "r", "higher", 0.80, 0.60,
               "The ordering of materials by the property is right, which is what a search needs.",
               "The model cannot rank materials by the property.", "More data or more epochs.",
               "pipeline_checkup.py", reference=dict(published=0.50, control=0.55, fixed=0.88, final=0.86, mp=0.82)),
        Metric("metal_accuracy", "Metal / non-metal accuracy",
               "Share of test materials on the right side of the zero-gap boundary.", "share", "higher", 0.95, 0.85,
               "The model distinguishes conductors from semiconductors, the coarsest and most important call.",
               "The model cannot tell a metal from a semiconductor, so any gap target is meaningless.",
               "Switch the structure losses on (the control configuration shows their effect: 4% vs 98%).",
               "pipeline_checkup.py", reference=dict(published=0.044, control=0.042, fixed=0.975, final=0.975, mp=0.897)),
        Metric("cost_rel_mae", "Second property error relative to its spread",
               "Mean absolute error of the stability or energy property, divided by its standard deviation.",
               "spreads", "lower", 0.25, 0.50, "The stability estimate is usable for ranking.",
               "Stability predictions are not usable.", "More data or more epochs.", "pipeline_checkup.py",
               reference=dict(published=0.544, control=0.802, fixed=0.07, final=0.07, mp=0.11)),
        Metric("knn_rel_mae", "Latent organised by property",
               "Error of a 5-nearest-neighbour prediction in the structure latent, divided by the property spread.",
               "spreads", "lower", 0.25, 0.50,
               "Materials with similar properties sit together in the latent, which is what makes a latent search possible.",
               "The latent is not organised by the property, so searching it cannot find the property.",
               "More training, or check the alignment weight.", "pipeline_checkup.py",
               reference=dict(published=0.103, control=0.150, fixed=0.090, final=0.081, mp=0.277),
               reference_note="The published app PASSES this while failing the property read-out: its latent was fine, "
                              "its head was broken. That contrast is why these are separate metrics."),
        Metric("unseen_degradation", "Trust outside the training chemistry",
               "Target error on materials containing a held-out element, divided by the error on seen chemistry.",
               "ratio", "lower", 1.5, 2.5,
               "Labels can be trusted for elements beyond the training set.",
               "Labels for materials containing new elements rest on untrained embeddings.",
               "Keep candidates inside the training chemistry, or state the bias explicitly.",
               "unseen_element_test.py", cap="WARN",
               reference_note="Measured on SEPARATE models trained with La/Y held out, not on the configurations in the "
                              "table, so no per-configuration value is stored: 2.9x, 3.1x and 3.4x worse (0.85 -> 2.50 "
                              "eV, 0.86 -> 2.64, 0.79 -> 2.65). On Perov-5 this makes lanthanide labels run about 0.7 eV "
                              "low. Capped at WARN because it bounds the SCOPE of a working encoder rather than showing "
                              "a broken one; it only bites when the design space needs unseen elements, which on Perov-5 "
                              "it always does (0 of 148 novel candidates avoided them)."),
    ])

# ───────────────────────────── S2 alignment ─────────────────────────────
S2 = Stage(
    "S2", "Alignment (structure and property latents)", "Do the two latents line up?",
    "Whether a property can be used to point at a region of structure space.",
    when="after training",
    metrics=[
        Metric("retrieval_vs_chance", "Retrieval above chance",
               "Top-1 retrieval of the matching property profile from a structure latent, as a multiple of chance.",
               "x chance", "higher", 20, 5, "A property latent points at the right region of structure space.",
               "The two latents are unrelated, so a property cannot aim the search.",
               "Raise the alignment weight or train longer.", "pipeline_checkup.py",
               reference=dict(published=123.3, control=42.1, fixed=40.1, final=44.7, mp=25.0),
               reference_note="This block PASSES in the broken app too, and most strongly of all (123x). Alignment was "
                              "never the fault; tuning it would have been wasted work."),
        Metric("matched_cosine", "Matched cosine",
               "Cosine between the structure and property latents of the same material.", "cosine", "higher", 0.6, 0.4,
               "The two views of one material agree.", "The two views disagree.", "Raise the alignment weight.",
               "pipeline_checkup.py", reference=dict(published=0.77, control=0.53, fixed=0.62, final=0.61, mp=0.79)),
        Metric("target_latent_distance", "Distance of a target's latent from the structure manifold",
               "One minus the largest cosine between a target's property latent and any training structure latent.",
               "distance", "lower", None, None, "", "",
               "Context: explains why the property latent cannot be decoded directly.", "reliability_map.py",
               info_only=True, reference=dict(final=0.33),
               reference_note="0.31-0.35 for every target, against 0.000-0.046 between real structures: a target's latent "
                              "sits about 8x further out than any structure the decoder was trained on."),
    ])

# ───────────────────────────── S3 decoder ─────────────────────────────
S3 = Stage(
    "S3", "Decoder (latent to structure)", "Can a latent be turned back into a material?",
    "Whether the pipeline can propose structures itself, or must screen an enumerated design space instead.",
    when="after training",
    metrics=[
        Metric("comp_exact_gen", "Composition recovered from the structure latent",
               "Share of test materials whose exact composition is decoded back from their structure latent, under the "
               "same conditions as generation (zero start coordinates).", "%", "higher", 80, 50,
               "The decoder can propose compositions, so the generative engine may be used.",
               "The decoder cannot reconstruct compositions; the run must screen the design space instead of generating.",
               "Use screening mode, or add data (see the density metric in S0).",
               "pipeline_checkup.py / decoder_autopsy.py",
               reference=dict(published=0.03, control=0.98, fixed=51.4, final=64.1, mp=1.37)),
        Metric("condition_drop", "Training to generation condition drop",
               "Percentage points of composition recovery lost when the decoder is given the inputs it gets at generation "
               "time instead of the ones it was trained on.", "points", "lower", 10, 30,
               "The decoder is run the way it was trained.",
               "The decoder was trained on inputs it never gets at generation time, so generation silently fails.",
               "Train the decoder with the generation-time inputs (zero coordinates).", "pipeline_checkup.py",
               reference=dict(published=86.0, control=0.05, fixed=-0.98, final=-0.08, mp=-0.69),
               reference_note="This diagnoses the published app's specific bug (trained on true atom positions, run with "
                              "zeros: 86 -> 0%). It measures the MISMATCH, not the capability: the control model passes "
                              "it at 7% -> 8%, equally unable in both. Always read it with comp_exact_gen."),
        Metric("comp_exact_from_property", "Composition recovered from the property latent alone",
               "Share of test materials decoded correctly from their property latent only.", "%", "higher", None, None,
               "", "", "Context: 0% is expected, because many structures share a property. The search resolves this.",
               "pipeline_checkup.py", info_only=True,
               reference=dict(published=0.0, control=0.08, fixed=0.0, final=0.03, mp=0.0)),
        Metric("lattice_error", "Lattice constant error",
               "Mean absolute error of the generated lattice constant against an ML-potential relaxation.",
               "Angstrom", "lower", 0.10, 0.20,
               "Generated cells are the right size.", "Generated cells are the wrong size.",
               "Read the lattice from the decoder at the structure latent rather than from a radii rule.",
               "lattice_source.py", reference=dict(final=0.076),
               reference_note="Decoder at the structure latent 0.076 A; the radii rule it replaced 0.164 A; the decoder "
                              "read at the off-manifold search latent 0.688 A (journal Entry 41)."),
    ],
    caveats=["A WARN here is expected when the data is thin: 64% on Perov-5 is close to what 218 compositions per element "
             "allows. The remedy is data or screening, not tuning."])

# ───────────────────────────── S4 property head ─────────────────────────────
S4 = Stage(
    "S4", "Property head (labels)", "Does the label shown describe the returned structure?",
    "Whether the number displayed for a candidate is really that candidate's predicted property.",
    when="after a run",
    metrics=[
        Metric("label_rel_mae", "Label describes the returned structure",
               "Absolute difference between the label shown for a candidate and the property predicted from the structure "
               "actually returned, divided by the property spread.", "spreads", "lower", 0.10, 0.25,
               "The label belongs to the structure the user receives.",
               "The number shown does not describe the material shown.",
               "Read the label back from the returned structure (label_source=structure). Locked on in the app.",
               "pipeline_checkup.py",
               reference=dict(published=1.643, control=2.526, fixed=0.000, final=0.000),
               reference_note="This catches the central bug of the published app: the label came from the search latent "
                              "and was attached to whatever composition was decoded, a 2.57 eV discrepancy. After the "
                              "fix it is 0.00 by construction, so this metric is a regression guard."),
        Metric("head_length_sensitivity", "Sensitivity to latent length",
               "Change in predictions, in property spreads, when the latent is stretched from length 1 to 4.",
               "spreads", "lower", 3.0, 6.0,
               "Predictions do not depend on how long the latent is.",
               "Predictions change wildly with latent length, so a search that drifts away from length 1 produces "
               "meaningless labels.",
               "Constrain the search to the unit sphere. Locked on in the app.",
               "pipeline_checkup.py", conditional_on=("search_length_ratio", "gt", 1.25),
               reference=dict(published=11.74, control=21.81, fixed=2.15, final=2.26, mp=1.62),
               recalibrated="The original band (0.25 / 0.50 spreads) graded every configuration FAIL, including the fixed "
                            "one, for a hazard that cannot arise there: the fixed search holds the latent at length 1.00. "
                            "The metric is now conditional on the search actually drifting (S5 length ratio > 1.25), "
                            "which is the accurate statement of what the unit sphere does: it removes a hazard rather than "
                            "improving results."),
    ])

# ───────────────────────────── S5 search ─────────────────────────────
S5 = Stage(
    "S5", "Search (proposal engine)", "Is the search aimed at my target, and does it stay where the model is trusted?",
    "Whether proposals come from a region the model has seen, and whether they are conditioned on the target at all.",
    when="after a run",
    metrics=[
        Metric("search_length_ratio", "Latent length ratio",
               "Median length of the final search latents divided by the median length of training structure latents.",
               "ratio", "lower", 1.25, 2.0,
               "The search stays at the scale the model was trained on.",
               "The search left the scale of the training latents, so the property head is being read far outside its "
               "domain.", "Constrain the search to the unit sphere.", "pipeline_checkup.py",
               reference=dict(published=4.175, control=4.517, fixed=1.000, final=1.000)),
        Metric("search_manifold_cos", "Distance to the data manifold",
               "Median largest cosine between a final search latent and any training structure latent.",
               "cosine", "higher", 0.95, 0.85,
               "Proposals come from the populated part of the latent space.",
               "Proposals come from empty latent space, where nothing was ever trained.",
               "Sample between nearest real structure latents instead of following a gradient.", "pipeline_checkup.py",
               reference=dict(published=0.181, control=0.199, fixed=0.342, final=0.992)),
        Metric("raw_steering_rho", "Raw steering, before any filter",
               "Spearman correlation between the requested target and the true property of the raw proposals, with no "
               "filtering applied.", "rho", "higher", 0.60, 0.30,
               "The proposals themselves are conditioned on the target; the result is not an artefact of filtering.",
               "The search is not conditioned on the target: any apparent success comes from the filter alone.",
               "Aim the search with the property latent; check the alignment block.", "steer_test.py",
               reference=dict(published=0.0, final=0.85),
               reference_note="Final configuration +0.85 (replicate +0.84) against about 0 for random proposals. This is "
                              "the only clean evidence of real conditioning, because it is measured before filtering."),
        Metric("seed_spread", "Seed reproducibility",
               "Difference in hit rate, in percentage points, between two training seeds of the same configuration.",
               "points", "lower", 10, 25,
               "The result is reproducible across seeds.",
               "The result depends on the seed, so a single run must not be reported as an improvement.",
               "Always run at least two seeds and report the range.", "ablation_summary.json",
               reference=dict(fixed=1.8, final=26.5),
               reference_note="Full fix 67.3 vs 65.5 (1.8 points). On-manifold search 83.3 vs 56.8 (26.5 points), which "
                              "is why its advantage over the plain baseline is reported as unproven."),
    ],
    caveats=["On-manifold sampling and the novelty rule conflict: it samples between known structures, so with novelty "
             "required it returned 0 candidates in 3 of 4 arms. The search mode is therefore a choice by goal, not a "
             "quality setting."])

# ───────────────────────────── S6 end-to-end ─────────────────────────────
S6 = Stage(
    "S6", "End-to-end target following", "Do the proposed materials actually hit my target?",
    "The question the whole pipeline exists to answer.",
    when="after a run",
    metrics=[
        Metric("rho_target", "Target vs true property of the returned structures",
               "Spearman correlation between the requested target and the reference property of what was returned.",
               "rho", "higher", 0.70, 0.40,
               "Asking for more gap returns more gap: the pipeline follows the target.",
               "What is returned is unrelated to what was asked for.",
               "Check S4 (labels read from the returned structure) first: that is what fixed it here.", "eval_analyse.py",
               reference=dict(published=0.01, control=-0.09, fixed=0.98, final=0.98),
               new_dataset_note="On Perov-5 the whole grid has DFT, so this is measured directly. On a user's dataset the "
                                "equivalent is the hold-out rediscovery test: hide the test split, screen, and compare "
                                "with its DFT."),
        Metric("hit_vs_random", "Hit rate against a blind draw",
               "Share of returned candidates within the target window, divided by the same share for random valid "
               "compositions.", "x random", "higher", 3.0, 1.5,
               "The pipeline is far better than guessing.", "The pipeline is no better than guessing.",
               "Check S4 and S1.", "eval_analyse.py",
               reference=dict(published=1.2, fixed=8.7, final=10.8),
               reference_note="Published 9.5% against a 7.7% random baseline (1.2x). Fixed 67.3% (8.7x). Best 83.3% "
                              "(10.8x), replicate 56.8% (7.4x). A DFT oracle on the same space reaches 21.4%."),
        Metric("label_mae_dft", "Label error against the reference",
               "Mean absolute difference between the label shown and the reference property of the returned material.",
               "eV", "lower", 0.50, 1.00, "The promised property is close to the real one.",
               "The promised property is far from the real one.", "Check S4 and S1.", "eval_analyse.py",
               dataset_agnostic=False,
               new_dataset_note="Express in spreads of the target property to transfer between datasets.",
               reference=dict(published=2.48, fixed=0.33, final=0.18)),
        Metric("judge_mae_request", "Independent judge against the request (family-free generation)",
               "Mean absolute difference between the requested property and a QUALIFIED independent judge's value for "
               "the generated structures, over the whole pool before any consensus selection.  Measures the generator, "
               "not the filter.", "eV", "lower", 1.00, 1.50,
               "Asking for a gap returns structures whose independently judged gap is near it.",
               "The generator returns the training set's dominant answer (for MP-20: zero-gap intermetallics) whatever "
               "was asked for; the model's own search-latent label hides this by reading the request back.",
               "Read the label from the returned structure, not the search latent (S4); use the target anchor with no "
               "latent refinement; require an anion; cap the cell at the encoder's max_sites so every candidate can be "
               "re-encoded.  Each of these was measured separately on MP-20.",
               "conditional_generate.py --geometry wyckoff + target_calibration.py --judge megnet",
               reference=dict(mp20_before=2.00, mp20=1.10),
               reference_note="MP-20, 7 targets 0.5-4 eV: search-latent labels + free chemistry 2.00 eV (77 of 84 metals); "
                              "label read from the returned structure, no refinement, anion required, cell capped: 1.10 eV (24 of 175 metals). "
                              "Saturates above 3 eV."),
        Metric("consensus_yield", "Two-judge consensus yield",
               "Share of the generated pool that BOTH the model's own label, read from the returned structure, and the qualified independent judge place "
               "within 0.5 eV of the request.  This is the set a user may be shown.", "share of pool", "higher", 0.15, 0.05,
               "Enough candidates survive two independent judges to serve the target.",
               "Almost nothing survives both judges: the target is outside what this model and data can serve.",
               "Widen the window only with the error band shown; otherwise report the target as not servable (S9).",
               "target_calibration.py --select 0.5",
               reference=dict(mp20=0.21),
               reference_note="MP-20: 37 of 175; 14 at 0.5 eV, 8 at 1.5, 5 at 2.0, 5 at 2.5, 2 at 3.0, 1 at 4.0."),
    ],
    caveats=["Random proposals plus the structure-read label filter already reach 64.1%, so most of the end-to-end gain comes from the "
             "filter rather than from the search. Reported, not hidden.",
             "Family-free generation on MP-20: the latent refinement steps made the property decoder say the target while "
             "pushing the structure decoder into metals (semiconductor share 20% with them, 42-62% without), so the "
             "symmetry path uses the target anchor alone."])

# ───────────────────────────── S7 validation funnel ─────────────────────────────
S7 = Stage(
    "S7", "Validation funnel", "Stable, unique, novel, and really a perovskite?",
    "Independent evidence for every surviving candidate, and a full account of how many were rejected.",
    when="after a run",
    metrics=[
        Metric("mlip_agreement", "Two potentials agree",
               "Share of candidates for which two independent ML potentials relax to the same space group.",
               "share", "higher", 0.90, 0.70,
               "The relaxed structure does not depend on which potential was used.",
               "The two potentials disagree, so the structure and its stability are not trustworthy.",
               "Report the disagreement; do not claim stability.", "candidate_cells.py",
               reference=dict(final=1.00, mp=1.00),
               reference_note="70/70 on the discovery set (median lattice difference 0.024 A) and 16/16 on the MP set."),
        Metric("rediscoveries", "Known materials rediscovered",
               "Number of returned candidates that are experimentally known compounds, at their measured property.",
               "compounds", "higher", 1, 0,
               "The pipeline recovers real materials it was never shown, the most persuasive single check.",
               "No known material was recovered; say so rather than implying validation.",
               "Relax the novelty filter for one run to see whether known compounds are reachable.",
               "discovery_report.py", reference=dict(final=7)),
        Metric("stable_share", "Stable share of the proposals",
               "Share of validated candidates within the hull-distance threshold.", "share", "higher", None, None,
               "", "", "Context: report the funnel, not a single number. Stability is the dominant filter.",
               "sun_validate.py", info_only=True, reference=dict(final=0.40),
               reference_note="Funnel on the discovery set: 70 validated -> 68 absent from Materials Project -> 61 not in "
                              "the literature -> 51 formable -> 17 stable -> 8 after the judges."),
    ],
    caveats=["No DFT is run anywhere in this pipeline. Stability rests on two ML potentials agreeing, and is labelled as "
             "such."])

# ───────────────────────────── S8 judges ─────────────────────────────
S8 = Stage(
    "S8", "Independent judges", "Can I trust the independent evidence?",
    "A verifier has to prove itself before its verdict counts.",
    when="after training",
    metrics=[
        Metric("judge_qualification", "The judge's own error relative to the property spread",
               "The judge's error on the held-out split, divided by the spread of the property, measured before it judges "
               "anything.", "spreads", "lower", 0.50, 0.80,
               "The judge is accurate enough for its verdict to mean something.",
               "The judge is not accurate enough to verify anything; its agreement or disagreement is noise.",
               "Train a judge on the user's own data; if it still fails, report that no independent check is available.",
               "cgcnn_judge.py (train, metrics on the test split)",
               reference=dict(final=0.38, mp20_megnet=0.07),
               reference_note="Perov-5 test split: CGCNN trained on the data 0.59 eV / r +0.92 / metal 98% (qualified); "
                              "MEGNet multi-fidelity 1.71 eV / r +0.51 / metal 17% (not usable here); CGCNN pretrained "
                              "elsewhere 1.23 eV / r +0.32 / metal 30%. On the MP dataset its own judge reaches 0.74 eV / "
                              "r +0.85 / metal 89%."),
        Metric("judge_consensus", "Qualified judges agreeing with the target",
               "Number of qualified judges that place a candidate within the agreed tolerance of its target.",
               "judges", "higher", 2, 1,
               "At least two independent checks agree with the claim.",
               "Nothing independent supports the claim.", "Qualify more judges, or report the candidate as unverified.",
               "judge_consensus.py", reference=dict(final=2),
               reference_note="On 70 candidates: a qualified judge gives rho +0.87 with the target and DFT analogues "
                              "+0.86, while the unqualified MEGNet gives +0.44. The first discovery report used MEGNet "
                              "and so understated the pipeline: the judge was the problem, not the candidates."),
    ],
    caveats=["A judge trained on the user's data shares that data's blind spots, so model-judge agreement is weaker "
             "evidence than agreement with DFT."])

# ───────────────────────────── S9 readiness ─────────────────────────────
S9 = Stage(
    "S9", "Readiness", "Which targets can this dataset serve, decided before generating?",
    "Turn the known limits into a prediction made in advance rather than an excuse afterwards.",
    when="after training",
    metrics=[
        Metric("servable_targets", "Targets with enough support",
               "Number of requested targets whose training support passes the S0 support band.", "targets", "higher",
               1, 0, "At least one requested target is supported by the data.",
               "No requested target is supported.", "Choose targets inside the supported range.", "reliability_map.py",
               superseded_by="holdout_label_error",      # a count only PREDICTS the error; once it is measured, that wins
               reference=dict(final=8),
               reference_note="Perov-5: 0 to 3.5 eV servable; 4 eV and above unreliable (22, 14, 8 and 7 materials). "
                              "Validated against the outcome: targets called servable gave a mean label error of 0.59 eV, "
                              "those called unreliable 0.95 eV."),
        Metric("holdout_label_error", "Measured label error on the held-out split",
               "Mean absolute error of the target on the held-out test split, divided by the spread of that split.",
               "spreads", "lower", 0.25, 0.50,
               "Labels on unseen materials are accurate, measured rather than predicted.",
               "Labels on unseen materials are not accurate enough to aim a target at.",
               "More data, or restrict targets to the range the model demonstrably handles.", "scorecard.py",
               reference_note="On the user's 246-structure upload this is 0.179 spreads (0.647 eV on a 3.62 eV spread) "
                              "even though every target fails the support count, which is why the count is only a proxy."),
        Metric("latent_distance_usable", "Is latent distance usable as an uncertainty signal",
               "Correlation between a material's latent distance to the training set and its prediction error.",
               "correlation", "higher", 0.40, 0.20,
               "Latent distance can be used to flag untrustworthy candidates.",
               "Latent distance carries no information on this dataset and must not be quoted as uncertainty.",
               "Fall back to training support at the target, which does work.", "reliability_map.py", info_only=True,
               reference=dict(final=-0.12),
               reference_note="-0.12 on Perov-5: a complete grid leaves the axis no range, since every test material "
                              "almost touches a training one. The block reports the axis as unusable instead of quoting a "
                              "meaningless number. It is re-tested per dataset, never assumed."),
    ],
    caveats=["Training support at a target is only a PROXY for label error, and it did not transfer. It was calibrated on "
             "Perov-5, where 96% of gaps are exactly zero so the non-zero region really is sparse. On the user's "
             "246-structure upload, whose gaps are continuous over 0.6-14 eV, every target fails the support count while "
             "the measured held-out error is 0.179 spreads, and support barely correlates with error (Spearman -0.11). "
             "So when a model exists, `holdout_label_error` supersedes the count; the count is kept for the preview, where "
             "no model has been trained yet."])

STAGES = [S0, S1, S2, S3, S4, S5, S6, S7, S8, S9]
BY_ID = {s.id: s for s in STAGES}
ALL_METRICS = {m.id: (s, m) for s in STAGES for m in s.metrics}

# which component implements which block (one answer to 'where does block Sx live?')
STAGE_SCRIPTS = {
    "S0": [
        "ingest_upload.py (upload adapter: folder + spreadsheet -> one table, joined on composition)",
        "intake.py (audit, prototypes, composition-grouped split)",
        "preview.py (the gate: runs with no model)",
        "auto_family.py (design space learned from the data)",
    ],
    "S1": [
        "pipeline_checkup.py (the graded checks)",
        "model_metrics.py (held-out property prediction)",
        "unseen_element_test.py (trust outside the training chemistry)",
    ],
    "S2": [
        "pipeline_checkup.py (retrieval and matched cosine)",
        "reliability_map.py (distance of a target's latent)",
    ],
    "S3": [
        "pipeline_checkup.py (recovery under generation conditions)",
        "decoder_autopsy.py (why it fails: collapse, cell size, prototype, density)",
        "lattice_source.py (lattice from the decoder vs from a radii rule)",
    ],
    "S4": [
        "pipeline_checkup.py (label-source check and latent-length sensitivity)",
    ],
    "S5": [
        "eval_generate.py (engine and screen modes)",
        "screen_polymorphs.py (polymorph-aware screening)",
        "steer_test.py (raw steering before any filter)",
        "conditional_generate.py --geometry wyckoff (family-free generation: symmetry decoder, label read from the returned structure, anion "
        "required, cell capped, no latent refinement)",
    ],
    "S6": [
        "eval_analyse.py (ablation summary)",
        "exhaustive_truth.py + generator_vs_truth.py (precision and recall against exact truth)",
        "screen_polymorphs.py --truth test (hold-out rediscovery, the generic replacement on a user dataset)",
        "target_calibration.py (qualified independent judge, fidelity chosen by measurement; --select = two-judge "
        "consensus with a charge-balance flag)",
        "instrument_sheet.py (response curve, bias, precision, accuracy with CI, linearity, resolution, range, yield)",
        "generate_to_target.py (the one command: generate -> judge -> relax -> re-judge -> report)",
    ],
    "S7": [
        "candidate_cells.py (two independent ML potentials)",
        "sun_validate.py (hull, formability, novelty)",
        "perovskite_geometry.py (corner-sharing test)",
        "prefetch_mp.py (Materials Project data, login node)",
        "relax_cache.py, stability_distorted.py (relaxation helpers)",
        "d1_mlip_check.py (two potentials on generated cells: drop on relaxation, displacement, space group kept)",
    ],
    "S8": [
        "cgcnn_judge.py (train and apply a judge on the user's own data)",
        "judge_consensus.py (agreement of qualified judges)",
    ],
    "S9": [
        "reliability_map.py (support and calibration)",
        "scorecard.py (the measured held-out label error)",
    ],
}
for _sid, _lst in STAGE_SCRIPTS.items():
    BY_ID[_sid].scripts = _lst


# What each dataset taught which block.  Read as a timeline: every entry is a change to the code that a specific test
# forced, so it is visible which testing improved which block — and how much of the pipeline is still Perov-5 shaped.
DATASET_HISTORY = [
    ("Perov-5", "11,356 structures, one cubic prototype, a complete 52x52x7 grid, 96% zero gaps", [
        ("S1/S4", "The published app read the label from the SEARCH latent and attached it to whatever composition was "
                  "decoded (2.57 eV discrepancy). Fixed by reading the label back from the returned structure; S4 now "
                  "measures 0.00 by construction and acts as a regression guard."),
        ("S1", "A `structure_property` loss was added so the property head is trained on structure latents: metal "
               "accuracy 4% -> 98%, and it is the single decisive switch (+62 points of hit rate)."),
        ("S5", "Search latents grew to |z| 4.18 in random directions. Constrained to the unit sphere; the latent-length "
               "sensitivity check became conditional, because at |z| = 1 the hazard cannot arise."),
        ("S3", "The decoder was trained with true atom positions but run with zeros (86 -> 0% recovery). Retrained under "
               "generation conditions."),
        ("S0", "A complete grid makes novelty and trustworthiness mutually exclusive: 0 of 148 novel candidates avoided "
               "unseen elements. The novelty frontier became an S0 metric."),
        ("all", "The ten blocks, their bands, and the executable validation against known-broken and known-good "
                "configurations were established here."),
    ]),
    ("Materials Project perovskites", "634 structures, 73 prototypes, realistic sparse coverage", [
        ("S3", "Composition recovery collapsed 64% -> 1.4%. The decoder autopsy ruled out collapse, cell size and "
               "prototype count, and isolated DENSITY: 12 compositions per element against Perov-5's 218. The density "
               "curve (12 -> 0.1%, 30 -> 0.7%, 80 -> 5.4%, 218 -> 64%) became the S0 rule that chooses generation or "
               "screening before training."),
        ("all", "Every component was made dataset-driven (EVAL_DATA / EVAL_GAP / EVAL_COST) instead of reading Perov-5's "
                "column names; `auto_family.py` learns a design space from any intake."),
        ("S0", "Oxidation states are now learned from the dataset's own charge balance rather than from pymatgen's coarse "
               "defaults, which had rejected real perovskites such as LaVO3 and LaMnO3."),
    ]),
    ("User upload", "246 structures, 21 prototypes, hybrid gaps and dielectric constants, no energy column", [
        ("S0", "Uploads arrive as a structure folder plus a spreadsheet, not a table: `ingest_upload.py` added. Names "
               "cannot join them (`Ba2YBiO6` vs `POSCAR_alpha-Ba2BiYO6`), so the join is on COMPOSITION: 142 -> 236 of "
               "246 rows matched, and the 10 that remain are reported rather than guessed."),
        ("S0", "`preview.py` added: block S0 as a gate that runs with no model in seconds. It predicted 'screening, not "
               "generation' and the trained decoder then measured 0.00%."),
        ("S9", "The support count, validated on Perov-5 (0.59 vs 0.95 eV), did NOT transfer: here support correlates "
               "-0.11 with error because the property is continuous rather than 96% zero. Added `superseded_by`: a "
               "metric that only PREDICTS a quantity becomes context once that quantity is measured, so the new "
               "`holdout_label_error` now decides S9."),
        ("S5", "The novelty rule compared site keys, which encode a family's group layout, so on a four-group A2BB'X6 "
               "family it matched nothing and excluded 0 while reporting success — 5 of 60 'novel' candidates were "
               "already in the user's data. Novelty is now judged on the reduced COMPOSITION, which is layout "
               "independent. Added additively: the site-key path Perov-5 uses is untouched and still removes 39 of 105."),
        ("S7", "A function-local import shadowed the module-level `Composition` and killed the hull step in every shard. "
                "Removed."),
        ("all", "Both bugs had one shape — a step reporting success while doing nothing. `announce_dataset()` and "
                "`warn_if_noop()` were added so that shape is visible rather than silent."),
    ]),
    ("MP-20", "45,229 structures, 89 elements, 6,282 prototypes, 68% zero gaps; the first dataset above the decoder's density threshold", [
        ("S5/S6", "Family-free generation: the search-latent label read the request back (windows always pass, the "
                  "defect fixed in generate.py but never ported here); the latent refinement pushed structures into "
                  "zero-gap metals; the species head returned MP-20's dominant intermetallic; 74% of cells exceeded the "
                  "encoder's max_sites and could not be checked.  Fixed at search time: label read from the returned structure, anchor only, one "
                  "anion required, cell capped.  Independent-judge MAE 2.00 -> 1.10 eV; two-judge consensus 37 of 175."),
        ("S3", "A symmetry (space group + representative sites) geometry path makes template-free cells buildable "
               "(0% -> 100%, all 230 space groups) once the lattice is projected onto the crystal system and symmetry "
               "images are merged by distance (0.8 A).  Refined cells, not conventional-standard ones, for the targets: "
               "the latter discarded 48% of orthorhombic structures including 96% of Pnma."),
        ("S3", "Coordinate accuracy is the open item: regression RMSE 0.24 and a 48-point discrete grid both leave "
               "structure-level accuracy unchanged, because a structure needs all ~13 components right.  The Wyckoff "
               "letter, which couples them, is the remaining route."),
    ]),
]


# What the bands MUST say about each configuration. This is the executable form of the validation.
# must_fail: known broken here, the bands have to catch it.  must_pass: known good here.
# may_warn: a WARN is acceptable.  documented_fail: a FAIL that IS the finding, with the reason recorded.
EXPECTATIONS = {
    "published": dict(must_fail=["S1", "S3", "S4", "S5", "S6"], must_pass=["S2"]),
    "control": dict(must_fail=["S1", "S3", "S4", "S5", "S6"], must_pass=[]),
    "fixed": dict(must_pass=["S1", "S2", "S4", "S6"], may_warn=["S3"],
                  documented_fail={"S5": "gradient search left the data manifold (max-cosine 0.342); this is what the "
                                         "on-manifold search in the final configuration fixes"}),
    "final": dict(must_pass=["S1", "S2", "S4", "S6", "S7", "S8"], may_warn=["S3"],
                  documented_fail={"S5": "the hit rate of the on-manifold search swings 83.3 vs 56.8 between seeds "
                                         "(26.5 points), so its advantage over the plain baseline is NOT proven — the "
                                         "band is right to fail it"}),
    "mp": dict(must_fail=["S3"], must_pass=["S2"], may_warn=["S1"]),
}


def reference_values(config: str) -> dict:
    return {mid: m.reference[config] for mid, (_s, m) in ALL_METRICS.items() if config in m.reference}


def grade_config(config: str) -> dict:
    """Stage verdicts for a configuration, from the stored reference values."""
    values = reference_values(config)
    out = {}
    for s in STAGES:
        if not any(m.id in values for m in s.metrics):
            continue
        verdict, grades = s.verdict(values, context=values)
        out[s.id] = (verdict, grades)
    return out


def validate(verbose=True) -> list:
    """Re-grade the stored Perov-5 references and report every contradiction with EXPECTATIONS."""
    problems = []
    for config, exp in EXPECTATIONS.items():
        graded = grade_config(config)
        if verbose:
            print(f"\n{config}  ({CONFIGS[config]['label']})")
            print(f"  known: {CONFIGS[config]['known']}")
        for sid, (verdict, grades) in sorted(graded.items()):
            detail = ", ".join(f"{k}={g}" for k, g in grades.items() if g != "INFO")
            if verbose:
                print(f"  {sid:3s} {verdict:4s}  {detail}")
            documented = exp.get("documented_fail", {})
            if sid in exp.get("must_fail", []) and verdict != "FAIL":
                problems.append(f"{config}/{sid}: expected FAIL (known broken here), got {verdict}")
            if sid in exp.get("must_pass", []) and verdict != "PASS":
                problems.append(f"{config}/{sid}: expected PASS (known good here), got {verdict}")
            if verdict == "FAIL" and sid in documented and verbose:
                print(f"      documented FAIL: {documented[sid]}")
            if (verdict == "FAIL" and sid not in exp.get("must_fail", []) and sid not in exp.get("may_warn", [])
                    and sid not in documented and sid != "S0"):
                problems.append(f"{config}/{sid}: unexpected FAIL — a band may be too strict, or the FAIL is a real "
                                f"finding that belongs in documented_fail")
        for sid in exp.get("must_fail", []) + exp.get("must_pass", []):
            if sid not in graded:
                problems.append(f"{config}/{sid}: expected a verdict but no reference value is stored")
    return problems


def markdown() -> str:
    L = ["# MEIDNet staged evaluation — reference bands, validated on Perov-5", "",
         "**Generated from `meidnet_fix/eval/stages.py` — edit that file, not this one.** Every script and the Matter app "
         "read their bands from it, so the document cannot drift from the code.", "",
         "A band is only accepted if it separates configurations whose quality we already know, and "
         "`python stages.py --validate` re-checks that on every edit:", ""]
    L += ["| column | configuration | checkup tag | what it is |", "|---|---|---|---|"]
    for k, c in CONFIGS.items():
        L.append(f"| **{k}** | {c['label']} | `{c['checkup']}` | {c['known']} |")
    L += ["", "Rule: a band that passes a known-broken configuration is wrong; a band that fails a known-good one without "
          "a documented reason is wrong. Units are relative (spreads, multiples of chance, multiples of a random baseline) "
          "so they transfer to other datasets.", ""]

    for s in STAGES:
        L += [f"## {s.id} — {s.name}: *\"{s.question}\"*", "", f"{s.purpose}", "",
              f"*Runs:* {s.when}. *Stage verdict:* {s.verdict_rule}.", ""]
        L += ["| metric | PASS | WARN | FAIL | " + " | ".join(CONFIGS) + " |",
              "|---|---|---|---|" + "---|" * len(CONFIGS)]
        for m in s.metrics:
            p, w, f = m.band_text()
            cells = []
            for cfg in CONFIGS:
                v = m.reference.get(cfg)
                if v is None:
                    cells.append("—")
                else:
                    g = m.grade(v, context=reference_values(cfg))
                    cells.append(f"{v:g} {g}" if g != "INFO" else f"{v:g}")
            cond = " *(conditional)*" if m.conditional_on else ""
            L.append(f"| **{m.name}**{cond} ({m.unit}) | {p} | {w} | {f} | " + " | ".join(cells) + " |")
        L.append("")
        for m in s.metrics:
            bits = [f"**{m.name}** — {m.definition}"]
            if not m.info_only and m.pass_at is not None:
                bits.append(f"Good: {m.meaning_good} Bad: {m.meaning_bad} **Remedy:** {m.remedy}")
            else:
                bits.append(m.remedy)
            if m.conditional_on:
                bits.append(f"Graded only when `{m.conditional_on[0]}` is "
                            f"{'above' if m.conditional_on[1] == 'gt' else 'below'} {m.conditional_on[2]:g}.")
            if m.recalibrated:
                bits.append(f"**Recalibrated:** {m.recalibrated}")
            if m.reference_note:
                bits.append(f"*Measured:* {m.reference_note}")
            if not m.dataset_agnostic:
                bits.append(f"*Not dataset-agnostic:* {m.new_dataset_note}")
            elif m.new_dataset_note:
                bits.append(f"*On a new dataset:* {m.new_dataset_note}")
            bits.append(f"Computed by `{m.computed_by}`.")
            L += ["- " + " ".join(bits)]
        if s.caveats:
            L += [""] + [f"> **Caveat.** {c}" for c in s.caveats]
        L.append("")

    L += ["## How each dataset improved which block", "",
          "Read as a timeline. Every entry is a change that a specific test forced, so it is visible which testing "
          "improved which block — and how much of the pipeline is still shaped by the dataset it was born on.", ""]
    for name, desc, items in DATASET_HISTORY:
        L += [f"### {name}", "", f"*{desc}*", "", "| block | what this dataset forced |", "|---|---|"]
        L += [f"| **{b}** | {t} |" for b, t in items]
        L.append("")
    L += ["## Which component implements which block", "",
          "One answer to \"where does block Sx live?\". A component may serve several blocks; the block, not the file "
          "name, is the unit of meaning.", "", "| block | components |", "|---|---|"]
    for st in STAGES:
        L.append(f"| **{st.id}** {st.name} ({st.when}) | " + "<br>".join(f"`{x}`" for x in st.scripts) + " |")
    L += ["", "### Guards against silent failure", "",
          "Two real bugs on the first external upload had the same shape: a step reported success while doing nothing — "
          "the novelty rule excluded 0 compositions because its site keys could not match a four-group family, and a "
          "shadowed import killed a hull step in every shard. Neither crashed, and both produced plausible output. "
          "Two helpers in `stages.py` make that shape visible:", "",
          "* `announce_dataset(script, data, **columns)` — every component prints the dataset and columns it is about to "
          "use. Seven active components default to the built-in Perov-5 paths, so a forgotten environment variable would "
          "otherwise evaluate the wrong data and report perfectly plausible numbers. `MEIDNET_STRICT=1` turns that "
          "default into an error.",
          "* `warn_if_noop(step, before, after, reference_size)` — a filter that removes nothing, while holding a "
          "non-empty reference set, says so loudly instead of passing silently.", "",
          "**Rule for new components: a step that can legitimately remove nothing must still report what it compared "
          "against.**", "",
          "## Validation table", "",
          "Each cell is the verdict these bands give that configuration, computed from the stored measurements by "
          "`stages.py --validate`.", "", "| block | " + " | ".join(CONFIGS) + " |", "|---|" + "---|" * len(CONFIGS)]
    graded = {c: grade_config(c) for c in CONFIGS}
    notes, seen = [], {}
    for s in STAGES:
        row = [f"**{s.id}** {s.name}"]
        for c in CONFIGS:
            v = graded[c].get(s.id, ("\u2014",))[0]
            doc = EXPECTATIONS.get(c, {}).get("documented_fail", {}).get(s.id)
            if v == "FAIL" and doc:
                key = (c, s.id)
                if key not in seen:
                    seen[key] = len(notes) + 1
                    notes.append(f"{seen[key]}. **{c} / {s.id} FAIL is the finding, not a miscalibration:** {doc}")
                v = f"FAIL[^{seen[key]}]"
            row.append(v)
        L.append("| " + " | ".join(row) + " |")
    if notes:
        L += [""] + notes
    L += ["", "The bands do what they are for: every block the X-ray found broken in the published app is FAIL, and the "
          "one block that was never broken (S2 alignment) is PASS in all of them, including the broken app \u2014 the "
          "evaluation localises the fault instead of smearing it. The good configurations pass every block except where a "
          "WARN or a FAIL is declared above with its reason (decoder recovery limited by data density; the on-manifold "
          "search not reproducible across seeds). S0 FAILs everywhere on Perov-5 because it is a complete grid with 96% "
          "zero gaps: a property of the dataset, reported rather than hidden.", "",
          "**Not claimed.** No DFT was run in this project: S7 stability rests on two ML potentials agreeing. Recovery "
          "from the property latent alone is 0% in every configuration. The bands for S0, S5 seed spread, S7 and S8 come "
          "from one dataset family and should be revisited as more datasets pass through: they are reference bands, not "
          "constants of nature.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true"); ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--show")
    ap.add_argument("--out", default=None, help="where --markdown writes (required with --markdown)")
    ap.add_argument("--json", default=None, help="also write export_blocks() as JSON to this path")
    a = ap.parse_args()
    if a.show:
        s = BY_ID[a.show.upper()]
        print(f"{s.id} {s.name}: {s.question}\n{s.purpose}\nruns: {s.when}\n")
        for m in s.metrics:
            p, w, f = m.band_text()
            print(f"  {m.id:28s} {m.unit:22s} PASS {p:8s} WARN {w:8s} FAIL {f:8s} refs {m.reference}")
        return
    if a.markdown:
        if not a.out:
            raise SystemExit("--markdown needs --out PATH")
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(markdown())
        print(f"wrote {a.out} ({len(STAGES)} blocks, {len(ALL_METRICS)} metrics)", file=sys.stderr)
    if a.json:
        import json
        with open(a.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(export_blocks(), f, indent=1, ensure_ascii=False, sort_keys=True)
        print(f"wrote {a.json}", file=sys.stderr)
    if a.validate or not (a.markdown or a.show):
        problems = validate()
        print("\n" + "=" * 70)
        if problems:
            print(f"{len(problems)} CONTRADICTION(S) between the bands and what we know:")
            for p in problems:
                print("  -", p)
            raise SystemExit(1)
        print(f"bands validated: {len(STAGES)} blocks, {len(ALL_METRICS)} metrics, "
              f"{len(EXPECTATIONS)} configurations, no contradictions")


def export_blocks() -> dict:
    """Everything the blocks define, as plain data for a page or a report.

    The `published` configuration is left out: its reference values exist only to validate the bands against the
    original application and are not a result to show.  Grades of reference values are recomputed here, so a page
    and the validation can never disagree.
    """
    skip = {"published"}
    configs = {k: (dict(v) if isinstance(v, dict) else {"label": str(v)}) for k, v in CONFIGS.items() if k not in skip}

    def metric(m):
        p, w, f = m.band_text()
        refs = {k: v for k, v in m.reference.items() if k not in skip}
        grades = {}
        for k, v in refs.items():
            try:
                grades[k] = m.grade(v, reference_values(k) if k in CONFIGS else None)
            except Exception:
                grades[k] = "INFO"
        return {"id": m.id, "name": m.name, "definition": m.definition, "unit": m.unit, "better": m.better,
                "pass_at": m.pass_at, "warn_at": m.warn_at, "band": {"pass": p, "warn": w, "fail": f},
                "meaning_good": m.meaning_good, "meaning_bad": m.meaning_bad, "remedy": m.remedy,
                "computed_by": m.computed_by, "info_only": m.info_only,
                "conditional_on": list(m.conditional_on) if m.conditional_on else None, "cap": m.cap,
                "superseded_by": m.superseded_by, "recalibrated": m.recalibrated,
                "dataset_agnostic": m.dataset_agnostic, "new_dataset_note": m.new_dataset_note,
                "reference": refs, "reference_grades": grades, "reference_note": m.reference_note}

    table = {}
    for cfg in configs:
        try:
            g = grade_config(cfg)
        except Exception:
            continue
        table[cfg] = {blk: (v[0] if isinstance(v, (tuple, list)) else v) for blk, v in (g or {}).items() if v is not None}
    return {"schema": "meidnet-matter/pipeline-blocks/1", "grades": ["PASS", "WARN", "FAIL", "INFO"], "configs": configs,
            "blocks": [{"id": st.id, "name": st.name, "question": st.question, "purpose": st.purpose, "when": st.when,
                        "verdict_rule": st.verdict_rule, "caveats": list(st.caveats),
                        "metrics": [metric(m) for m in st.metrics],
                        "components": list(STAGE_SCRIPTS.get(st.id, []))} for st in STAGES],
            "dataset_history": [{"dataset": name, "description": desc, "items": [{"blocks": b, "text": t} for b, t in items]}
                                for name, desc, items in DATASET_HISTORY],
            "validation_table": table}


if __name__ == "__main__":
    main()


# ───────────────────────── guards against the failure class that bit us twice ─────────────────────────
# Both real bugs on the user upload were the same shape: a step reported success while doing nothing (the novelty rule
# excluded 0 because its site keys could not match a 4-group family; a shadowed import killed a hull step in every shard).
# Neither crashed. These helpers make that shape visible instead of silent.

def announce_dataset(script, data, **columns):
    """Print the dataset and columns a component is about to use.

    Seven active components default to the Perov-5 paths, so a forgotten environment variable would silently evaluate the
    wrong dataset and report perfectly plausible numbers. One printed line makes that impossible to miss.
    """
    import os
    bits = " ".join(f"{k}={v}" for k, v in columns.items() if v)
    print(f"[{script}] dataset: {data}" + (f" | {bits}" if bits else ""), flush=True)
    if os.environ.get("MEIDNET_STRICT") and "meidnet_matter_fidelity_check" in str(data):
        raise SystemExit(f"{script}: MEIDNET_STRICT is set and the dataset is the built-in Perov-5 default "
                         f"({data}); pass the dataset explicitly.")
    return data


def warn_if_noop(step, before, after, reference_size=None):
    """A filter that removes nothing, when it had something to compare against, is reported rather than passed over."""
    removed = before - after
    note = f"[{step}] {before} -> {after} ({removed} removed"
    note += f"; reference set {reference_size})" if reference_size is not None else ")"
    print(note, flush=True)
    if removed == 0 and reference_size:
        print(f"  WARNING: {step} removed nothing although its reference set holds {reference_size} entries. "
              f"Check that the two sides are comparable — this is exactly how the novelty rule failed silently on a "
              f"four-group family.", flush=True)
    return after
