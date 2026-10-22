"""Corpus hors correspondances exactes, sans Ollama ni Windows."""
import json
from pathlib import Path
from clara.catalogue import similar_command
from clara.config import defaults


def evaluate(threshold, margin):
    cases = json.loads((Path(__file__).resolve().parents[1] / 'tests/data/similarity_fr.json').read_text())
    accepted = wrong = missed = 0
    for case in cases:
        command, ambiguous = similar_command(case['text'], dict(defaults(), catalogue_path=None,
                                             similarity_threshold=threshold, similarity_margin=margin))
        if command and command != case['command']:
            wrong += 1
        elif case['command'] and command == case['command']:
            accepted += 1
        elif case['command']:
            missed += 1
    return {'threshold': threshold, 'margin': margin, 'positive_matches': accepted,
            'false_acceptances': wrong, 'missed_positives': missed, 'cases': len(cases)}


if __name__ == '__main__':
    for threshold in [.80, .84, .86, .90, .94, .98]:
        print(json.dumps(evaluate(threshold, .06), ensure_ascii=False))
