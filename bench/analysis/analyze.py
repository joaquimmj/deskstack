"""Statistical analysis of deskstack-bench.

Reads the committed scorer summaries (denominators, cost, time) and the hand-read counts in hand_read.json
(numerators), and writes:

  bench/analysis/output/stats.json   every number quoted in the paper
  bench/analysis/output/tables.md    the same, as tables
  bench/analysis/output/fig_*.pdf    figures (and .png)

Run from the repository root:

  python3 bench/analysis/analyze.py

Needs numpy, scipy, pandas and matplotlib. Deterministic: the bootstrap uses a fixed seed.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
SEED = 20261109
N_BOOT = 20_000
ARMS = ["A", "B", "C"]
ARM_LABEL = {"A": "A: web search only", "B": "B: sourced data", "C": "C: sourced data + reviewers"}


# ---------------------------------------------------------------------------------------------------------------
# Interval estimators
# ---------------------------------------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (Clopper-Pearson) interval; the right one to quote for 0 of n."""
    lo = 0.0 if k == 0 else stats.beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(1 - alpha / 2, k + 1, n - k)
    return (float(lo), float(hi))


def newcombe_diff(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """Difference p1 - p2 with Newcombe's hybrid score interval (method 10)."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    lo = d - np.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + np.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (d, float(lo), float(hi))


def fisher(k1: int, n1: int, k2: int, n2: int) -> float:
    """Two-sided Fisher exact test on a 2x2 table."""
    return float(stats.fisher_exact([[k1, n1 - k1], [k2, n2 - k2]])[1])


def mcnemar_exact(b: int, c: int) -> float:
    """Exact McNemar test from the two discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    return float(min(1.0, 2 * stats.binom.cdf(min(b, c), n, 0.5)))


def cluster_bootstrap_rate(errors_by_cluster: np.ndarray, figures_by_cluster: np.ndarray, rng) -> dict:
    """Percentile bootstrap over companies (the sampling unit), for a ratio of sums."""
    n = len(errors_by_cluster)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    rates = errors_by_cluster[idx].sum(1) / figures_by_cluster[idx].sum(1)
    lo, hi = np.percentile(rates, [2.5, 97.5])
    point = errors_by_cluster.sum() / figures_by_cluster.sum()
    # Design effect: variance under clustering over variance under independent figures.
    p = point
    var_iid = p * (1 - p) / figures_by_cluster.sum()
    deff = float(rates.var(ddof=1) / var_iid) if var_iid > 0 else float("nan")
    return {"rate": float(point), "ci95": [float(lo), float(hi)], "design_effect": deff}


# ---------------------------------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------------------------------


def load_arms(results_dir: str) -> pd.DataFrame:
    summary = json.loads((ROOT / results_dir / "summary.json").read_text())
    df = pd.DataFrame(summary["arms"]).set_index("arm")
    return df


def proportion_row(label: str, k: int, n: int) -> dict:
    w = wilson(k, n)
    cp = clopper_pearson(k, n)
    return {"label": label, "k": k, "n": n, "rate": k / n if n else float("nan"),
            "wilson95": list(w), "exact95": list(cp)}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    hand = json.loads((HERE / "hand_read.json").read_text())
    res: dict = {"seed": SEED, "n_boot": N_BOOT}

    # ---- Per-task error rates and comparisons ------------------------------------------------------------------
    task_frames = {}
    for task in ("dcf", "comps"):
        h = hand[task]
        df = load_arms(h["results_dir"])
        task_frames[task] = df
        block = {"arms": {}, "comparisons": {}}
        for arm in ARMS:
            n = int(df.loc[arm, "checked"])
            k = int(h["wrong"][arm])
            row = proportion_row(ARM_LABEL[arm], k, n)
            row.update({
                "runs": int(df.loc[arm, "runs"]),
                "valid": int(df.loc[arm, "valid"]),
                "avg_cost_usd": float(df.loc[arm, "avg_cost"]),
                "avg_seconds": float(df.loc[arm, "avg_seconds"]),
                "avg_tokens": float(df.loc[arm, "avg_tokens"]),
                "unsourced_pct": float(df.loc[arm, "unsourced"] / df.loc[arm, "typed"]),
            })
            if "placeholders" in h:
                row["placeholders"] = int(h["placeholders"][arm])
            block["arms"][arm] = row
        a = block["arms"]["A"]
        for other in ("B", "C"):
            o = block["arms"][other]
            d, lo, hi = newcombe_diff(a["k"], a["n"], o["k"], o["n"])
            block["comparisons"][f"A_vs_{other}"] = {
                "risk_difference": d, "newcombe95": [lo, hi],
                "fisher_p": fisher(a["k"], a["n"], o["k"], o["n"]),
                "cost_ratio": o["avg_cost_usd"] / a["avg_cost_usd"],
                "time_ratio": o["avg_seconds"] / a["avg_seconds"],
            }
        res[task] = block

    # ---- DCF: company-level paired test and cluster bootstrap ----------------------------------------------------
    h = hand["dcf"]
    n_comp = 50
    errs = np.zeros(n_comp)
    vals = list(h["errors_by_company_A"].values())
    errs[: len(vals)] = vals
    assert errs.sum() == h["wrong"]["A"], "per-company errors must add up to the hand-read total"
    n_checked_A = res["dcf"]["arms"]["A"]["n"]
    # Per-company denominators are not in the committed summaries (the raw runs are). We spread the checked
    # figures evenly across companies; the sensitivity check below shows the interval barely moves when they vary.
    figs_even = np.full(n_comp, n_checked_A / n_comp)
    boot_even = cluster_bootstrap_rate(errs, figs_even, rng)
    sens = []
    for _ in range(200):
        w = rng.dirichlet(np.full(n_comp, 8.0))  # moderate spread in figures per company
        figs = w * n_checked_A
        sens.append(cluster_bootstrap_rate(errs, figs, np.random.default_rng(rng.integers(1 << 32)))["ci95"])
    sens = np.array(sens)
    k_comp = h["companies_with_wrong"]["A"]
    res["dcf"]["company_level"] = {
        "companies_with_wrong_A": proportion_row("companies with a wrong figure, arm A", k_comp, n_comp),
        "companies_with_wrong_B": proportion_row("companies with a wrong figure, arm B", 0, int(task_frames["dcf"].loc["B", "valid"])),
        "companies_with_wrong_C": proportion_row("companies with a wrong figure, arm C", 0, int(task_frames["dcf"].loc["C", "valid"])),
        # Paired by company: A wrong & B clean = discordant pairs, B wrong & A clean = 0.
        # B finished 49 of 50. The committed summaries don't say which company B missed, so the A-vs-B test is
        # computed conservatively, as if that company were one of A's 12 (11 usable discordant pairs).
        "mcnemar_A_vs_B_p": mcnemar_exact(k_comp - 1, 0),
        "mcnemar_A_vs_C_p": mcnemar_exact(k_comp, 0),
        "cluster_bootstrap_A": boot_even,
        "cluster_bootstrap_A_sensitivity_ci95_range": {
            "lower": [float(sens[:, 0].min()), float(sens[:, 0].max())],
            "upper": [float(sens[:, 1].min()), float(sens[:, 1].max())],
        },
        "max_errors_in_one_company": int(errs.max()),
        "share_of_errors_in_top3_companies": float(np.sort(errs)[-3:].sum() / errs.sum()),
    }

    # ---- Pooled across both tasks ---------------------------------------------------------------------------------
    kA = res["dcf"]["arms"]["A"]["k"] + res["comps"]["arms"]["A"]["k"]
    nA = res["dcf"]["arms"]["A"]["n"] + res["comps"]["arms"]["A"]["n"]
    kBC = sum(res[t]["arms"][a]["k"] for t in ("dcf", "comps") for a in ("B", "C"))
    nBC = sum(res[t]["arms"][a]["n"] for t in ("dcf", "comps") for a in ("B", "C"))
    d, lo, hi = newcombe_diff(kA, nA, kBC, nBC)
    res["pooled"] = {
        "A": proportion_row("A, both tasks", kA, nA),
        "B_and_C": proportion_row("B and C, both tasks", kBC, nBC),
        "risk_difference": d, "newcombe95": [lo, hi], "fisher_p": fisher(kA, nA, kBC, nBC),
        # Cochran-Mantel-Haenszel across the two tasks (strata), A against B+C.
        "cmh": cmh_test([
            (res[t]["arms"]["A"]["k"], res[t]["arms"]["A"]["n"],
             res[t]["arms"]["B"]["k"] + res[t]["arms"]["C"]["k"], res[t]["arms"]["B"]["n"] + res[t]["arms"]["C"]["n"])
            for t in ("dcf", "comps")
        ]),
        # How many figures B+C would need for one error at A's rate, and the rule-of-three bound.
        "rule_of_three_upper_BC": 3 / nBC,
    }

    # ---- Robustness (pre-registered) ----------------------------------------------------------------------------------
    rb = hand["robustness"]["settings"]
    a12, a30 = rb["A12"], rb["A30"]
    res["robustness"] = {
        "A12": proportion_row("A12 wrong", a12["wrong"], a12["checked"]),
        "A30": proportion_row("A30 wrong", a30["wrong"], a30["checked"]),
        "wrong_fisher_p": fisher(a12["wrong"], a12["checked"], a30["wrong"], a30["checked"]),
        "A12_placeholders": a12["placeholders"], "A30_placeholders": a30["placeholders"],
        "cost_per_table": {"A12": a12["spend"] / a12["tables"], "A30": a30["spend"] / a30["tables"]},
        "pre_registered_claim_holds": a30["wrong"] > 0,
        # Power: with A's main-run rate, chance that 117 figures show zero errors if nothing changed.
        "p_zero_errors_at_main_rate": float((1 - res["comps"]["arms"]["A"]["rate"]) ** a30["checked"]),
    }

    # ---- Error taxonomy -------------------------------------------------------------------------------------------------
    res["taxonomy"] = {"dcf_wrong": hand["dcf"]["causes_A"], "dcf_not_wrong": hand["dcf"]["not_wrong_A"],
                       "comps_wrong": hand["comps"]["causes_A"]}
    flagged = hand["dcf"]["not_wrong_A"]
    res["dcf"]["scorer_precision_A"] = {
        "scorer_mismatches_after_rescore": int(task_frames["dcf"].loc["A", "mismatch"]),
        "confirmed_wrong_by_hand": hand["dcf"]["wrong"]["A"],
        "precision": hand["dcf"]["wrong"]["A"] / int(task_frames["dcf"].loc["A", "mismatch"]),
    }
    res["comps"]["scorer_precision_A"] = {
        "scorer_mismatches_after_rescore": int(task_frames["comps"].loc["A", "mismatch"]),
        "confirmed_wrong_by_hand": hand["comps"]["wrong"]["A"],
        "precision": hand["comps"]["wrong"]["A"] / int(task_frames["comps"].loc["A", "mismatch"]),
    }

    (OUT / "stats.json").write_text(json.dumps(res, indent=2))
    write_tables(res)
    make_figures(res, hand)
    print(f"Wrote {OUT/'stats.json'}, {OUT/'tables.md'} and figures.")


def cmh_test(strata: list[tuple[int, int, int, int]]) -> dict:
    """Cochran-Mantel-Haenszel chi-square (with continuity correction) and Mantel-Haenszel risk difference."""
    num, var, rd_num, rd_den = 0.0, 0.0, 0.0, 0.0
    for k1, n1, k2, n2 in strata:
        t = n1 + n2
        m1 = k1 + k2
        e = n1 * m1 / t
        num += k1 - e
        var += n1 * n2 * m1 * (t - m1) / (t**2 * (t - 1))
        w = n1 * n2 / t
        rd_num += w * (k1 / n1 - k2 / n2)
        rd_den += w
    chi2 = (abs(num) - 0.5) ** 2 / var
    return {"chi2": float(chi2), "p": float(stats.chi2.sf(chi2, 1)), "mh_risk_difference": float(rd_num / rd_den)}


def pct(x: float, d: int = 1) -> str:
    return f"{100*x:.{d}f}%"


def write_tables(res: dict) -> None:
    lines = ["# deskstack-bench: statistical tables", "",
             "Generated by `bench/analysis/analyze.py`. Intervals are 95%: Wilson for proportions, Clopper-Pearson "
             "(exact) for zero counts, Newcombe for differences.", ""]
    for task, title in (("dcf", "DCF (50 companies)"), ("comps", "Comps (49 companies with all arms)")):
        lines += [f"## {title}", "", "| Arm | Wrong / checked | Rate | 95% CI | Avg cost | Avg time |", "|---|---|---|---|---|---|"]
        for arm in ARMS:
            r = res[task]["arms"][arm]
            ci = r["exact95"] if r["k"] == 0 else r["wilson95"]
            lines.append(f"| {r['label']} | {r['k']} / {r['n']} | {pct(r['rate'],2)} | {pct(ci[0],2)} to {pct(ci[1],2)} | "
                         f"${r['avg_cost_usd']:.2f} | {r['avg_seconds']:.0f} s |")
        lines.append("")
        for k, c in res[task]["comparisons"].items():
            lines.append(f"- {k.replace('_',' ')}: difference {pct(c['risk_difference'],2)} "
                         f"(95% CI {pct(c['newcombe95'][0],2)} to {pct(c['newcombe95'][1],2)}), Fisher p = {c['fisher_p']:.1e}; "
                         f"cost ×{c['cost_ratio']:.2f}, time ×{c['time_ratio']:.2f}")
        lines.append("")
    cl = res["dcf"]["company_level"]
    b = cl["cluster_bootstrap_A"]
    lines += ["## DCF at the company level", "",
              f"- Companies with at least one wrong figure: A {cl['companies_with_wrong_A']['k']}/50 "
              f"({pct(cl['companies_with_wrong_A']['rate'],0)}, 95% CI {pct(cl['companies_with_wrong_A']['wilson95'][0],0)} to "
              f"{pct(cl['companies_with_wrong_A']['wilson95'][1],0)}); B 0/49; C 0/50.",
              f"- Exact McNemar, paired by company: A vs B p = {cl['mcnemar_A_vs_B_p']:.1e}; A vs C p = {cl['mcnemar_A_vs_C_p']:.1e}.",
              f"- Arm A error rate with a bootstrap over companies: {pct(b['rate'],2)} (95% CI {pct(b['ci95'][0],2)} to "
              f"{pct(b['ci95'][1],2)}), design effect {b['design_effect']:.2f}.",
              f"- The 3 companies with the most errors hold {pct(cl['share_of_errors_in_top3_companies'],0)} of them.", ""]
    p = res["pooled"]
    lines += ["## Both tasks pooled", "",
              f"- A: {p['A']['k']}/{p['A']['n']} ({pct(p['A']['rate'],2)}, 95% CI {pct(p['A']['wilson95'][0],2)} to {pct(p['A']['wilson95'][1],2)}).",
              f"- B and C: {p['B_and_C']['k']}/{p['B_and_C']['n']} (exact 95% upper bound {pct(p['B_and_C']['exact95'][1],2)}).",
              f"- CMH across tasks: chi2 = {p['cmh']['chi2']:.1f}, p = {p['cmh']['p']:.1e}; MH risk difference {pct(p['cmh']['mh_risk_difference'],2)}.", ""]
    r = res["robustness"]
    lines += ["## Robustness (pre-registered)", "",
              f"- A12: {r['A12']['k']}/{r['A12']['n']} wrong, {r['A12_placeholders']} placeholders, ${r['cost_per_table']['A12']:.2f} per table.",
              f"- A30: {r['A30']['k']}/{r['A30']['n']} wrong, {r['A30_placeholders']} placeholders, ${r['cost_per_table']['A30']:.2f} per table.",
              f"- Fisher on wrong figures: p = {r['wrong_fisher_p']:.2f} (no detectable difference; the sample is small).",
              f"- Probability of seeing zero errors in 117 figures at the main comps rate: {pct(r['p_zero_errors_at_main_rate'],1)}.", ""]
    (OUT / "tables.md").write_text("\n".join(lines))


def make_figures(res: dict, hand: dict) -> None:
    plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    colors = {"A": "#b4492f", "B": "#2f6fb4", "C": "#3d8f5a"}

    # Figure 1: error rates with 95% CIs, per task.
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.4), sharey=True)
    for ax, task, title in zip(axes, ("dcf", "comps"), ("DCF", "Comps")):
        for i, arm in enumerate(ARMS):
            r = res[task]["arms"][arm]
            ci = r["exact95"] if r["k"] == 0 else r["wilson95"]
            ax.bar(i, 100 * r["rate"], color=colors[arm], width=0.6)
            ax.errorbar(i, 100 * r["rate"], yerr=[[100 * (r["rate"] - ci[0])], [100 * (ci[1] - r["rate"])]],
                        color="black", capsize=3, lw=0.8)
            ax.text(i, 100 * ci[1] + 0.25, f"{r['k']}/{r['n']}", ha="center", fontsize=7.5)
        ax.set_xticks(range(3), ["A\nweb search", "B\nsourced", "C\nsourced\n+ review"])
        ax.set_title(title)
    axes[0].set_ylabel("Wrong filed figures (%)")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig_error_rates.{ext}", dpi=200)
    plt.close(fig)

    # Figure 2: arm A error causes.
    fig, ax = plt.subplots(figsize=(6.6, 2.3))
    causes = {**{f"DCF: {k}": v for k, v in hand["dcf"]["causes_A"].items()},
              **{f"Comps: {k}": v for k, v in hand["comps"]["causes_A"].items()}}
    items = sorted(causes.items(), key=lambda kv: kv[1])
    ax.barh([k for k, _ in items], [v for _, v in items], color="#b4492f")
    for i, (_, v) in enumerate(items):
        ax.text(v + 0.2, i, str(v), va="center", fontsize=7.5)
    ax.set_xlabel("Wrong figures, arm A (read by hand)")
    ax.tick_params(axis="y", labelsize=7.5)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig_error_causes.{ext}", dpi=200)
    plt.close(fig)

    # Figure 3: cost and accuracy frontier.
    fig, ax = plt.subplots(figsize=(3.3, 2.4))
    for task, marker in (("dcf", "o"), ("comps", "s")):
        for arm in ARMS:
            r = res[task]["arms"][arm]
            ax.scatter(r["avg_cost_usd"], 100 * r["rate"], color=colors[arm], marker=marker, s=28, zorder=3)
    ax.scatter([], [], marker="o", color="grey", label="DCF")
    ax.scatter([], [], marker="s", color="grey", label="Comps")
    ax.set_xlabel("Average cost per model (USD)")
    ax.set_ylabel("Wrong figures (%)")
    ax.legend(frameon=False, fontsize=7.5)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig_cost_accuracy.{ext}", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
