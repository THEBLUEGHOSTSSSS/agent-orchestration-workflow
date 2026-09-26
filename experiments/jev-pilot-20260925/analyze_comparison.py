"""Offline paired-probe analysis; reads fixed labels only after inference."""
import hashlib
import json
from pathlib import Path

p = Path(__file__).resolve().parent
gold = json.loads((p / 'gold.json').read_text())['labels']
jev = json.loads((p / 'jev.json').read_text())
baseline = json.loads((p / 'resumed-baseline.json').read_text())
assisted = json.loads((p / 'resumed-assisted.json').read_text())
packet_hash = hashlib.sha256((p / 'packet.json').read_bytes()).hexdigest()
for row in (baseline, assisted):
    assert row['status'] == 'OK' and row['packet_sha256'] == packet_hash
    assert set(row['answers']) == set(gold)

def quality(labels):
    return {'correct': sum(labels[i] == g['expected'] for i, g in gold.items()),
            'total': len(gold),
            'unsupported_false_support': sum(g['expected'] != 'supported' and labels[i] == 'supported' for i, g in gold.items())}

cost_a = baseline['usage']['cost']
cost_b = assisted['usage']['cost'] + jev['cost']
time_a = baseline['duration_seconds']
time_b = assisted['duration_seconds'] + jev['duration_seconds']
result = {
    'source_kind': 'probe', 'paired_llm_comparison_completed': True,
    'pairs': 1, 'packet_sha256': packet_hash,
    'baseline': {**quality(baseline['answers']), 'api_cost_usd': cost_a, 'duration_seconds': time_a, 'usage': baseline['usage']},
    'assisted': {**quality(assisted['answers']), 'api_cost_usd': cost_b, 'summed_stage_duration_seconds': time_b, 'astra_usage': assisted['usage'], 'jev_usage': jev['usage']},
    'jev_only': quality({i: a['choice'] for i, a in jev['answers'].items()}),
    'cost_change_percent': (cost_b / cost_a - 1) * 100,
    'summed_stage_latency_change_percent': (time_b / time_a - 1) * 100,
    'astra_prompt_token_change': assisted['usage']['prompt_tokens'] - baseline['usage']['prompt_tokens'],
    'resumed_calls_cost_usd': cost_a + assisted['usage']['cost'],
    'all_successful_probe_calls_including_previous_jev_cost_usd': cost_a + cost_b,
    'latency_caveat': 'One call per arm. Assisted latency is sum of prior Jev stage and current Astra stage, not one uninterrupted observed end-to-end run.',
    'scope_caveat': 'Reviewer label task only, not code implementation productivity; 12 seeded counterclaims; no independent human labeler; excludes development/preparation/commander costs.'
}
(p / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ('cost_change_percent','summed_stage_latency_change_percent','resumed_calls_cost_usd','all_successful_probe_calls_including_previous_jev_cost_usd')}, indent=2))
