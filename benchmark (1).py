"""Benchmark the AI reviewer against manual reviews.

Usage:  python benchmark.py [model]   (needs OPENAI_API_KEY set)
Inputs:  test_snippets.json and manual_reviews.json
Outputs: results.csv and summary.md
"""
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reviewer import DEFAULT_MODEL, review_code  # noqa: E402

HERE = Path(__file__).resolve().parent
TOLERANCE = 2  # lines of slack when matching an AI issue to a manual issue


def overlaps(a, b, tol=TOLERANCE):
    return a["line_start"] - tol <= b["line_end"] and b["line_start"] - tol <= a["line_end"]


def match_issues(ai_issues, manual_issues):
    """Return (true_positive_ai, found_manual_indexes)."""
    found = set()
    tp = 0
    for ai in ai_issues:
        hit = False
        for idx, man in enumerate(manual_issues):
            if overlaps(ai, man):
                found.add(idx)
                hit = True
        tp += hit
    return tp, found


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("Set OPENAI_API_KEY first.")
    manual = json.loads((HERE / "manual_reviews.json").read_text())
    snippets = json.loads((HERE / "test_snippets.json").read_text())
    rows, tot = [], dict(ai=0, tp=0, man=0, found=0, secs=0.0, man_secs=0.0, man_n=0, clean_fp=0)

    for name, truth in manual.items():
        if name.startswith("_"):
            continue
        code = snippets[name]
        lang = "Python" if name.endswith(".py") else "JavaScript"
        review = review_code(code, lang, api_key, model)
        ai_issues = review["issues"]
        tp, found = match_issues(ai_issues, truth["issues"])
        rows.append({
            "snippet": name, "manual_issues": len(truth["issues"]), "ai_issues": len(ai_issues),
            "ai_true_positives": tp, "manual_issues_found_by_ai": len(found),
            "ai_seconds": review["_meta"]["seconds"], "manual_seconds": truth.get("manual_time_seconds"),
        })
        tot["ai"] += len(ai_issues); tot["tp"] += tp
        tot["man"] += len(truth["issues"]); tot["found"] += len(found)
        tot["secs"] += review["_meta"]["seconds"]
        if truth.get("manual_time_seconds"):
            tot["man_secs"] += truth["manual_time_seconds"]; tot["man_n"] += 1
        if not truth["issues"]:
            tot["clean_fp"] += len(ai_issues)
        print(f"{name}: AI {len(ai_issues)} issues, caught {len(found)}/{len(truth['issues'])} manual")

    with open(HERE / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

    recall = tot["found"] / tot["man"] if tot["man"] else 0
    precision = tot["tp"] / tot["ai"] if tot["ai"] else 0
    n = len(rows)
    man_avg = f"{tot['man_secs'] / tot['man_n']:.0f}s" if tot["man_n"] else "not recorded"
    summary = f"""# Benchmark: AI review vs manual review

Model: {model} | Snippets: {n}

| Metric | Result |
|---|---|
| Recall (manual issues the AI also found) | {recall:.0%} ({tot['found']}/{tot['man']}) |
| Precision (AI issues matching a manual issue) | {precision:.0%} ({tot['tp']}/{tot['ai']}) |
| False alarms on the clean control snippet | {tot['clean_fp']} |
| Avg AI review time | {tot['secs'] / n:.1f}s |
| Avg manual review time | {man_avg} |

Matching rule: an AI issue counts as a hit if its line range is within {TOLERANCE} lines of a manual issue.
Precision is a lower bound: AI issues not in the manual list may still be valid, so check them by hand.
"""
    (HERE / "summary.md").write_text(summary)
    print("\n" + summary)


if __name__ == "__main__":
    main()
