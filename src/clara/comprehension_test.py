"""Corpus versionnés : compréhension seule, aucun appel Windows ou cloud."""
import argparse
import hashlib
import json
import time
from collections import Counter
from importlib.resources import files
from pathlib import Path

from .config import data_dir, load
from .contracts import ClaraError
from .planner import Planner
from .test_evidence import write_artifacts


def evaluate(config, split="evaluation", planner=None):
    source = files("clara").joinpath(f"resources/comprehension_{split}_fr.json").read_bytes()
    cases = json.loads(source)["cases"]
    # Tests reproductibles sans Jev, sans Ollama, mais avec le vrai moteur local.
    planner = planner or Planner(dict(config, jev_enabled=False), False)
    planner.config = dict(planner.config, jev_enabled=False)
    report = {"version": 1, "status": "RUNNING", "backend": "understanding_only", "split": split,
              "corpus_role": "regression_after_first_evaluation" if split in {'evaluation', 'confirmation'} else split,
              "corpus_sha256": hashlib.sha256(source).hexdigest(), "steps": [], "understanding": [],
              "limits": "Aucune exécution Windows, voix, Jev ou inférence Ollama dans ce corpus."}
    routes = Counter()
    for case in cases:
        entry = dict(case)
        started = time.monotonic()
        try:
            steps, origin = planner.interpret(case["text"], {}, "test-results")
            entry.update(actual_steps=steps, origin=origin,
                         status="PASSED" if steps == case["expected_steps"] else "FAILED")
            routes[origin] += 1
        except ClaraError as exc:
            entry.update(error_code=exc.code, message=str(exc),
                         status="PASSED" if case["expected_steps"] is None else "FAILED")
        entry["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        entry["trace"] = list(planner.last_trace)
        report["understanding"].append(entry)
    positives = [c for c in report["understanding"] if c["expected_steps"] is not None]
    negatives = [c for c in report["understanding"] if c["expected_steps"] is None]
    novel = [c for c in positives if c.get('category') == 'positive_novel' or (
        c.get('category') != 'positive_exact' and (not c.get('trace') or c['trace'][0].get('status') == 'NO_MATCH'))]
    durations = sorted(c["duration_ms"] for c in report["understanding"])
    report["metrics"] = {"cases": len(cases), "positive_total": len(positives),
        "positive_correct": sum(c["status"] == "PASSED" for c in positives),
        "wrong_positive_actions": sum(c['status'] != 'PASSED' and 'actual_steps' in c for c in positives),
        "novel_positive_total": len(novel), "novel_positive_correct": sum(c['status'] == 'PASSED' for c in novel),
        "false_acceptances": sum(c["status"] != "PASSED" for c in negatives), "routes": dict(routes),
        "cold_first_ms": durations and report["understanding"][0]["duration_ms"],
        "p95_ms": durations[int((len(durations) - 1) * .95)],
        "semantic_model": planner.semantic.encoder.identity if getattr(planner.semantic, 'encoder', None) else 'UNAVAILABLE'}
    report['all_cases_passed'] = all(c['status'] == 'PASSED' for c in report['understanding'])
    exact = [c for c in positives if c.get('category') == 'positive_exact']
    metrics = report['metrics']
    report['acceptance'] = {
        'zero_wrong_actions': metrics['wrong_positive_actions'] == 0 and metrics['false_acceptances'] == 0,
        'exact_cases_correct': all(c['status'] == 'PASSED' for c in exact),
        'novel_local_recall_at_least_90_percent': not novel or metrics['novel_positive_correct'] / len(novel) >= .9,
        'semantic_encoder_exercised': metrics['semantic_model'] != 'UNAVAILABLE'}
    report["status"] = "PASSED" if all(report['acceptance'].values()) else "FAILED"
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=data_dir() / "config.json")
    parser.add_argument("--split", choices=["calibration", "evaluation", "confirmation"], default="confirmation")
    parser.add_argument("--output", type=Path, default=data_dir() / "comprehension.json")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--margin", type=float)
    args = parser.parse_args()
    config = load(args.config)
    if args.threshold is not None:
        config["semantic_threshold"] = args.threshold
    if args.margin is not None:
        config["semantic_margin"] = args.margin
    report = evaluate(config, args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_artifacts(args.output, report)
    print(json.dumps(report["metrics"], ensure_ascii=False))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
