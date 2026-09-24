"""Validated public routing contracts. No external IO except loading the registry JSON."""
from copy import deepcopy
from datetime import datetime
import json
import math
from pathlib import Path

MAX_WORKER_ATTEMPTS = 2
SIGNATURE_LABELS = ('domain', 'task_type', 'task_subtype', 'language', 'framework')
SCALE = ('low', 'medium', 'high')
SIGNATURE_SCALES = ('complexity', 'reasoning_intensity', 'tool_intensity', 'risk_level',
                    'cross_module_scope', 'estimated_execution_volume')
SIGNATURE_FIELDS = SIGNATURE_LABELS + SIGNATURE_SCALES + ('verification_strength', 'scope', 'environment')
ATTRIBUTIONS = ('MODEL_RELATED', 'TASK_SPEC_RELATED', 'ENVIRONMENT_RELATED', 'TOOL_RELATED',
                'DATA_RELATED', 'EXTERNAL_SERVICE_RELATED', 'UNKNOWN', 'NONE')


def _number(value, label, *, minimum=0, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{label} must be a finite number in range')
    return value


def _label(value, name):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f'{name} must be a nonempty, trimmed string')
    return value


def validate_signature(fields):
    if not isinstance(fields, dict):
        raise ValueError('signature must be an object')
    result = {}
    for name in SIGNATURE_LABELS:
        result[name] = _label(fields.get(name), name)
    for name in SIGNATURE_SCALES:
        value = fields.get(name)
        if value not in SCALE or type(value) is not str:
            raise ValueError(f'{name} must be low/medium/high')
        result[name] = value
    for name, options in (('verification_strength', ('weak', 'moderate', 'strong')),
                          ('scope', ('single_file', 'multi_file', 'repository')),
                          ('environment', ('local', 'ci', 'staging', 'production'))):
        value = fields.get(name)
        if type(value) is not str or value not in options:
            raise ValueError(f'{name} invalid')
        result[name] = value
    capabilities = fields.get('required_capabilities', [])
    if not isinstance(capabilities, list) or any(not isinstance(x, str) or not x.strip() or x != x.strip() for x in capabilities) or len(capabilities) != len(set(capabilities)):
        raise ValueError('required_capabilities must be a list of unique, nonempty strings')
    result['required_capabilities'] = capabilities[:]
    return result


def profile_task(fields, repo_context=None):
    result = validate_signature(fields)
    if repo_context is not None:
        if not isinstance(repo_context, dict):
            raise ValueError('repo_context must be an object')
        try:
            json.dumps(repo_context, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('repo_context must be finite JSON data') from exc
        result['repo_context'] = deepcopy(repo_context)
    return result


def validate_diagnosis(fields, accepted):
    if type(accepted) is not bool or not isinstance(fields, dict):
        raise ValueError('diagnosis and accepted flag required')
    attribution = fields.get('attribution')
    failure_type = fields.get('failure_type')
    severity = fields.get('severity')
    summary = fields.get('summary')
    if attribution not in ATTRIBUTIONS or type(attribution) is not str:
        raise ValueError('invalid attribution')
    if type(severity) is not str or severity not in ('none', 'low', 'medium', 'high'):
        raise ValueError('invalid severity')
    if accepted:
        if attribution != 'NONE' or failure_type != 'NONE' or severity != 'none':
            raise ValueError('accepted work has no failure attribution')
        if summary is not None and not isinstance(summary, str):
            raise ValueError('invalid summary')
    else:
        if attribution == 'NONE' or not isinstance(failure_type, str) or not failure_type.strip() or failure_type == 'NONE' or severity == 'none':
            raise ValueError('rejected work needs failure type, attribution and severity')
        _label(summary, 'summary')
    return {'attribution': attribution, 'failure_type': failure_type, 'severity': severity,
            'summary': summary or ''}


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError('config must be an object')
    if type(config.get('max_worker_attempts')) is not int or config['max_worker_attempts'] != MAX_WORKER_ATTEMPTS:
        raise ValueError('max_worker_attempts must equal 2')
    if config.get('routing_mode') != 'AUTO':
        raise ValueError('routing_mode must be AUTO')
    _label(config.get('currency'), 'currency')
    workers = config.get('workers')
    if not isinstance(workers, list) or not workers:
        raise ValueError('workers must be a nonempty list')
    seen = set()
    for w in workers:
        if not isinstance(w, dict):
            raise ValueError('worker must be an object')
        for key in ('worker_id', 'provider', 'model', 'reasoning_effort', 'version'):
            _label(w.get(key), key)
        if w['worker_id'] in seen:
            raise ValueError('duplicate worker id')
        seen.add(w['worker_id'])
        if type(w.get('enabled')) is not bool or w.get('availability') not in ('available', 'unavailable'):
            raise ValueError('invalid availability/enabled')
        if w['reasoning_effort'] not in ('low', 'medium', 'high', 'xhigh'):
            raise ValueError('invalid reasoning effort')
        adapter = w.get('adapter')
        if not isinstance(adapter, dict) or adapter.get('kind') not in ('codex_worker', 'command') or not isinstance(adapter.get('command'), list) or not adapter['command'] or any(not isinstance(a, str) or not a.strip() for a in adapter['command']):
            raise ValueError('adapter requires a nonempty argv command')
        caps = w.get('capabilities')
        if not isinstance(caps, list) or any(not isinstance(c, str) or not c.strip() for c in caps) or len(caps) != len(set(caps)):
            raise ValueError('invalid capabilities')
        for profile, field in (('cost_profile', 'estimated_cost'), ('latency_profile', 'estimated_seconds')):
            p = w.get(profile)
            if not isinstance(p, dict) or field not in p:
                raise ValueError(f'invalid {profile}')
            if p[field] is not None:
                _number(p[field], field)
        currency = w['cost_profile'].get('currency')
        if currency is not None:
            _label(currency, 'worker currency')
        prior = w.get('prior')
        if not isinstance(prior, dict):
            raise ValueError('prior required')
        _number(prior.get('base'), 'prior.base', maximum=1)
        for key in ('domain_preferences', 'task_type_preferences', 'reasoning_intensity_preferences'):
            preferences = prior.get(key)
            if not isinstance(preferences, dict):
                raise ValueError(f'{key} must be an object')
            for label, value in preferences.items():
                _label(label, key)
                _number(value, key, minimum=-1, maximum=1)
        if not isinstance(w.get('manual_notes', ''), str):
            raise ValueError('manual_notes must be text')
    policy = config.get('policy')
    if not isinstance(policy, dict):
        raise ValueError('policy required')
    bounded = ('similarity_threshold', 'version_discount', 'exploration_gap', 'failure_penalty',
               'cost_penalty', 'latency_penalty', 'repair_penalty', 'repair_quality_penalty')
    positive = ('recency_half_life_days', 'recency_window_days', 'shrinkage_samples',
                'confidence_medium_samples', 'confidence_high_samples', 'exploration_max_samples')
    for key in bounded:
        _number(policy.get(key), key, maximum=1)
    for key in positive:
        _number(policy.get(key), key, minimum=0.000001)
    if policy['confidence_high_samples'] <= policy['confidence_medium_samples']:
        raise ValueError('confidence thresholds out of order')
    if type(policy.get('exploration_enabled')) is not bool:
        raise ValueError('exploration_enabled must be boolean')
    weights = policy.get('similarity_weights')
    expected = {'domain', 'task_type', 'related_task_type', 'task_subtype', 'language', 'framework', 'scope', 'complexity', 'tool_intensity', 'cross_module_scope', 'estimated_execution_volume', 'reasoning_intensity', 'risk_level', 'verification_strength'}
    if not isinstance(weights, dict) or set(weights) != expected:
        raise ValueError('complete similarity_weights required')
    for value in weights.values():
        _number(value, 'similarity weight', maximum=1)
    _number(config.get('execution_timeout_seconds'), 'execution timeout', minimum=0.001)
    groups = policy.get('task_type_groups')
    if not isinstance(groups, list) or any(not isinstance(group, list) or not group or any(not isinstance(x, str) or not x.strip() for x in group) for group in groups):
        raise ValueError('invalid task_type_groups')
    severities = policy.get('failure_severity')
    if not isinstance(severities, dict) or set(severities) != {'none', 'low', 'medium', 'high'}:
        raise ValueError('failure_severity must define each severity')
    for value in severities.values():
        _number(value, 'failure_severity', maximum=1)
    weights = policy.get('failure_type_weights')
    if not isinstance(weights, dict):
        raise ValueError('failure_type_weights must be an object')
    for name, value in weights.items():
        _label(name, 'failure_type')
        _number(value, 'failure_type_weight', maximum=1)
    _number(policy.get('default_failure_type_weight'), 'default_failure_type_weight', maximum=1)
    # Catch invalid numeric extensions as well as JSON NaN/Infinity and booleans in numeric slots.
    def check_tree(node):
        if isinstance(node, dict):
            for item in node.values():
                check_tree(item)
        elif isinstance(node, list):
            for item in node:
                check_tree(item)
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError('nonfinite config value')
    check_tree(config)
    return deepcopy(config)


def load_config(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name('defaults.json')
    try:
        data = json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (OSError, ValueError) as exc:
        raise ValueError(f'cannot load routing config: {exc}') from exc
    return validate_config(data)
