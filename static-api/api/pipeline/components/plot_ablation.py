"""Small multiples: for every ablation setting, the band gap of each returned structure (DFT where Perov-5 has it,
else the CGCNN judge on the relaxed cell) against the target, with the label the engine shows and the diagonal."""
import os
import numpy as np
import pandas as pd
import matplotlib
def main():
    """The script's work; nothing runs on import."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    HERE = os.path.dirname(os.path.abspath(__file__))
    RES = f"{HERE}/results"
    SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#5f5e58", "#e4e3dc"
    TRUE_C, LABEL_C = "#2a78d6", "#eb6834"      # categorical slots 1 and 2 of the reference palette

    allc = pd.read_csv(f"{RES}/all_candidates_enriched.csv")
    tab = pd.read_csv(f"{RES}/ablation_table.csv").set_index("tag")
    order = [t for t in ["R", "O", "G0", "G2", "G5", "AR", "OA", "OAall", "ARs1", "OAs1", "G7", "S0", "G1", "G6", "G3", "G4", "G5w1000",
                         "G8", "G9", "G10", "V2S", "V2S1S"] if t in tab.index]
    allc["truth"] = allc.dft_gap.fillna(allc.cgcnn_gap)
    ncol = 4; nrow = int(np.ceil(len(order) / ncol))
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "text.color": INK, "font.family": "DejaVu Sans"})
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.4 * ncol, 2.9 * nrow + 1.1), sharex=True, sharey=True, facecolor=SURFACE)
    axes = np.atleast_2d(axes)
    rng = np.random.RandomState(0)
    for k, ax in enumerate(axes.flat):
        if k >= len(order):
            ax.axis("off"); continue
        tag = order[k]; d = allc[allc.tag == tag]; r = tab.loc[tag]
        ax.set_facecolor(SURFACE); ax.grid(True, color=GRID, linewidth=0.7); ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.plot([0, 6.5], [0, 6.5], color=INK2, linestyle=(0, (4, 3)), linewidth=1.0, zorder=1)
        jit = rng.uniform(-0.16, 0.16, len(d))
        if d.label_gap.notna().any():
            ax.scatter(d.target + jit - 0.1, d.label_gap, s=14, color=LABEL_C, edgecolor=SURFACE, linewidth=0.8, zorder=3)
        ax.scatter(d.target + jit + 0.1, d.truth, s=14, color=TRUE_C, edgecolor=SURFACE, linewidth=0.8, zorder=3)
        m = d.groupby("target").truth.mean()
        if len(m) > 1:
            ax.plot(m.index + 0.1, m.values, color=TRUE_C, linewidth=1.8, zorder=4)
        rho = r.rho_dft
        ax.set_title(f"{tag}: {r.model}", loc="left", fontsize=9.5, color=INK, pad=14)
        ax.text(0.0, 1.015, f"labels {r.labels} · latent {r.latent} · pull {r.manifold}", transform=ax.transAxes, fontsize=7.5, color=INK2)
        ax.text(0.03, 0.96, f"ρ(DFT) {rho:+.2f}" if np.isfinite(rho) else "ρ(DFT) n/a", transform=ax.transAxes, fontsize=8.5,
                color=INK, va="top", fontweight="bold")
        ax.text(0.03, 0.85, f"{int(r.returned)} returned · {int(r.distinct)} distinct", transform=ax.transAxes, fontsize=7.5, color=INK2, va="top")
        ax.set_xlim(-0.5, 6.5); ax.set_ylim(-0.3, 7.3); ax.set_xticks(range(7))
    for ax in axes[-1]:
        ax.set_xlabel("Target gap (eV)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Band gap (eV)")
    handles = [Line2D([], [], marker="o", linestyle="", color=TRUE_C, markersize=5), Line2D([], [], color=TRUE_C, linewidth=1.8),
               Line2D([], [], marker="o", linestyle="", color=LABEL_C, markersize=5), Line2D([], [], color=INK2, linestyle=(0, (4, 3)))]
    labels = ["Gap of the returned structure (DFT, else CGCNN on relaxed cell)", "Mean per target",
              "Gap the engine shows (label)", "Perfect conditioning"]
    fig.suptitle("Ablation: which part of the pipeline makes generation follow the band-gap target?", x=0.01, ha="left",
                 fontsize=12.5, fontweight="bold", color=INK)
    fig.legend(handles, labels, loc="upper left", ncol=4, frameon=False, bbox_to_anchor=(0.005, 1 - 0.55 / fig.get_figheight()),
               fontsize=8.5, labelcolor=INK)
    fig.tight_layout(rect=(0, 0, 1, 1 - 1.0 / fig.get_figheight()))
    fig.savefig(f"{RES}/ablation_chart.png", dpi=150, facecolor=SURFACE)
    print("saved", f"{RES}/ablation_chart.png")


if __name__ == "__main__":
    main()
