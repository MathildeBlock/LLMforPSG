import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from prompts import get_prompt, list_prompts


# ══════════════════════════════════════════════════════════════════════════════
#  DEFINER DINE EKSPERIMENTER HER
#  Tilføj eller fjern entries — scriptet kører dem i rækkefølge.
#  "prompt_key" refererer til en nøgle i prompts.py → SYSTEM_PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

EXPERIMENTS = [
    {
        "name":              "phi4_all",
        "model":             "microsoft/phi-4",
        "prompt_key":        "rules_fulloneshot_temp2-ny",
        "quant":             "4bit",
        "dtype":             "bfloat16",
        "gpu_max_memory_gb": 18,
        "max_new_tokens":    4096,
    },    
    # {
    #     "name":              "qwen14b_bestrules",
    #     "model":             "Qwen/Qwen2.5-14B-Instruct",
    #     "prompt_key":        "rules_best",           # → prompts.py
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
    # {
    #     "name":              "phi4_bestrules",
    #     "model":             "microsoft/phi-4",
    #     "prompt_key":        "rules_best",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
    # {
    #     "name":              "qwen14b_fulloneshot_temp1-ny",
    #     "model":             "Qwen/Qwen2.5-14B-Instruct",
    #     "prompt_key":        "rules_fulloneshot_temp1-ny",           # → prompts.py
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },      
    # {
    #     "name":              "phi4_fulloneshot_temp1-ny",
    #     "model":             "microsoft/phi-4",
    #     "prompt_key":        "rules_fulloneshot_temp1-ny",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # }, 
    # {
    #     "name":              "qwen14b_fulloneshot_temp2-ny",
    #     "model":             "Qwen/Qwen2.5-14B-Instruct",
    #     "prompt_key":        "rules_fulloneshot_temp2-ny",           # → prompts.py
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
    # {
    #     "name":              "phi4_fulloneshot_temp2-ny",
    #     "model":             "microsoft/phi-4",
    #     "prompt_key":        "rules_fulloneshot_temp2-ny",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # }, 
    # {
    #     "name":              "qwen14b_fulloneshot_temp3-ny",
    #     "model":             "Qwen/Qwen2.5-14B-Instruct",
    #     "prompt_key":        "rules_fulloneshot_temp3-ny",           # → prompts.py
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
    # {
    #     "name":              "phi4_fulloneshot_temp3-ny",
    #     "model":             "microsoft/phi-4",
    #     "prompt_key":        "rules_fulloneshot_temp3-ny",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },   
    # {
    #     "name":              "qwen14b_noshot-ny",
    #     "model":             "Qwen/Qwen2.5-14B-Instruct",
    #     "prompt_key":        "noshot",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
    # {
    #     "name":              "phi4_noshot-ny",
    #     "model":             "microsoft/phi-4",
    #     "prompt_key":        "noshot",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
    # {
    #     "name":              "qwen14b_rules_oneshot",
    #     "model":             "Qwen/Qwen2.5-14B-Instruct",
    #     "prompt_key":        "rules_oneshot",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
    # {
    #     "name":              "phi4_rules_oneshot",
    #     "model":             "microsoft/phi-4",
    #     "prompt_key":        "rules_oneshot",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
    # Tilføj flere her:
    # {
    #     "name":              "mistral_rules_oneshot",
    #     "model":             "mistralai/Mistral-Nemo-Instruct-2407",
    #     "prompt_key":        "rules_oneshot",
    #     "quant":             "4bit",
    #     "dtype":             "bfloat16",
    #     "gpu_max_memory_gb": 18,
    #     "max_new_tokens":    4096,
    # },
]

# ══════════════════════════════════════════════════════════════════════════════

EXTRACTOR_SCRIPT = "psg_extractPL.py"
INPUT_DIR        = Path("/dprhlz/home/matblo/data/txt-ny")
RESULTS_DIR      = Path("results")
HF_TOKEN         = ""


def format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}t {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def already_done(run_name: str) -> bool:
    return len(list(RESULTS_DIR.glob(f"{run_name}_*"))) > 0


def get_report_files(subset: int = None) -> list[Path]:
    files = sorted(INPUT_DIR.glob("*.txt"))
    if subset:
        random.seed(42)
        files = random.sample(files, min(subset, len(files)))
    return files


def run_experiment(exp: dict, report_files: list[Path], subset: int = None) -> dict:
    run_name   = exp["name"]
    prompt_key = exp["prompt_key"]
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    output_dir = RESULTS_DIR / f"{run_name}"
    # output_dir = RESULTS_DIR / f"{run_name}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Hent prompt og gem kopi i output-mappe (reproducerbarhed)
    prompt_text = get_prompt(prompt_key)
    (output_dir / "system_prompt.txt").write_text(prompt_text, encoding="utf-8")

    # Skriv til scripts mappe så psg_extract_pipeline.py læser den rigtige
    script_dir = Path(EXTRACTOR_SCRIPT).resolve().parent
    (script_dir / "system_prompt.txt").write_text(prompt_text, encoding="utf-8")

    # Gem config + metadata
    with open(output_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(exp, f, indent=2, ensure_ascii=False)
    with open(output_dir / "run_meta.json", "w", encoding="utf-8") as f:
        json.dump({
            "run_name":   run_name,
            "timestamp":  timestamp,
            "n_reports":  len(report_files),
            "model":      exp["model"],
            "prompt_key": prompt_key,
        }, f, indent=2, ensure_ascii=False)

    # Hvis subset: kopier de udvalgte filer til en midlertidig mappe
    # så --mappe kun ser de relevante filer
    if subset and len(report_files) < len(list(INPUT_DIR.glob("*.txt"))):
        tmp_dir = output_dir / "_tmp_input"
        tmp_dir.mkdir(exist_ok=True)
        for f in report_files:
            shutil.copy(f, tmp_dir / f.name)
        input_mappe = tmp_dir
    else:
        input_mappe = INPUT_DIR

    # Kald extractoren én gang med --mappe — modellen loades kun én gang
    cmd = [
        sys.executable, EXTRACTOR_SCRIPT,
        "--mappe",          str(input_mappe),
        "--output-mappe",   str(output_dir),
        "--model",          exp["model"],
        "--token",          HF_TOKEN,
        "--device",         "cuda",
        "--device-map",     "cuda",
        "--dtype",          exp.get("dtype", "bfloat16"),
        "--quant",          exp.get("quant", "4bit"),
        "--max-new-tokens", str(exp.get("max_new_tokens", 4096)),
        "--prefetch",       "2",
    ]
    if exp.get("gpu_max_memory_gb"):
        cmd += ["--gpu-max-memory-gb", str(exp["gpu_max_memory_gb"])]

    start = time.time()
    try:
        result = subprocess.run(cmd, text=True, timeout=86400)  # 24 timer max
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        print("  ✗ Timeout!")
        returncode = -1
    except Exception as e:
        print(f"  ✗ Fejl: {e}")
        returncode = -1

    duration = time.time() - start

    # Ryd op midlertidig mappe
    if subset and (output_dir / "_tmp_input").exists():
        shutil.rmtree(output_dir / "_tmp_input")

    # Tæl output filer
    json_filer = [f for f in output_dir.glob("*.json")
                  if f.name not in ("config.json", "run_meta.json")]
    succeeded = len(json_filer)
    failed    = max(0, len(report_files) - succeeded)

    return {
        "run_name":         run_name,
        "output_dir":       str(output_dir),
        "model":            exp["model"],
        "prompt_key":       prompt_key,
        "n_reports":        len(report_files),
        "succeeded":        succeeded,
        "failed":           failed,
        "skipped":          0,
        "returncode":       returncode,
        "duration_seconds": round(duration, 1),
        "duration_human":   format_duration(duration),
    }


def print_summary(results: list[dict]):
    print(f"\n{'═'*65}")
    print(f"  QUEUE FÆRDIG — SAMMENFATNING")
    print(f"{'═'*65}")
    total_time = sum(r["duration_seconds"] for r in results)
    for r in results:
        status = "✓" if r["failed"] == 0 else f"⚠ {r['failed']} fejl"
        print(f"  {r['run_name']:<40} {r['duration_human']:>8}  {status}")
    print(f"{'─'*65}")
    print(f"  Total tid: {format_duration(total_time)}")
    print(f"{'═'*65}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", type=int, default=None,
                        help="Kør kun N rapporter per eksperiment (reproducerbart, seed=42)")
    parser.add_argument("--skip-done", action="store_true",
                        help="Spring eksperimenter over der allerede har en output-mappe")
    parser.add_argument("--only", nargs="+", default=None,
                        help="Kør kun eksperimenter med disse navne")
    args = parser.parse_args()

    if not HF_TOKEN:
        print("FEJL: Sæt HF_TOKEN i miljøet eller indsæt direkte i scriptet.")
        sys.exit(1)

    RESULTS_DIR.mkdir(exist_ok=True)
    queue_timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    experiments = EXPERIMENTS
    if args.only:
        experiments = [e for e in experiments if e["name"] in args.only]

    report_files = get_report_files(subset=args.subset)

    print(f"\n{'═'*65}")
    print(f"  PSG EXTRACTION QUEUE")
    print(f"  Start:                {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Eksperimenter:        {len(experiments)}")
    print(f"  Rapporter per kørsel: {len(report_files)}"
          + (" (subset)" if args.subset else ""))
    print(f"  Estimeret total tid:  ~{len(experiments) * len(report_files) * 2 // 60} timer")
    print(f"{'═'*65}\n")

    all_results = []
    log_path = RESULTS_DIR / f"queue_log_{queue_timestamp}.json"

    for i, exp in enumerate(experiments, 1):
        print(f"[{i}/{len(experiments)}] {exp['name']}")
        print(f"  Model:  {exp['model']}")
        print(f"  Prompt: {exp['prompt_key']}")

        if args.skip_done and already_done(exp["name"]):
            print(f"  → Springer over (output findes allerede)\n")
            continue

        result = run_experiment(exp, report_files, subset=args.subset)
        all_results.append(result)

        # Gem log efter hvert eksperiment — crashsikker
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        print(f"  → Færdig: {result['succeeded']}/{result['n_reports']} ok "
              f"på {result['duration_human']}\n")

    print_summary(all_results)
    print(f"Log gemt: {log_path}")
    print(f"\nKør nu: python compare_experiments.py --results results/ --ground-truth data/ground_truth/")


if __name__ == "__main__":
    main()