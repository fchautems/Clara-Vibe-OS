"""Réglage sur calibration uniquement ; ne lit jamais le corpus d'évaluation."""
import argparse
import json
from pathlib import Path

from clara.comprehension_test import evaluate
from clara.config import data_dir, load
from clara.planner import Planner
from clara.semantic import SemanticMatcher


def calibrate(config):
    matcher = SemanticMatcher(config)
    # Refuse une calibration qui n'aurait pas réellement chargé l'encodeur.
    matcher.match('retourne vers le niveau superieur')
    measurements = []
    for threshold in (.65, .70, .74, .78, .82, .86, .90):
        for margin in (.04, .08, .12):
            candidate = dict(config, semantic_threshold=threshold, semantic_margin=margin, jev_enabled=False)
            matcher.config = candidate
            report = evaluate(candidate, 'calibration', Planner(candidate, False, matcher))
            measurements.append({'threshold': threshold, 'margin': margin, **report['metrics']})
    safe = [m for m in measurements if m['false_acceptances'] == 0 and m['wrong_positive_actions'] == 0]
    recommendation = max(safe, key=lambda m: (m['positive_correct'], m['threshold'], m['margin'])) if safe else None
    return {'split': 'calibration', 'measurements': measurements, 'recommendation': recommendation,
            'model': matcher.encoder.identity, 'corpus_sha256': report['corpus_sha256'],
            'limits': 'Réglage du corpus local ; aucune validation Windows ou vocale. Aucun réglage modifié automatiquement.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=data_dir() / 'config.json')
    parser.add_argument('--output', type=Path, default=data_dir() / 'calibration-semantique.json')
    args = parser.parse_args()
    result = calibrate(load(args.config))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['recommendation'], ensure_ascii=False))


if __name__ == '__main__':
    main()
