from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.ticker as mticker
    import numpy as np
    import matplotlib.colors as mc
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

TOMME = {"", "-", "\u2013", "\u2014", "n/a", "na", "none", "null", "ikke udfyldt", "mangler", "-/-", "./.", "."}
SKIP = {"metadata.filnavn", "metadata.udfyldt_af"}
FRITEKST = {
    "klinisk_information.klinisk_resume",
    "klinisk_information.kommentar",
    "klinisk_information.patient_oplysninger_ved_optagelse",
    "klinisk_information.medicin",
    "test_oplysninger.henvisningsdiagnose",
    "test_oplysninger.henviser",
    "hjerte.ekg_bemaerkninger",
    "patient.navn",
    "sammenfatning.soevnmoenster",
    "sammenfatning.soevn_dagtid",
    "sammenfatning.anfald",
    "sammenfatning.beskrivelse",
    "sammenfatning.paroksystisk_aktivitet",
    "sammenfatning.fokal",
    "konklusion_og_plan.konklusion_tekst",
    "konklusion_og_plan.plan",
    "konklusion_og_plan.bedoemt_af",
}
NOMINALE = {
    "patient.cpr-nummer",
    "test_oplysninger.dato",
    "test_oplysninger.starttid",
    "test_oplysninger.sluttid",
    "test_oplysninger.montage",
    "oget_muskelaktivitet_rem.chin",
    "oget_muskelaktivitet_rem.tib",
    "oget_muskelaktivitet_rem.fds",
    "konklusion_og_plan.dato_for_bedoemmelse",
    "konklusion_og_plan.a_diagnose.kode",
    "konklusion_og_plan.a_diagnose.tekst",
    "konklusion_og_plan.b_diagnose.kode",
    "konklusion_og_plan.b_diagnose.tekst",
}
EMNEGRUPPER = {
    "Patient": ["patient.", "metadata."],
    "Test oplysninger": ["test_oplysninger."],
    "Klinisk information": ["klinisk_information."],
    "Soevn opsummering": ["soevn_opsummering."],
    "Soevnstadier": ["soevnstadier."],
    "Muskelaktivitet REM": ["oget_muskelaktivitet_rem."],
    "Respirationsanalyse": ["respirations_analyse."],
    "SpO2": ["spo2_oversigt."],
    "Benbevaegelser": ["benbevaegelser."],
    "Hjerte": ["hjerte."],
    "Sammenfatning": ["sammenfatning."],
    "Konklusion og plan": ["konklusion_og_plan."],
}
KATEGORI_FARVER = {
    "FORMAT": "#3B82F6",
    "UDELADELSE": "#EF4444",
    "NUMERISK_AFVIGELSE": "#8B5CF6",
    "FAKTUEL_FEJL": "#DC2626",
    "FRITEKST_DELVIS": "#F59E0B",
    "FRITEKST_DIVERGENS": "#EF4444",
}
GOLD_MISSING_ZERO_OK_FIELDS = {
    "benbevaegelser.plms_indeks.vaagen",
    "soevnstadier.vaagen.procent_af_tst",
    "benbevaegelser.lms_efterfulgt_af_arousals",
}

BAGGRUND = "#F9FAFB"
BLA = "#3B82F6"
GROEN = "#10B981"
ROED = "#EF4444"
GUL = "#F59E0B"
GRAA = "#D1D5DB"
MOERK = "#1F2937"
DAEMPET = "#6B7280"
PALETTER = ["#3B82F6", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444", "#06B6D4", "#EC4899", "#84CC16"]


def saet_stil():
    if not HAS_MATPLOTLIB:
        return
    plt.rcParams.update({
        "figure.facecolor": BAGGRUND,
        "axes.facecolor": "white",
        "axes.edgecolor": "#E5E7EB",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.spines.bottom": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": "#E5E7EB",
        "grid.linestyle": "-",
        "grid.linewidth": 1.0,
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "figure.dpi": 220,
        "text.color": MOERK,
        "axes.labelcolor": DAEMPET,
        "xtick.color": DAEMPET,
        "ytick.color": DAEMPET,
    })


def gem(fig, ud_mappe, filnavn, show=False):
    if not HAS_MATPLOTLIB:
        return
    if ud_mappe:
        ud = Path(ud_mappe) / filnavn
        fig.savefig(ud, bbox_inches="tight", facecolor=BAGGRUND)
        print(f"  Gemt: {ud}")
    if not show:
        plt.close(fig)


def _feld_key_label(felt):
    return (felt.split(".")[-2] + "." if felt.count(".") >= 2 else "") + felt.split(".")[-1]


def p_samlet(data, ud, show=False):
    if not HAS_MATPLOTLIB:
        return
    sorteret = sorted(data.items(), key=lambda x: x[1]["overall"] or 0)
    navne = [d["meta"].get("run_name", k) for k, d in sorteret]
    rater = [(d["overall"] or 0) * 100 for _, d in sorteret]
    rater_f = [(d.get("overall_faelles") or 0) * 100 for _, d in sorteret]
    har_faelles = any(d.get("overall_faelles") is not None for d in data.values())

    fig, ax = plt.subplots(figsize=(11, max(4, len(navne) * 0.8)))
    fig.patch.set_facecolor(BAGGRUND)
    y = np.arange(len(navne))
    h = 0.35 if har_faelles else 0.6

    ax.barh(y + (h / 2 if har_faelles else 0), rater,
            height=h, color=[PALETTER[i % len(PALETTER)] for i in range(len(navne))],
            edgecolor="white", linewidth=1.2, zorder=3, label="All reports")
    for i, rate in enumerate(rater):
        ax.text(min(rate + 0.8, 97), y[i] + (h / 2 if har_faelles else 0),
                f"{rate:.1f}%", va="center", ha="left", fontsize=8, fontweight="bold", color=MOERK)

    if har_faelles:
        ax.barh(y - h / 2, rater_f, height=h,
                color=[PALETTER[i % len(PALETTER)] for i in range(len(navne))],
                edgecolor="white", linewidth=1.2, zorder=3, alpha=0.45, label="Comparable subset*")
        for i, rate in enumerate(rater_f):
            if rate > 0:
                ax.text(min(rate + 0.8, 97), y[i] - h / 2, f"{rate:.1f}%", va="center", ha="left", fontsize=8, color=DAEMPET)

    ax.set_yticks(y)
    ax.set_yticklabels(navne)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Agreement (%)")
    ax.set_title("Overall Agreement per Run")
    ax.axvline(75, color=DAEMPET, linestyle="--", linewidth=1, alpha=0.6)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    if har_faelles:
        n_faelles = len(next(iter(data.values())).get("rapport_navne", set()) &
                        set.intersection(*[d.get("rapport_navne", set()) for d in data.values()]))
        ax.legend(fontsize=8, framealpha=0.9, edgecolor="none",
                  title=f"* n={n_faelles} rapporter alle modeller har koert", title_fontsize=7)
    else:
        ax.legend(fontsize=8, framealpha=0.9, edgecolor="none")
    fig.tight_layout()
    gem(fig, ud, "1_samlet_agreement.png", show)


def p_gruppe(data, ud, show=False):
    if not HAS_MATPLOTLIB:
        return
    alle_g = sorted({g for d in data.values() for g in d["gruppe"]})
    rn = list(data.keys())
    n = len(rn)
    br = min(0.8 / n, 0.25)
    x = np.arange(len(alle_g))
    fig, ax = plt.subplots(figsize=(max(12, len(alle_g) * 1.3), 6))
    fig.patch.set_facecolor(BAGGRUND)
    for idx, (rk, d) in enumerate(data.items()):
        label = d["meta"].get("run_name", rk)
        rater = [(d["gruppe"].get(g, {}).get("agreement") or 0) * 100 for g in alle_g]
        ax.bar(x + (idx - n / 2 + 0.5) * br, rater, br * 0.9, label=label,
               color=PALETTER[idx % len(PALETTER)], edgecolor="white", linewidth=0.8, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(alle_g, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Agreement (%)")
    ax.set_ylim(0, 115)
    ax.set_title("Agreement per Clinical Section")
    ax.axhline(75, color=DAEMPET, linestyle="--", linewidth=1, alpha=0.5)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.legend(fontsize=8, loc="lower right", framealpha=0.9, edgecolor="none")
    ax.grid(True, axis="y", linestyle="-", color="#E5E7EB", linewidth=1.0)
    fig.tight_layout()
    gem(fig, ud, "2_gruppe_sammenligning.png", show)


def p_fejl(data, ud, show=False):
    if not HAS_MATPLOTLIB:
        return
    alle_k = sorted({k for d in data.values() for k in d["kategorier"]})
    rl = list(data.keys())
    n = len(rl)
    x = np.arange(len(alle_k))
    br = min(0.8 / n, 0.25)
    fig, ax = plt.subplots(figsize=(max(10, len(alle_k) * 1.5), 5))
    fig.patch.set_facecolor(BAGGRUND)
    for idx, (rk, d) in enumerate(data.items()):
        vals = [d["kategorier"].get(k, 0) for k in alle_k]
        ax.bar(x + (idx - n / 2 + 0.5) * br, vals, br * 0.9, label=d["meta"].get("run_name", rk),
               color=PALETTER[idx % len(PALETTER)], edgecolor="white", linewidth=0.8, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(alle_k, fontsize=9)
    ax.set_ylabel("Count")
    ax.set_title("Disagreement Categories")
    ax.legend(fontsize=8, loc="upper right", framealpha=0.9, edgecolor="none")
    ax.grid(True, axis="y", linestyle="-", color="#E5E7EB", linewidth=1.0)
    fig.tight_layout()
    gem(fig, ud, "3_fejlkategorier.png", show)


def p_worst(data, ud, show=False, top_n=20):
    if not HAS_MATPLOTLIB:
        return
    bk = max(data, key=lambda k: data[k]["overall"] or 0)
    kand = [(f, s) for f, s in data[bk]["felt"].items() if s["n_sammenlignet"] >= 5 and s["agreement"] is not None]
    worst = sorted(kand, key=lambda x: x[1]["agreement"])[:top_n]
    if not worst:
        return
    felter = [_feld_key_label(f) for f, _ in worst]
    rater = [s["agreement"] * 100 for _, s in worst]
    farver = [GROEN if r >= 75 else GUL if r >= 50 else ROED for r in rater]
    fig, ax = plt.subplots(figsize=(11, max(5, len(felter) * 0.5)))
    fig.patch.set_facecolor(BAGGRUND)
    ax.barh(felter, rater, color=farver, height=0.65, edgecolor="white", linewidth=1.2, zorder=3)
    for i, rate in enumerate(rater):
        ax.text(rate + 0.8, i, f"{rate:.0f}%", va="center", ha="left", fontsize=8, color=MOERK)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Agreement (%)")
    ax.set_title(f"Bottom {top_n} Fields by Agreement  ({data[bk]['meta'].get('run_name', bk)})")
    ax.axvline(75, color=DAEMPET, linestyle="--", linewidth=1, alpha=0.5)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.legend(handles=[mpatches.Patch(color=GROEN, label=">= 75%"),
                       mpatches.Patch(color=GUL, label="50-75%"),
                       mpatches.Patch(color=ROED, label="< 50%")],
              fontsize=8, framealpha=0.9, edgecolor="none", loc="lower right")
    fig.tight_layout()
    gem(fig, ud, "4_worst_fields.png", show)


def p_heatmap(data, ud, show=False, top_n=25):
    if not HAS_MATPLOTLIB:
        return
    rn = list(data.keys())
    rlab = [d["meta"].get("run_name", k) for k, d in data.items()]
    alle_f = set()
    for d in data.values():
        alle_f |= {f for f, s in d["felt"].items() if s["n_sammenlignet"] >= 5}
    varians = {}
    for felt in alle_f:
        vals = [data[r]["felt"].get(felt, {}).get("agreement") for r in rn]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 2:
            varians[felt] = max(vals) - min(vals)
    top = sorted(varians, key=lambda f: -varians[f])[:top_n]
    if not top:
        return
    matrix = np.zeros((len(top), len(rn)))
    for j, r in enumerate(rn):
        for i, felt in enumerate(top):
            agr = data[r]["felt"].get(felt, {}).get("agreement")
            matrix[i, j] = agr * 100 if agr is not None else -1
    cmap = mc.LinearSegmentedColormap.from_list("agr", [(0, ROED), (0.5, GUL), (0.75, GROEN), (1, "#065F46")], N=256)
    kf = [_feld_key_label(f) for f in top]
    fig, ax = plt.subplots(figsize=(max(8, len(rn) * 2 + 4), max(6, len(top) * 0.45 + 2)))
    fig.patch.set_facecolor(BAGGRUND)
    masked = np.ma.masked_where(matrix < 0, matrix)
    im = ax.imshow(masked, cmap=cmap, aspect="auto", vmin=0, vmax=100)
    for i in range(len(top)):
        for j in range(len(rn)):
            v = matrix[i, j]
            if v < 0:
                continue
            tc = "white" if v < 40 or v > 80 else MOERK
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7, fontweight="bold", color=tc)
    ax.set_xticks(range(len(rn)))
    ax.set_xticklabels(rlab, rotation=25, ha="right", fontsize=8)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(kf, fontsize=8)
    ax.set_title(f"Agreement Heatmap - Top {top_n} Most Variable Fields")
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(labelsize=7)
    cbar.set_label("Agreement %", fontsize=8)
    fig.tight_layout()
    gem(fig, ud, "5_heatmap.png", show)


def p_runtime_agreement(data, queue_logs, ud, show=False):
    """Plot køretid vs. agreement for hver run."""
    if not HAS_MATPLOTLIB or not queue_logs:
        return
    
    rn = list(data.keys())
    rlab = [d["meta"].get("run_name", k) for k, d in data.items()]
    
    # Hent køretider og agreement
    runtime_min = []
    agreement_pct = []
    succes_rate = []
    
    for k in rn:
        if k in queue_logs:
            ql = queue_logs[k]
            runtime_min.append(ql.get("duration_seconds", 0) / 60)
            succ = ql.get("succeeded", 0)
            total = ql.get("n_reports", 1)
            succes_rate.append((succ / total) * 100 if total > 0 else 0)
        else:
            runtime_min.append(0)
            succes_rate.append(0)
        
        agr = data[k].get("overall", 0)
        agreement_pct.append((agr or 0) * 100)
    
    if not any(runtime_min):
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(BAGGRUND)
    
    # Scatter plot: runtime vs agreement, farvet efter success rate
    scatter = ax.scatter(runtime_min, agreement_pct, 
                        c=succes_rate, s=200, cmap="RdYlGn",
                        edgecolor="white", linewidth=1.5, vmin=0, vmax=100, zorder=3)
    
    # Tilføj labels for hver punkt
    for i, (rt, agr, lbl) in enumerate(zip(runtime_min, agreement_pct, rlab)):
        ax.annotate(lbl, (rt, agr), xytext=(5, 5), textcoords="offset points",
                   fontsize=8, ha="left", bbox=dict(boxstyle="round,pad=0.3", 
                   facecolor="white", alpha=0.7, edgecolor="none"))
    
    ax.set_xlabel("Runtime (minutter)")
    ax.set_ylabel("Agreement (%)")
    ax.set_title("Runtime vs Agreement (farve = success rate)")
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_ylim(0, 110)
    
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Success Rate (%)")
    
    fig.tight_layout()
    gem(fig, ud, "6_runtime_agreement.png", show)


def _is_zeroish(v) -> bool:
    try:
        return isinstance(v, (int, float)) and float(v) == 0.0
    except Exception:
        return False


def _to_serializable(o):
    """Recursively convert non-JSON types (sets, tuples, defaultdicts) to JSON-serializable types."""
    # dict-like (including defaultdict)
    if isinstance(o, dict):
        return {k: _to_serializable(v) for k, v in o.items()}
    # lists/tuples
    if isinstance(o, (list, tuple)):
        return [_to_serializable(v) for v in o]
    # sets -> sorted list for stable output
    if isinstance(o, set):
        try:
            return sorted(_to_serializable(v) for v in o)
        except Exception:
            return [_to_serializable(v) for v in o]
    # basic types pass through
    return o


def laes_queue_logs(results_dir, run_names=None):
    """Indlæs queue logs fra results_dir og match med run_names."""
    queue_logs = {}
    results_path = Path(results_dir)
    
    # Søg efter queue_log*.json filer
    for qf in sorted(results_path.glob("queue_log_*.json")):
        try:
            data = json.loads(qf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for entry in data:
                    run_name = entry.get("run_name")
                    if run_name and (run_names is None or run_name in run_names):
                        queue_logs[run_name] = entry
            else:
                run_name = data.get("run_name")
                if run_name and (run_names is None or run_name in run_names):
                    queue_logs[run_name] = data
        except Exception as e:
            pass  # bare spring over queue logs der ikke kan læses
    
    return queue_logs


def fladgor(d, prefix=""):
    items = {}
    if not isinstance(d, dict):
        return items
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(fladgor(v, key))
        else:
            items[key] = v
    return items


def indlaes(sti):
    try:
        ra = fladgor(json.loads(Path(sti).read_text(encoding="utf-8")))
    except json.JSONDecodeError as e:
        print(f"FEJL: {Path(sti).name}: {e}")
        sys.exit(1)
    return ra, ra.copy()


def emne(felt):
    for g, ps in EMNEGRUPPER.items():
        if any(felt.startswith(p) for p in ps):
            return g
    return "Andet"


def felttype(felt, na, nb):
    if felt in FRITEKST:
        return "fritekst"
    if felt in NOMINALE:
        return "nominal"
    if isinstance(na, (int, float)) or isinstance(nb, (int, float)):
        return "numerisk"
    return "nominal"


def f1(a, b):
    sa = str(a).lower() if a is not None else ""
    sb = str(b).lower() if b is not None else ""
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    sa = re.sub(r"[^\w]+", " ", sa, flags=re.UNICODE)
    sb = re.sub(r"[^\w]+", " ", sb, flags=re.UNICODE)
    ta, tb = set(sa.split()), set(sb.split())
    ov = ta & tb
    if not ov:
        return 0.0
    p = len(ov) / len(tb)
    r = len(ov) / len(ta)
    return 2 * p * r / (p + r)


def sammenlign(ra_p, np_, ra_g, ng_):
    alle = (set(np_) | set(ng_)) - SKIP
    res = {}
    for felt in sorted(alle):
        a, b = np_.get(felt), ng_.get(felt)
        ft = felttype(felt, a, b)
        r = {
            "gruppe": emne(felt),
            "felttype": ft,
            "pred_ra": ra_p.get(felt),
            "gold_ra": ra_g.get(felt),
            "pred": a,
            "gold": b,
            "f1": None,
            "kategori": None,
        }
        if a is None and b is None:
            r["status"] = "begge_mangler"
            r["enige"] = None
        elif a is None:
            r["status"] = "pred_mangler"
            r["enige"] = False
            r["kategori"] = "UDELADELSE"
        elif b is None:
            r["status"] = "gold_mangler"
            r["enige"] = False
            r["gold_mangler_ok"] = felt in GOLD_MISSING_ZERO_OK_FIELDS and _is_zeroish(a)
        elif ft == "fritekst":
            score = f1(a, b)
            r["f1"] = round(score, 3)
            r["enige"] = score >= 0.8
            r["status"] = "udfyldt"
            if not r["enige"]:
                r["kategori"] = "FRITEKST_DELVIS" if score >= 0.4 else "FRITEKST_DIVERGENS"
        elif ft == "numerisk":
            try:
                af, bf = float(str(a).replace(",", ".")), float(str(b).replace(",", "."))
                if af == 0 and bf == 0:
                    match = True
                elif af == 0 or bf == 0:
                    match = abs(af - bf) <= 0.05
                else:
                    match = abs(af - bf) / max(abs(af), abs(bf)) <= 0.05
                r["enige"] = match
                r["status"] = "udfyldt"
                if not match:
                    r["kategori"] = "NUMERISK_AFVIGELSE"
            except (TypeError, ValueError):
                ens = str(a).lower().strip() == str(b).lower().strip()
                r["enige"] = ens
                r["status"] = "udfyldt"
                if not ens:
                    r["kategori"] = "FAKTUEL_FEJL"
        else:
            ens = str(a).lower().strip() == str(b).lower().strip()
            r["enige"] = ens
            r["status"] = "udfyldt"
            if not ens:
                ap = str(ra_p.get(felt, "")).strip().lower()
                bp = str(ra_g.get(felt, "")).strip().lower()
                r["kategori"] = "FORMAT" if ap == bp else "FAKTUEL_FEJL"
        res[felt] = r
    return res


def aggreger(alle_par):
    felt_stats = defaultdict(lambda: {
        "gruppe": None,
        "felttype": None,
        "n_sammenlignet": 0,
        "n_enige": 0,
        "n_uenige": 0,
        "n_mangler": 0,
        "n_gold_mangler": 0,
        "n_gold_mangler_ok": 0,
        "n_begge_mangler": 0,
        "f1_sum": 0.0,
        "f1_count": 0,
        "kategorier": defaultdict(int),
    })
    kat_tael = defaultdict(int)
    for par in alle_par:
        for felt, info in par.items():
            s = felt_stats[felt]
            s["gruppe"] = info["gruppe"]
            s["felttype"] = info["felttype"]
            if info["status"] == "begge_mangler":
                s["n_begge_mangler"] += 1
                continue
            if info["status"] == "gold_mangler":
                s["n_gold_mangler"] += 1
                if info.get("gold_mangler_ok"):
                    s["n_gold_mangler_ok"] += 1
                s["n_sammenlignet"] += 1
                s["n_uenige"] += 1
                continue
            s["n_sammenlignet"] += 1
            if info["status"] == "pred_mangler":
                s["n_mangler"] += 1
                s["n_uenige"] += 1
                kat_tael["UDELADELSE"] += 1
                s["kategorier"]["UDELADELSE"] += 1
            elif info.get("enige"):
                s["n_enige"] += 1
            else:
                s["n_uenige"] += 1
                if info.get("f1") is not None:
                    s["f1_sum"] += info["f1"]
                    s["f1_count"] += 1
                if info.get("kategori"):
                    kat_tael[info["kategori"]] += 1
                    s["kategorier"][info["kategori"]] += 1
    for s in felt_stats.values():
        n = s["n_sammenlignet"]
        s["agreement"] = round(s["n_enige"] / n, 4) if n > 0 else None
        s["gns_f1"] = round(s["f1_sum"] / s["f1_count"], 3) if s["f1_count"] > 0 else None
        s["missing_rate"] = round(s["n_mangler"] / n, 4) if n > 0 else None
        gold_missing_total = s["n_gold_mangler"] + s["n_begge_mangler"]
        s["n_gold_missing_total"] = gold_missing_total
        s["udelad_enighed"] = (
            round(s["n_begge_mangler"] / gold_missing_total, 4)
            if gold_missing_total > 0 else None
        )
    gs = defaultdict(lambda: {"n_sammenlignet": 0, "n_enige": 0, "n_uenige": 0, "n_mangler": 0})
    for s in felt_stats.values():
        g = gs[s["gruppe"]]
        g["n_sammenlignet"] += s["n_sammenlignet"]
        g["n_enige"] += s["n_enige"]
        g["n_uenige"] += s["n_uenige"]
        g["n_mangler"] += s["n_mangler"]
    for g in gs.values():
        n = g["n_sammenlignet"]
        g["agreement"] = round(g["n_enige"] / n, 4) if n > 0 else None
    total_s = sum(s["n_sammenlignet"] for s in felt_stats.values())
    total_e = sum(s["n_enige"] for s in felt_stats.values())
    overall = round(total_e / total_s, 4) if total_s > 0 else None
    return dict(felt_stats), dict(gs), dict(kat_tael), overall


def evaluer(results_dir, ground_truth_dir, annotator=None, kun_runs=None):
    gold = Path(ground_truth_dir)
    gold_map = {}
    for gf in sorted(gold.glob("*.json")):
        stem = gf.stem
        if "-" in stem:
            basis = stem.rsplit("-", 1)[0]
            suffiks = stem.rsplit("-", 1)[1]
            if annotator is not None and suffiks != annotator:
                continue
            if basis not in gold_map:
                gold_map[basis] = gf
        else:
            gold_map[stem] = gf

    if not gold_map:
        print(f"FEJL: Ingen ground truth filer fundet (annotator='{annotator}')")
        return {}

    print(f"  Ground truth: {len(gold_map)} filer" + (f" (annotator: {annotator})" if annotator else " (alle annotatorer)"))

    runs = sorted([d for d in Path(results_dir).iterdir()
                   if d.is_dir() and (d / "run_meta.json").exists()
                   and (kun_runs is None or d.name in kun_runs)])
    data = {}
    for run in runs:
        meta = json.loads((run / "run_meta.json").read_text(encoding="utf-8"))
        preds = sorted([f for f in run.glob("*.json") if f.name not in ("config.json", "run_meta.json")])
        par = []
        par_med_navne = {}
        rapport_aar = {}
        for pf in preds:
            gf = gold_map.get(pf.stem)
            if gf is None:
                continue
            rp, np2 = indlaes(pf)
            rg, ng2 = indlaes(gf)
            par_res = sammenlign(rp, np2, rg, ng2)
            par.append(par_res)
            par_med_navne[pf.stem] = par_res
        if not par:
            print(f"  Springer over {run.name} (ingen matchede filer)")
            continue
        fs, gs, kt, ov = aggreger(par)
        total_strict = sum(s.get("n_sammenlignet", 0) for s in fs.values())
        total_enige = sum(s.get("n_enige", 0) for s in fs.values())
        total_gold_mangler = sum(s.get("n_gold_mangler", 0) for s in fs.values())
        total_gold_mangler_ok = sum(s.get("n_gold_mangler_ok", 0) for s in fs.values())
        denom_lenient = total_strict - total_gold_mangler
        ov_lenient = round(total_enige / denom_lenient, 4) if denom_lenient > 0 else None
        ov_zero_ok = round((total_enige + total_gold_mangler_ok) / total_strict, 4) if total_strict > 0 else None
        rapport_navne = {pf.stem for pf in preds if gold_map.get(pf.stem)}
        data[run.name] = {
            "meta": meta,
            "n": len(par),
            "overall": ov,
            "overall_lenient": ov_lenient,
            "overall_zero_ok": ov_zero_ok,
            "felt": fs,
            "gruppe": gs,
            "kategorier": kt,
            "rapport_navne": rapport_navne,
            "par": par,
            "par_med_navne": par_med_navne,
            "rapport_aar": rapport_aar,
        }
        if ov_lenient is not None:
            print(f"  {run.name:<55} {len(par):>3} filer   {ov:.1%}  (lenient {ov_lenient:.1%}, zeroOK {ov_zero_ok:.1%})")
        else:
            print(f"  {run.name:<55} {len(par):>3} filer   {ov:.1%}")

    if data:
        faelles = None
        for d in data.values():
            faelles = d["rapport_navne"] if faelles is None else faelles & d["rapport_navne"]
        if faelles:
            for run_navn, d in data.items():
                faelles_par = []
                preds = sorted([f for f in Path(results_dir, run_navn).glob("*.json") if f.name not in ("config.json", "run_meta.json")])
                for pf in preds:
                    if pf.stem not in faelles:
                        continue
                    gf = gold_map.get(pf.stem)
                    if gf is None:
                        continue
                    rp, np2 = indlaes(pf)
                    rg, ng2 = indlaes(gf)
                    faelles_par.append(sammenlign(rp, np2, rg, ng2))
                if faelles_par:
                    fs_f, _, _, ov_f = aggreger(faelles_par)
                    total_strict_f = sum(s.get("n_sammenlignet", 0) for s in fs_f.values())
                    total_enige_f = sum(s.get("n_enige", 0) for s in fs_f.values())
                    total_gold_mangler_f = sum(s.get("n_gold_mangler", 0) for s in fs_f.values())
                    denom_lenient_f = total_strict_f - total_gold_mangler_f
                    ov_f_lenient = round(total_enige_f / denom_lenient_f, 4) if denom_lenient_f > 0 else None
                    d["overall_faelles"] = ov_f
                    d["overall_faelles_lenient"] = ov_f_lenient
    return data


def print_rapport(data):
    print(f"\n{'='*72}\n  EKSPERIMENT SAMMENLIGNING\n{'='*72}")
    print(f"  {'Korsel':<50} {'N':>4}  {'Agreement':>10}  {'Lenient':>8}  {'ZeroOK':>7}  {'Agreement*':>11}")
    print(f"  {'-'*72}")

    faelles = None
    for d in data.values():
        navne = d.get("rapport_navne", set())
        faelles = navne if faelles is None else faelles & navne
    n_faelles = len(faelles) if faelles else 0

    for navn, d in sorted(data.items(), key=lambda x: -(x[1]["overall"] or 0)):
        ov_faelles = d.get("overall_faelles")
        faelles_str = f"{ov_faelles:>10.1%}" if ov_faelles is not None else "         -"
        ov_lenient = d.get("overall_lenient")
        lenient_str = f"{ov_lenient:>7.1%}" if ov_lenient is not None else "      -"
        ov_zero_ok = d.get("overall_zero_ok")
        zero_str = f"{ov_zero_ok:>6.1%}" if ov_zero_ok is not None else "     -"
        print(f"  {navn:<50} {d['n']:>4}  {d['overall']:>9.1%}  {lenient_str}  {zero_str}  {faelles_str}")

    print(f"\n  * Agreement paa faelles subset (rapporter alle modeller har koert, n={n_faelles})")
    print("  Agreement = STRICT (gold_mangler tæller som uenighed).")
    print("  Lenient = ekskludér gold_mangler fra nævneren.")
    print("  ZeroOK = STRICT + (gold_mangler,pred==0) kan tælles som OK for felter i GOLD_MISSING_ZERO_OK_FIELDS.")
    print(f"{'='*72}\n")

    print(f"  Svageste felter (gennemsnit paa tvaers af alle modeller):\n  {'-'*60}")
    min_n = 5
    felt_gns = {}
    felt_miss = {}
    felt_coverage = {}
    felt_udelad = {}
    felt_udelad_n = {}

    for felt in {f for d in data.values() for f in d["felt"]}:
        sum_w = 0
        sum_agr = 0.0
        sum_miss = 0.0
        n_models = 0
        sum_cov = 0.0
        sum_u_w = 0
        sum_u = 0.0
        for d in data.values():
            s = d["felt"].get(felt)
            if not s:
                continue
            agr = s.get("agreement")
            n = s.get("n_sammenlignet", 0)
            if agr is None or n < min_n:
                continue
            sum_w += n
            sum_agr += agr * n
            mr = s.get("missing_rate")
            if mr is not None:
                sum_miss += mr * n
            u_ok = s.get("udelad_enighed")
            u_n = s.get("n_gold_missing_total")
            if u_ok is not None and u_n:
                sum_u_w += u_n
                sum_u += u_ok * u_n
            n_models += 1
            if d.get("n"):
                sum_cov += min(1.0, n / max(1, d["n"]))
        if n_models >= max(1, len(data) // 2) and sum_w > 0:
            felt_gns[felt] = sum_agr / sum_w
            felt_miss[felt] = (sum_miss / sum_w) if sum_w else None
            felt_coverage[felt] = (sum_cov / n_models) if n_models else None
            if sum_u_w > 0:
                felt_udelad[felt] = sum_u / sum_u_w
                felt_udelad_n[felt] = sum_u_w

    worst = sorted(felt_gns.items(), key=lambda x: x[1])[:15]
    for felt, acc in worst:
        per_model = ""
        for navn, d in sorted(data.items()):
            run_name = d["meta"].get("run_name", navn)[:8]
            s = d["felt"].get(felt, {})
            agr = s.get("agreement")
            n = s.get("n_sammenlignet")
            mr = s.get("missing_rate")
            u_ok = s.get("udelad_enighed")
            u_n = s.get("n_gold_missing_total")
            if agr is None or not n:
                if u_ok is not None and u_n:
                    per_model += f"  {run_name}: -(udelad:{u_ok:.0%},n:{u_n})"
                else:
                    per_model += f"  {run_name}: -"
            else:
                miss_str = f", miss:{mr:.0%}" if mr is not None else ""
                u_str = f", udelad:{u_ok:.0%}(n:{u_n})" if (u_ok is not None and u_n) else ""
                per_model += f"  {run_name}: {agr:.0%} (n:{n}{miss_str}{u_str})"
        cov = felt_coverage.get(felt)
        miss = felt_miss.get(felt)
        cov_str = f" cov:{cov:.0%}" if cov is not None else ""
        miss_str = f" miss:{miss:.0%}" if miss is not None else ""
        print(f"  {felt:<45} gns:{acc:.0%}{cov_str}{miss_str}  |{per_model}")

    print(f"\n  Bedste felter (gennemsnit paa tvaers af alle modeller):\n  {'-'*60}")
    best = sorted(felt_gns.items(), key=lambda x: -x[1])[:10]
    for felt, acc in best:
        cov = felt_coverage.get(felt)
        miss = felt_miss.get(felt)
        cov_str = f"  cov:{cov:.0%}" if cov is not None else ""
        miss_str = f"  miss:{miss:.0%}" if miss is not None else ""
        print(f"  {felt:<45} {acc:.1%}{cov_str}{miss_str}")

    print(f"\n  Felter med mange udeladelser (pred_mangler blandt evaluerbare cases):\n  {'-'*60}")
    mangler_sorted = sorted([(f, r) for f, r in felt_miss.items() if r is not None], key=lambda x: -x[1])[:15]
    for felt, mr in mangler_sorted:
        acc = felt_gns.get(felt)
        cov = felt_coverage.get(felt)
        u_ok = felt_udelad.get(felt)
        u_n = felt_udelad_n.get(felt)
        acc_str = f"acc:{acc:.0%}" if acc is not None else "acc:-"
        cov_str = f" cov:{cov:.0%}" if cov is not None else ""
        u_str = f" udelad_enig:{u_ok:.0%}(n:{u_n})" if (u_ok is not None and u_n) else ""
        print(f"  {felt:<45} miss:{mr:.0%}  {acc_str}{cov_str}{u_str}")

    print(f"\n  Enighed i udeladelser (når gold mangler):\n  {'-'*60}")
    u_sorted = sorted([(f, r, felt_udelad_n.get(f, 0)) for f, r in felt_udelad.items()], key=lambda x: (-x[2], -(x[1] or 0)))[:15]
    if not u_sorted:
        print("  (Ingen gold-mangler cases fundet i dette datasæt)\n")
    else:
        for felt, r, n_u in u_sorted:
            print(f"  {felt:<45} udelad_enig:{r:.0%}  (n:{n_u})")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--plots", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--queue-logs", default=None, help="Sti til mappe med queue logs (default: samme som --results)")
    parser.add_argument("--show", action="store_true", help="Vis plots inline (bruges typisk fra notebook)")
    parser.add_argument("--runs", nargs="+", default=None)
    parser.add_argument("--annotator", default=None)
    args = parser.parse_args()

    print(f"\nEvaluerer runs i: {args.results}\nGround truth:     {args.ground_truth}")
    if args.annotator:
        print(f"Annotator:        {args.annotator}")
    print()
    data = evaluer(args.results, args.ground_truth, annotator=args.annotator, kun_runs=args.runs)
    if not data:
        print("Ingen runs.")
        return
    
    # Indlæs queue logs hvis de findes
    queue_logs_dir = args.queue_logs or args.results
    run_names = set(data.keys())
    queue_logs = laes_queue_logs(queue_logs_dir, run_names)
    if queue_logs:
        print(f"  Fandt queue logs for {len(queue_logs)} runs")
    
    print_rapport(data)
    if args.plots or args.show:
        if not HAS_MATPLOTLIB:
            print("matplotlib mangler - springer plots over.")
        else:
            if args.plots:
                Path(args.plots).mkdir(parents=True, exist_ok=True)
            saet_stil()
            ud = args.plots
            print(f"\nGenererer plots{f' -> {args.plots}' if args.plots else ''}")
            p_samlet(data, ud, show=args.show)
            p_gruppe(data, ud, show=args.show)
            p_fejl(data, ud, show=args.show)
            p_worst(data, ud, show=args.show)
            p_heatmap(data, ud, show=args.show)
            if queue_logs:
                p_runtime_agreement(data, queue_logs, ud, show=args.show)
    if args.output:
        # Beholder kun de kortfattede opsummeringer, fjerner par/par_med_navne
        compact = {}
        for run_navn, d in data.items():
            entry = {
                "meta": d["meta"],
                "n": d["n"],
                "overall": d["overall"],
                "overall_lenient": d.get("overall_lenient"),
                "overall_zero_ok": d.get("overall_zero_ok"),
                "overall_faelles": d.get("overall_faelles"),
                "overall_faelles_lenient": d.get("overall_faelles_lenient"),
                "felt": d["felt"],
                "gruppe": d["gruppe"],
                "kategorier": d["kategorier"],
                "rapport_navne": d.get("rapport_navne"),
            }
            # Tilføj queue log info hvis den findes
            if run_navn in queue_logs:
                ql = queue_logs[run_navn]
                entry["runtime_seconds"] = ql.get("duration_seconds")
                entry["runtime_human"] = ql.get("duration_human")
                entry["succeeded"] = ql.get("succeeded")
                entry["failed"] = ql.get("failed")
                entry["model"] = ql.get("model")
            compact[run_navn] = entry
        ser = _to_serializable(compact)
        Path(args.output).write_text(json.dumps(ser, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Gemt rapport i: {args.output}")


if __name__ == "__main__":
    main()
