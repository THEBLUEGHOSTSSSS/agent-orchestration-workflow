"""Deterministic, explainable, side-effect-free worker selection."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import math

from .models import validate_config, validate_diagnosis, validate_signature

METRICS = ('sample_count', 'confidence', 'first_pass_acceptance_rate',
           'second_pass_acceptance_rate', 'overall_acceptance_rate',
           'model_related_failure_rate', 'retry_rate', 'switch_away_rate',
           'strong_model_takeover_rate', 'average_execution_cost', 'average_latency',
           'average_repair_burden', 'accepted_tasks_per_cost')
EXCLUSION_FLAGS = ('cancelled', 'invalid', 'user_change', 'corrupted_repo',
                   'user_changed', 'corrupted_repository')
SERIOUS_FAILURES = ('REASONING_FAILURE', 'ARCHITECTURE_FAILURE', 'LOOP_BEHAVIOR',
                    'CONTEXT_HANDLING_FAILURE', 'ALGORITHM_FAILURE', 'INVARIANT_FAILURE')


def _similarity(target, past, policy):
    verification = {'weak': 0, 'moderate': 1, 'strong': 2}
    if verification[past['verification_strength']] < verification[target['verification_strength']]:
        return 0.0
    if target['risk_level'] == 'high' and past['risk_level'] == 'low':
        return 0.0
    if target['environment'] == 'production' and past['environment'] != 'production':
        return 0.0
    if target['domain'].casefold() != past['domain'].casefold():
        return 0.0
    if {target['reasoning_intensity'], past['reasoning_intensity']} == {'low', 'high'}:
        return 0.0
    t, p = target['task_type'].casefold(), past['task_type'].casefold()
    related = any(t in group and p in group for group in policy['task_type_groups'])
    if t != p and not related:
        return 0.0
    weights = policy['similarity_weights']
    value = weights['domain'] + weights['task_type' if t == p else 'related_task_type']
    for field, weight in weights.items():
        if field not in ('domain', 'task_type', 'related_task_type') and target[field].casefold() == past[field].casefold():
            value += weight
    return min(1.0, value)


def _prior(worker, signature):
    prior = worker['prior']
    score = prior['base']
    for field, preference in (('domain', 'domain_preferences'),
                              ('task_type', 'task_type_preferences'),
                              ('reasoning_intensity', 'reasoning_intensity_preferences')):
        score += prior[preference].get(signature[field], 0)
    return max(0, min(1, score))


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _contains_pollution(value):
    if isinstance(value, dict):
        if any(value.get(flag) is True for flag in EXCLUSION_FLAGS):
            return True
        return any(_contains_pollution(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_pollution(item) for item in value)
    return False


def _excluded(record, worker, signature, now, policy):
    if not isinstance(record, dict):
        return 'malformed'
    if record.get('valid') is not True or record.get('source_kind') != 'real':
        return 'unverified_or_nonreal'
    if _contains_pollution(record):
        return 'cancelled_or_polluted'
    snapshot = record.get('worker')
    if not isinstance(snapshot, dict) or any(snapshot.get(key) != worker[key] for key in ('worker_id', 'provider', 'model', 'reasoning_effort')):
        return 'worker_snapshot_mismatch'
    if not isinstance(snapshot.get('version'), str) or not snapshot['version']:
        return 'worker_snapshot_mismatch'
    try:
        past = validate_signature(record.get('task_signature'))
    except ValueError:
        return 'invalid_signature'
    if _similarity(signature, past, policy) < policy['similarity_threshold']:
        return 'dissimilar'
    date = _timestamp(record.get('timestamp'))
    if date is None:
        return 'invalid_timestamp'
    age = (now - date).total_seconds() / 86400
    if age < 0 or age > policy['recency_window_days']:
        return 'future_or_expired'
    expiry = record.get('expires_at')
    if expiry is not None and (_timestamp(expiry) is None or _timestamp(expiry) < now):
        return 'future_or_expired'
    if not isinstance(record.get('experience_id'), str) or not record['experience_id'].strip() or not isinstance(record.get('logical_task_id'), str) or not record['logical_task_id'].strip():
        return 'invalid_identity'
    attempt = record.get('attempt_number')
    if type(attempt) is not int or attempt not in (1, 2):
        return 'invalid_attempt'
    verification, outcome = record.get('verification'), record.get('outcome')
    if not isinstance(verification, dict) or not isinstance(outcome, dict):
        return 'unreviewed'
    reviewed = verification.get('reviewer_result')
    if reviewed not in ('accepted', 'rejected') or not isinstance(verification.get('reviewer'), str) or not verification['reviewer'].strip():
        return 'unreviewed'
    if type(outcome.get('accepted')) is not bool or outcome['accepted'] != (reviewed == 'accepted'):
        return 'inconsistent_review'
    try:
        diagnosis = validate_diagnosis(record.get('diagnosis'), outcome['accepted'])
    except ValueError:
        return 'invalid_diagnosis'
    if not outcome['accepted'] and diagnosis['attribution'] != 'MODEL_RELATED':
        return 'non_model_failure'
    return None


def _metric_rate(records, numerator):
    return sum(1 for r in records if numerator(r)) / len(records) if records else None


def _average(values):
    return sum(values) / len(values) if values else None


def _quality(record, policy):
    if not record['outcome']['accepted']:
        return 0.0
    quality = record['outcome'].get('final_quality')
    quality = quality if type(quality) in (int, float) and math.isfinite(quality) and 0 <= quality <= 1 else 1.0
    repair = record.get('repair') or {}
    severity = policy['failure_severity'].get(repair.get('severity', 'none'), 0)
    return quality * (1 - policy['repair_quality_penalty'] * severity)


def _collect(worker, signature, experiences, now, config):
    policy = config['policy']
    included, excluded = [], Counter()
    for record in experiences:
        reason = _excluded(record, worker, signature, now, policy)
        if reason:
            excluded[reason] += 1
            continue
        age = (now - _timestamp(record['timestamp'])).total_seconds() / 86400
        similarity = _similarity(signature, validate_signature(record['task_signature']), policy)
        recency = 2 ** (-age / policy['recency_half_life_days'])
        version = 1 if record['worker']['version'] == worker['version'] else policy['version_discount']
        weight = similarity * recency * version
        if weight <= 0:
            excluded['zero_effective_weight'] += 1
            continue
        included.append((record, weight))
    records = [r for r, _ in included]
    groups = defaultdict(list)
    for record, weight in included:
        groups[record['logical_task_id']].append((record, weight))
    # An attempt can affect outcomes, but repeated attempts from one logical task
    # contribute at most one unit of evidence to score and confidence.
    numerator, severity_numerator, denominator = 0.0, 0.0, 0.0
    for group in groups.values():
        group_weight = max(w for _, w in group)
        attempt_weight = sum(w for _, w in group)
        quality = sum(w * _quality(r, policy) for r, w in group) / attempt_weight
        severity = sum(w * policy['failure_severity'][r['diagnosis']['severity']]
                       * policy['failure_type_weights'].get(r['diagnosis']['failure_type'], policy['default_failure_type_weight'])
                       for r, w in group if not r['outcome']['accepted']) / attempt_weight
        numerator += group_weight * quality
        severity_numerator += group_weight * severity
        denominator += group_weight
    accepted = lambda r: r['outcome']['accepted']
    first = [r for r in records if r['attempt_number'] == 1]
    second = [r for r in records if r['attempt_number'] == 2]
    costs = [r['execution']['estimated_cost'] for r in records
             if isinstance(r.get('execution'), dict)
             and r['execution'].get('currency') == config['currency']
             and _nonnegative(r['execution'].get('estimated_cost'))]
    latencies = [r['execution']['duration_seconds'] for r in records
                 if isinstance(r.get('execution'), dict) and _nonnegative(r['execution'].get('duration_seconds'))]
    burdens = [r['repair']['burden'] for r in records if isinstance(r.get('repair'), dict)
               and _nonnegative(r['repair'].get('burden'))]
    def weighted_metric(part, field, currency=False):
        pairs = [(r[part][field], weight) for r, weight in included
                 if isinstance(r.get(part), dict) and _nonnegative(r[part].get(field))
                 and (not currency or r[part].get('currency') == config['currency'])]
        return sum(value * weight for value, weight in pairs) / sum(weight for _, weight in pairs) if pairs else None
    cost = weighted_metric('execution', 'estimated_cost', True)
    accepted_logical_tasks = {r['logical_task_id'] for r in records if r['outcome']['accepted']}
    values = {
        'sample_count': len(groups), 'confidence': ('HIGH' if denominator >= policy['confidence_high_samples']
            else 'MEDIUM' if denominator >= policy['confidence_medium_samples'] else 'LOW'),
        'first_pass_acceptance_rate': _metric_rate(first, accepted),
        'second_pass_acceptance_rate': _metric_rate(second, accepted),
        'overall_acceptance_rate': _metric_rate(records, accepted),
        'model_related_failure_rate': _metric_rate(records, lambda r: not accepted(r)),
        'retry_rate': _metric_rate(records, lambda r: bool(isinstance(r.get('retry'), dict) and r['retry'].get('required') is True)),
        'switch_away_rate': _metric_rate(records, lambda r: bool(isinstance(r.get('retry'), dict) and r['retry'].get('action') in ('switch', 'switch_away', 'SWITCH', 'DIFFERENT_WORKER'))),
        'strong_model_takeover_rate': _metric_rate(records, lambda r: bool(isinstance(r.get('repair'), dict) and r['repair'].get('takeover') is True)),
        'average_execution_cost': cost, 'average_latency': weighted_metric('execution', 'duration_seconds'),
        'average_repair_burden': weighted_metric('repair', 'burden'),
        'accepted_tasks_per_cost': (len(accepted_logical_tasks) / sum(costs)
                                    if costs and len(costs) == len(records) and sum(costs) > 0 else None),
    }
    prior = _prior(worker, signature)
    empirical = numerator / denominator if denominator else None
    shrink = denominator / (denominator + policy['shrinkage_samples'])
    posterior = prior if empirical is None else prior * (1 - shrink) + empirical * shrink
    penalty = policy['failure_penalty'] * severity_numerator / denominator * shrink if denominator else 0
    return {'worker_id': worker['worker_id'], **values, 'prior_score': prior,
            'empirical_score': empirical, 'effective_sample_weight': denominator,
            'shrinkage_weight': shrink, 'failure_severity_penalty': penalty,
            'score': posterior - penalty, 'evidence_ids': [r['experience_id'] for r in records],
            'excluded_counts': dict(excluded), 'cost_penalty': None,
            'latency_penalty': None, 'repair_penalty': None}


def _normalized_penalties(suitability, config):
    policy = config['policy']
    for field, key, weight in (('routing_cost_estimate', 'cost_penalty', 'cost_penalty'),
                               ('routing_latency_estimate', 'latency_penalty', 'latency_penalty'),
                               ('average_repair_burden', 'repair_penalty', 'repair_penalty')):
        comparable = [row[field] for row in suitability.values() if row[field] is not None]
        if len(comparable) < 2:
            continue
        lo, hi = min(comparable), max(comparable)
        if lo == hi:
            continue
        for row in suitability.values():
            if row[field] is not None:
                penalty = policy[weight] * (row[field] - lo) / (hi - lo)
                row[key] = penalty
                row['score'] -= penalty


def route(signature, experiences, config, *, now=None, previous_worker=None,
          diagnosis=None, manual_worker=None):
    signature = validate_signature(signature)
    config = validate_config(config)
    if not isinstance(experiences, list):
        raise ValueError('experiences must be a list')
    now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be timezone-aware')
    previous_id = previous_worker.get('worker_id') if isinstance(previous_worker, dict) else previous_worker
    if previous_id is not None and (not isinstance(previous_id, str) or not previous_id):
        raise ValueError('invalid previous_worker')
    if diagnosis is not None:
        if previous_id is None:
            raise ValueError('retry diagnosis requires previous_worker')
        diagnosis = validate_diagnosis(diagnosis, False)
    if manual_worker is not None and (not isinstance(manual_worker, str) or not manual_worker):
        raise ValueError('invalid manual_worker')
    eligible = [w for w in config['workers'] if w['enabled'] and w['availability'] == 'available'
                and set(signature['required_capabilities']).issubset(w['capabilities'])]
    if not eligible:
        raise ValueError('no eligible workers')
    suitability = {w['worker_id']: _collect(w, signature, experiences, now, config) for w in eligible}
    for worker in eligible:
        row = suitability[worker['worker_id']]
        cost_prior = worker['cost_profile']
        row['cost_source'] = 'observed' if row['average_execution_cost'] is not None else 'unknown'
        if row['average_execution_cost'] is None and cost_prior.get('currency') == config['currency'] and cost_prior.get('estimated_cost') is not None:
            row['routing_cost_estimate'] = cost_prior['estimated_cost']
            row['cost_source'] = 'configured_prior'
        else:
            row['routing_cost_estimate'] = row['average_execution_cost']
        row['routing_latency_estimate'] = row['average_latency'] if row['average_latency'] is not None else worker['latency_profile']['estimated_seconds']
    _normalized_penalties(suitability, config)
    ranked = sorted(eligible, key=lambda w: (-suitability[w['worker_id']]['score'],
                                              w['worker_id']))
    selected, mode = ranked[0], 'HEURISTIC'
    reasons = []
    evidence = any(suitability[w['worker_id']]['sample_count'] for w in eligible)
    if evidence:
        mode = 'EXPLOIT'
    if manual_worker is not None:
        matches = [w for w in eligible if w['worker_id'] == manual_worker]
        if not matches:
            raise ValueError('manual worker not eligible')
        selected, mode = matches[0], 'MANUAL_OVERRIDE'
        reasons.append('Manual override requested for eligible worker.')
    elif previous_id is not None:
        previous = next((w for w in eligible if w['worker_id'] == previous_id), None)
        if diagnosis is None:
            raise ValueError('previous_worker requires a diagnosis')
        if diagnosis['attribution'] == 'MODEL_RELATED' and diagnosis['failure_type'] in SERIOUS_FAILURES and len(ranked) > 1:
            selected = next(w for w in ranked if w['worker_id'] != previous_id)
            mode = 'RETRY_SWITCH'
            reasons.append('Serious model-related failure: use an eligible alternative.')
        elif previous is not None:
            selected, mode = previous, 'RETRY_SAME'
            if diagnosis['attribution'] == 'MODEL_RELATED':
                reasons.append('Low/local implementation failure: retry with the same eligible worker.' if diagnosis['severity'] == 'low' and diagnosis['failure_type'] in ('LOCAL_IMPLEMENTATION_ERROR', 'INCOMPLETE_EXECUTION') else 'No serious switch-triggering model failure; retain eligible worker.')
            else:
                reasons.append(f'{diagnosis["attribution"]} is not evidence of poor worker suitability; fix prerequisite and retain worker.')
        else:
            mode = 'RETRY_SWITCH'
            reasons.append('Previous worker is ineligible; select an eligible candidate.')
    elif (config['policy']['exploration_enabled'] and signature['risk_level'] == 'low' and signature['verification_strength'] == 'strong'
          and signature['environment'] != 'production' and evidence and len(ranked) > 1):
        leader_score = suitability[ranked[0]['worker_id']]['score']
        candidates = [w for w in ranked[1:] if
                      leader_score - suitability[w['worker_id']]['score'] <= config['policy']['exploration_gap']
                      and suitability[w['worker_id']]['sample_count'] < config['policy']['exploration_max_samples']
                      and suitability[w['worker_id']]['sample_count'] < suitability[ranked[0]['worker_id']]['sample_count']]
        if candidates:
            selected, mode = candidates[0], 'EXPLORE'
            reasons.append('Low-risk, strongly verified first attempt: close-scoring candidate has fewer independent samples.')
    for candidate in suitability.values():
        candidate['score_explanation'] = (
            f'score={candidate["score"]:.4f}; prior={candidate["prior_score"]:.4f}; '
            f'empirical={candidate["empirical_score"] if candidate["empirical_score"] is not None else "unknown"}; '
            f'effective_weight={candidate["effective_sample_weight"]:.3f}; '
            f'failure_penalty={candidate["failure_severity_penalty"]:.4f}; '
            f'cost/latency/repair_penalties={candidate["cost_penalty"]}/'
            f'{candidate["latency_penalty"]}/{candidate["repair_penalty"]}; '
            f'evidence_ids={candidate["evidence_ids"]}')
    row = suitability[selected['worker_id']]
    alternatives = [w['worker_id'] for w in ranked if w['worker_id'] != selected['worker_id']]
    reasons.append(row['score_explanation'] + f'; independent historical tasks={row["sample_count"]}.')
    if not evidence:
        reasons.insert(0, 'No validated comparable history; using configured cold-start priors.')
    return {'selected_worker': selected['worker_id'], 'reasoning_effort': selected['reasoning_effort'],
            'selection_mode': mode, 'routing_reason': ' '.join(reasons),
            'historical_sample_count': row['sample_count'], 'historical_confidence': row['confidence'],
            'alternative_worker': alternatives[0] if alternatives else None,
            'historical_evidence_used': row['evidence_ids'], 'suitability': suitability}
