"""Pure verification policy, risk assessment, reviewer routing and evidence gates.

Selection is advisory. PASS never substitutes for Commander acceptance.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

FEATURES = ('complexity', 'uncertainty', 'business_impact', 'irreversibility',
            'security_risk', 'external_side_effects', 'worker_historical_failure_rate',
            'verification_difficulty')
TIERS = ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
ROLES = ('requirements_reviewer', 'correctness_reviewer', 'code_reviewer',
         'security_reviewer', 'architecture_reviewer', 'adversarial_reviewer',
         'ux_reviewer', 'business_reviewer', 'evidence_reviewer')
ACTIONS = ('accept', 'minor_fix', 'strategy_failure', 'worker_mismatch',
           'ambiguous_task', 'high_risk_uncertainty')


def _number(value, name, lower=0, upper=None):
    if type(value) not in (int, float) or not math.isfinite(value) or value < lower or (upper is not None and value > upper):
        raise ValueError(f'{name} must be finite numeric in [{lower}, {upper}]')
    return value


def default_policy():
    return validate_policy(json.loads(Path(__file__).with_name('verification_policy.json').read_text()))


def validate_policy(config):
    """Validate the entire frozen policy and return an independent snapshot."""
    if not isinstance(config, dict):
        raise ValueError('verification policy must be an object')
    # Scan aliases/nested model metadata as well as canonical provider fields.
    if 'gemini' in json.dumps(config, ensure_ascii=False).casefold():
        raise ValueError('Gemini reviewers are unsupported, including aliases')
    p = deepcopy(config)
    try:
        p.setdefault('judge', dict(min_confidence=.5, high_scrutiny_confidence=.7, worker_failure_scrutiny_threshold=.4, min_reliability=.4))
        for key in ('min_confidence','high_scrutiny_confidence','worker_failure_scrutiny_threshold','min_reliability'):
            _number(p['judge'][key], key, 0, 1)
        p.setdefault('selection_weights', dict(reliability=.45, independence=.25, diversity=.15, cost=.075, latency=.075))
        if set(p['selection_weights']) != {'reliability', 'independence', 'diversity', 'cost', 'latency'}:
            raise ValueError('selection_weights must name all five score components')
        for key, value in p['selection_weights'].items():
            _number(value, key)
        if sum(p['selection_weights'].values()) <= 0:
            raise ValueError('selection_weights must have positive total')
        if set(p['weights']) != set(FEATURES):
            raise ValueError('weights must contain exactly all eight risk features')
        for k, v in p['weights'].items():
            _number(v, k)
        if sum(p['weights'].values()) <= 0:
            raise ValueError('risk weights must have a positive total')
        thresholds = [_number(p['thresholds'][k], k, 0, 1) for k in ('medium', 'high', 'critical')]
        if not 0 < thresholds[0] < thresholds[1] < thresholds[2] <= 1:
            raise ValueError('risk thresholds must be strictly ordered')
        if set(p['tiers']) != set(TIERS):
            raise ValueError('all four tiers are required')
        for tier, count in zip(TIERS, (0, 1, 2, 2)):
            t = p['tiers'][tier]
            if type(t['reviewers']) is not int or t['reviewers'] != count:
                raise ValueError(f'{tier} requires {count} normal reviewers')
            if any(type(t[k]) is not bool for k in ('adversarial_review', 'human_approval')):
                raise ValueError('tier gates must be boolean')
        if not p['tiers']['CRITICAL']['adversarial_review'] or not p['tiers']['CRITICAL']['human_approval']:
            raise ValueError('CRITICAL requires adversarial review and human approval')
        for feature, floor in p.get('risk_floors', {}).items():
            if feature not in FEATURES or floor['tier'] not in TIERS:
                raise ValueError('invalid risk floor')
            _number(floor['threshold'], 'floor threshold', 0, 1)
        if type(p['max_revision_rounds']) is not int or p['max_revision_rounds'] not in (0, 1):
            raise ValueError('zero or one revision round is allowed')
        for key in ('max_total_cost', 'max_total_tokens', 'max_wall_time', 'max_reviewer_calls'):
            _number(p['budgets'][key], key, 0)
        for key in ('max_total_tokens', 'max_reviewer_calls'):
            if type(p['budgets'][key]) is not int:
                raise ValueError(f'{key} must be integer')
        if type(p['history']['min_samples']) is not int or p['history']['min_samples'] < 1:
            raise ValueError('min_samples must be positive integer')
        _number(p['history']['half_life_days'], 'half_life_days', 0.000001)
        if not isinstance(p['reviewers'], list):
            raise ValueError('reviewers must be a list')
        ids = set()
        for r in p['reviewers']:
            if not isinstance(r['reviewer_id'], str) or not r['reviewer_id'].strip() or r['reviewer_id'] in ids:
                raise ValueError('reviewer IDs must be unique nonempty strings')
            ids.add(r['reviewer_id'])
            if (r['provider'], r['family']) not in (('openai', 'gpt'), ('anthropic', 'claude')):
                raise ValueError('unsupported or inconsistent provider/family')
            if not isinstance(r['model_id'], str) or not r['model_id'].strip():
                raise ValueError('model_id is required')
            model = r['model_id'].casefold()
            if ('claude' in model and r['family'] != 'claude') or ('gpt' in model and r['family'] != 'gpt'):
                raise ValueError('model_id conflicts with reviewer family')
            aliases = r.get('allowed_resolved_models', [])
            if not isinstance(aliases, list) or any(not isinstance(a, str) or r['family'] not in a.lower() for a in aliases):
                raise ValueError('resolved model aliases must explicitly belong to reviewer family')
            if type(r['enabled']) is not bool:
                raise ValueError('enabled must be boolean')
            if not isinstance(r['roles_supported'], list) or not r['roles_supported'] or any(x not in ROLES for x in r['roles_supported']):
                raise ValueError('invalid reviewer roles')
            if not isinstance(r['capabilities'], list) or any(not isinstance(x, str) for x in r['capabilities']):
                raise ValueError('capabilities must be strings')
            for key in ('cost_class', 'latency_class'):
                if r[key] not in ('low', 'medium', 'high'):
                    raise ValueError(f'invalid {key}')
            for key in ('max_cost_usd', 'max_tokens', 'timeout_seconds'):
                _number(r[key], key, 0.000001)
            if type(r['max_tokens']) is not int:
                raise ValueError('max_tokens must be integer')
            a = r['adapter']
            if a['kind'] == 'command':
                if not isinstance(a['command'], list) or not a['command'] or any(not isinstance(x, str) or not x for x in a['command']):
                    raise ValueError('command adapter requires argv')
            elif a['kind'] == 'claude_code_reviewer':
                from routing.claude_reviewer import validate_adapter
                validate_adapter(a)
                if r['family'] != 'claude':
                    raise ValueError('Claude client requires Claude family')
            elif a['kind'] == 'anthropic_messages':
                from routing.anthropic_reviewer import validate_adapter
                validate_adapter(a)
                if r['family'] != 'claude':
                    raise ValueError('Anthropic adapter requires Claude family')
            elif a['kind'] == 'openrouter':
                if a['api_key_env'] != 'OPENROUTER_API_KEY':
                    raise ValueError('openrouter requires OPENROUTER_API_KEY env reference')
                if type(a['max_output_tokens']) is not int or a['max_output_tokens'] < 1:
                    raise ValueError('max_output_tokens must be positive integer')
            else:
                raise ValueError('unsupported reviewer adapter')
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'malformed verification policy: {exc}') from exc
    return p


def assess_risk(features, policy):
    p = validate_policy(policy)
    if not isinstance(features, dict) or any(k not in features for k in FEATURES):
        raise ValueError('all eight risk features are required')
    values = {k: _number(features[k], k, 0, 1) for k in FEATURES}
    score = sum(values[k] * p['weights'][k] for k in FEATURES) / sum(p['weights'].values())
    level = sum(score >= p['thresholds'][k] for k in ('medium', 'high', 'critical'))
    reasons = [f'Weighted risk score {score:.4f}']
    for key, floor in p.get('risk_floors', {}).items():
        if values[key] >= floor['threshold']:
            level = max(level, TIERS.index(floor['tier']))
            reasons.append(f'{key}={values[key]:.3f} triggers {floor["tier"]} floor')
    return dict(tier=TIERS[level], score=score, reasons=reasons, features=values)


def _tier(risk):
    tier = risk if isinstance(risk, str) else risk.get('tier')
    if tier not in TIERS:
        raise ValueError('invalid risk tier')
    return tier


def _model_id(value):
    value = str(value or '').casefold()
    if '/' in value and value.split('/', 1)[0] in ('openai', 'anthropic', 'codex'):
        value = value.split('/', 1)[1]
    return value


def _family(worker):
    if worker.get('family') in ('gpt', 'claude'):
        return worker['family']
    hint = ' '.join(str(worker.get(k, '')).casefold() for k in ('provider', 'model_id', 'model'))
    if any(x in hint for x in ('anthropic', 'claude')):
        return 'claude'
    if any(x in hint for x in ('openai', 'gpt', 'codex')):
        return 'gpt'
    return None


def _reliability(reviewer, role, signature, history, policy, tier):
    now = datetime.now(timezone.utc)
    total = good = 0.0
    samples = 0
    for h in history:
        if not isinstance(h, dict) or h.get('source_kind') != 'real' or h.get('confirmed') is not True or type(h.get('correct')) is not bool:
            continue
        if h.get('valid') is False:
            continue
        if any(h.get(k) for k in ('invalid', 'cancelled', 'synthetic', 'own_execution', 'same_artifact_execution')):
            continue
        if h.get('reviewer_id') != reviewer['reviewer_id'] or _model_id(h.get('model_id')) != _model_id(reviewer['model_id']) or h.get('role') != role:
            continue
        past = h.get('task_signature', {})
        if not isinstance(past, dict) or any(not signature.get(k) or past.get(k) != signature[k] for k in ('domain', 'task_type')):
            continue
        if h.get('provider') is not None and h['provider'] != reviewer['provider']:
            continue
        if reviewer.get('model_revision') is not None and h.get('model_revision') != reviewer['model_revision']:
            continue
        signature_risk = str(signature.get('risk_level', tier)).upper()
        current_risk = max((tier, signature_risk), key=lambda value: TIERS.index(value) if value in TIERS else -1)
        past_risk = str(h.get('risk_level', h.get('risk_tier', past.get('risk_level', '')))).upper()
        if current_risk in ('HIGH', 'CRITICAL') and past_risk not in ('HIGH', 'CRITICAL'):
            continue
        if current_risk == 'CRITICAL' and past_risk != 'CRITICAL':
            continue
        if h.get('worker_model_id') and _model_id(h['worker_model_id']) == _model_id(reviewer['model_id']):
            continue
        try:
            stamp = datetime.fromisoformat(h['timestamp'].replace('Z', '+00:00'))
            age = (now - stamp).total_seconds() / 86400
            if age < 0:
                continue
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        weight = 0.5 ** (age / policy['history']['half_life_days'])
        total += weight
        good += weight * h['correct']
        samples += 1
    prior = policy['history']['min_samples']
    return {'score': (good + prior * 0.5) / (total + prior), 'samples': samples,
            'effective_samples': total, 'confidence': total / (total + prior),
            'reason': 'Confirmed real same-domain/task/role/model evidence with recency decay and neutral shrinkage'}


def select_reviewers(signature, worker, history, policy, risk):
    p = validate_policy(policy)
    tier = _tier(risk)
    descriptor = ' '.join(str(signature.get(k, '')) for k in ('domain', 'task_type', 'task_subtype')).casefold()
    if 'security' in descriptor or (isinstance(risk, dict) and risk.get('features', {}).get('security_risk', 0) >= .5):
        preferred = ['security_reviewer', 'correctness_reviewer']
    elif any(x in descriptor for x in ('research', 'paper', 'evidence')):
        preferred = ['evidence_reviewer', 'requirements_reviewer']
    elif any(x in descriptor for x in ('business', 'strategy')):
        preferred = ['business_reviewer', 'requirements_reviewer']
    elif any(x in descriptor for x in ('design', 'ux', 'frontend')):
        preferred = ['ux_reviewer', 'code_reviewer']
    elif 'architecture' in descriptor:
        preferred = ['architecture_reviewer', 'correctness_reviewer']
    else:
        preferred = ['correctness_reviewer', 'code_reviewer']
    roles = preferred[:p['tiers'][tier]['reviewers']]
    if p['tiers'][tier]['adversarial_review']:
        roles.append('adversarial_reviewer')
    selected, missing = [], []
    for role in roles:
        candidates = []
        for r in p['reviewers']:
            if not r['enabled'] or role not in r['roles_supported']:
                continue
            if role != 'adversarial_reviewer' and any(x['reviewer']['reviewer_id'] == r['reviewer_id'] for x in selected):
                continue
            same_model = _model_id(r['model_id']) == _model_id(worker.get('model_id', worker.get('model')))
            independence = 0.3 if same_model else (0.6 if r['family'] == _family(worker) else 1.0)
            rel = _reliability(r, role, signature, history, p, tier)
            different_model = not any(_model_id(x['reviewer']['model_id']) == _model_id(r['model_id']) for x in selected)
            different_family = not any(x['reviewer']['family'] == r['family'] for x in selected)
            components = dict(independence=independence, reliability=rel['score'],
                              diversity=(different_model + different_family) / 2,
                              cost={'low':1, 'medium':.5, 'high':0}[r['cost_class']],
                              latency={'low':1, 'medium':.5, 'high':0}[r['latency_class']])
            rank = sum(components[k] * p['selection_weights'][k] for k in components) / sum(p['selection_weights'].values())
            candidates.append((rank, r, rel, independence, components))
        if not candidates:
            missing.append(role)
            continue
        rank, reviewer, reliability, independence, components = max(candidates, key=lambda x: x[0])
        selected.append(dict(role=role, reviewer=deepcopy(reviewer), independence_score=independence,
                             reliability=reliability, selection_score=rank, score_components=components,
                             reason=f'Weighted score {rank:.4f}; components {components}; weights {p["selection_weights"]}'))
    return dict(selected=selected, missing_roles=missing,
                reason=f'{tier}: required roles {roles}; registry capability and role coverage are explicit claims')


def judge(risk, checks, reviews, selection, policy, worker_failure_rate=0):
    p = validate_policy(policy)
    tier = _tier(risk)
    _number(worker_failure_rate, 'worker_failure_rate', 0, 1)
    reasons = [f'Risk {tier}; Worker historical failure rate {worker_failure_rate:.3f}.',
               'Confidence, specialty and conditional history inform scrutiny; they never outvote unresolved evidence.',
               'Commander artifact review and acceptance remain required, including LOW risk.']
    if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks):
        raise ValueError('checks must be a list of objects')
    if not isinstance(reviews, list) or not all(isinstance(r, dict) for r in reviews):
        raise ValueError('reviews must be a list of objects')
    failed = [c.get('id', '?') for c in checks if c.get('required') is True and c.get('status') == 'failed']
    absent = [c.get('id', '?') for c in checks if c.get('required') is True and c.get('status') not in ('passed', 'failed')]
    if not any(c.get('required') is True for c in checks):
        absent.append('at least one required check')
    missing = list(selection.get('missing_roles', []))
    uncertain, severe, moderate, verdicts, actions = [], [], [], [], []
    expected = selection.get('selected', [])
    required_count = p['tiers'][tier]['reviewers'] + int(p['tiers'][tier]['adversarial_review'])
    if len(expected) < required_count:
        missing.append('required reviewer selection')
    for s in expected:
        matches = [r for r in reviews if r.get('role') == s['role'] and r.get('reviewer_id') == s['reviewer']['reviewer_id']]
        if len(matches) != 1:
            missing.append(s['role'])
    expected_pairs = [(s['role'], s['reviewer']['reviewer_id']) for s in expected]
    if len(set(expected_pairs)) != len(expected_pairs):
        missing.append('distinct review slots')
    normal_roles = [s['role'] for s in expected if s['role'] != 'adversarial_reviewer']
    if len(set(normal_roles)) < p['tiers'][tier]['reviewers']:
        missing.append('distinct normal reviewer roles')
    if p['tiers'][tier]['adversarial_review'] and not any(s['role'] == 'adversarial_reviewer' for s in expected):
        missing.append('adversarial_reviewer')
    for review in reviews:
        if (review.get('role'), review.get('reviewer_id')) not in expected_pairs:
            uncertain.append('unrequested reviewer result')
        result = review.get('result', {})
        if not isinstance(result, dict):
            uncertain.append('malformed reviewer result')
            continue
        if review.get('valid') is False or result.get('valid') is False or review.get('error') or result.get('error'):
            uncertain.append(f'{review.get("role")}: invalid or error result')
        specialty = result.get('reviewer_specialty')
        if specialty != review.get('role'):
            uncertain.append(f'{review.get("role")}: specialty does not match assigned role')
        reasons.append(f'Reviewer {review.get("reviewer_id")}: assigned={review.get("role")}, specialty={specialty}, confidence={result.get("confidence")}, conditional_history={review.get("reliability")}, independence={review.get("independence_score")}.')
        verdict = str(result.get('verdict', '')).upper()
        verdicts.append(verdict)
        confidence = result.get('confidence')
        threshold = p['judge']['high_scrutiny_confidence'] if tier in ('HIGH','CRITICAL') or worker_failure_rate >= p['judge']['worker_failure_scrutiny_threshold'] else p['judge']['min_confidence']
        rel = review.get('reliability') or {}
        if rel.get('effective_samples', 0) >= p['history']['min_samples'] and rel.get('score', .5) < p['judge']['min_reliability']:
            uncertain.append(f'{review.get("role")}: confirmed domain reliability below policy floor')
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1 or confidence < threshold:
            uncertain.append(f'{review.get("role")}: low or invalid confidence')
        if verdict not in ('PASS', 'REVISE', 'FAIL', 'ESCALATE') or verdict == 'ESCALATE':
            uncertain.append(f'{review.get("role")}: uncertain verdict')
        if not result.get('evidence') or not result.get('reviewer_specialty'):
            uncertain.append(f'{review.get("role")}: missing evidence or specialty')
        independence = review.get('independence_score', 0)
        if type(independence) not in (int, float) or not math.isfinite(independence) or not 0 < independence <= 1:
            uncertain.append(f'{review.get("role")}: no Worker independence')
        issues = result.get('issues', [])
        if not isinstance(issues, list):
            uncertain.append('malformed issues')
            issues = []
        for issue in issues:
            if not isinstance(issue, dict):
                uncertain.append('malformed issue')
                continue
            # Resolution is a separate Commander operation, not a reviewer flag.
            if issue.get('severity') in ('high', 'critical'):
                severe.append(issue.get('id', '?'))
            elif issue.get('severity') in ('low', 'medium'):
                moderate.append(issue.get('id', '?'))
            else:
                uncertain.append('unknown issue severity')
            if not issue.get('evidence'):
                uncertain.append('issue without evidence')
        actions.append(result.get('recommended_action'))
    def answer(status, action, more):
        return dict(status=status, recommended_action=action, reasons=reasons + more)
    if failed:
        return answer('REVISE', 'strategy_failure', [f'Required checks failed: {failed}; reviewer PASS cannot override.'] )
    if severe:
        return answer('ESCALATE', 'high_risk_uncertainty', [f'Unresolved severe issues: {severe}; passing tests or votes do not disprove findings.'])
    if absent or missing or uncertain:
        return answer('ESCALATE', 'high_risk_uncertainty', [f'Incomplete checks: {absent}; missing review: {missing}; uncertainty: {uncertain}'])
    if 'PASS' in verdicts and any(v in ('FAIL', 'REVISE') for v in verdicts):
        return answer('ESCALATE', 'high_risk_uncertainty', ['Reviewer conflict requires evidence adjudication.'])
    if moderate or any(v in ('FAIL', 'REVISE') for v in verdicts):
        action = next((a for a in actions if a in ACTIONS and a != 'accept'), 'minor_fix')
        return answer('REVISE', action, [f'Revision findings: {moderate}'])
    if p['tiers'][tier]['human_approval']:
        return answer('HUMAN_APPROVAL_REQUIRED', 'accept', ['Policy requires explicit human approval before acceptance.'])
    return answer('PASS', 'accept', ['Available evidence supports a recommendation to accept.'])
