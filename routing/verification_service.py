"""Additive verification lifecycle. Commander owns conclusions and authority."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


def _now():
    return datetime.now(timezone.utc).isoformat()


def _num(value, name):
    import math
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{name} must be nonnegative and finite')
    return value


def snapshot(workspace, names):
    root = Path(workspace).resolve()
    if not isinstance(names, list) or not names or len(names) != len(set(names)):
        raise ValueError('unique verification artifacts required')
    artifacts = []
    for name in names:
        if not isinstance(name, str) or not name or Path(name).is_absolute():
            raise ValueError('artifact path must be relative')
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or '.git' in Path(name).parts:
            raise ValueError('artifact must be a workspace file outside .git')
        with path.open('rb') as stream:
            data = stream.read(262145)
        if len(data) > 262144:
            raise ValueError('artifact too large; select a bounded verifiable artifact')
        artifacts.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                          'content': data.decode('utf-8')})
    if sum(len(a['content'].encode()) for a in artifacts) > 524288:
        raise ValueError('artifact packet too large')
    identity = [{k: a[k] for k in ('path', 'sha256')} for a in artifacts]
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return artifacts, digest


def initialize_verification(spec, config):
    from routing.verification_rules import default_policy, validate_policy, assess_risk
    if not isinstance(spec, dict):
        raise ValueError('verification specification must be an object')
    policy = validate_policy(config if config is not None else default_policy())
    features = deepcopy(spec.get('risk_features'))
    risk = assess_risk(features, policy)
    artifacts = spec.get('artifacts')
    if not isinstance(artifacts, list) or not artifacts or any(not isinstance(x, str) or not x or Path(x).is_absolute() or '..' in Path(x).parts for x in artifacts):
        raise ValueError('relative artifact paths required')
    checks = spec.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('at least one explicit deterministic check required')
    ids = set()
    for check in checks:
        if (not isinstance(check, dict) or not isinstance(check.get('id'), str)
                or not check['id'] or check['id'] in ids):
            raise ValueError('unique check ids required')
        ids.add(check['id'])
        argv = check.get('argv')
        if not isinstance(argv, list) or not argv or any(not isinstance(s, str) or not s for s in argv):
            raise ValueError('check requires trusted argv, never shell command text')
        if type(check.get('required', True)) is not bool:
            raise ValueError('check.required must be boolean')
        if not 0 < _num(check.get('timeout_seconds', 30), 'check timeout') <= 120:
            raise ValueError('check timeout must be <=120 seconds')
    if not any(c.get('required', True) for c in checks):
        raise ValueError('at least one required deterministic check is mandatory')
    reservation = spec.get('worker_reservation')
    if not isinstance(reservation, dict):
        raise ValueError('worker_reservation cost_usd/tokens required for budget admission')
    _num(reservation.get('cost_usd'), 'worker reservation cost')
    if type(reservation.get('tokens')) is not int or reservation['tokens'] < 0:
        raise ValueError('worker token reservation required')
    context = spec.get('context', '')
    if not isinstance(context, str) or len(context) > 16000:
        raise ValueError('bounded explicit reviewer context required')
    return {'policy': policy, 'risk': risk, 'artifact_paths': deepcopy(artifacts),
            'check_specs': deepcopy(checks), 'context': context,
            'worker_reservation': deepcopy(reservation), 'created_at': _now(),
            'reservations': [], 'sessions': []}


def reserve_budget(v, kind, identity, cost, tokens):
    """Admission ceilings are not a billing-provider hard spending limit."""
    policy = v['policy']['budgets']
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(v['created_at'])).total_seconds()
    if elapsed >= policy['max_wall_time']:
        raise ValueError('verification task wall-time budget exhausted')
    rows = v['reservations']
    if any(r.get('unconverted_cost') is not None for r in rows):
        raise ValueError('unconverted Worker cost blocks budget admission')
    if sum(max(x['cost_reserved'], x.get('actual_cost') or 0) for x in rows) + cost > policy['max_total_cost']:
        raise ValueError('total cost reservation budget exhausted')
    if sum(max(x['tokens_reserved'], x.get('actual_tokens') or 0) for x in rows) + tokens > policy['max_total_tokens']:
        raise ValueError('total token reservation budget exhausted')
    if kind == 'reviewer' and sum(x['kind'] == 'reviewer' for x in rows) >= policy['max_reviewer_calls']:
        raise ValueError('reviewer call budget exhausted')
    rows.append({'kind': kind, 'id': identity, 'cost_reserved': cost, 'tokens_reserved': tokens,
                 'actual_cost': None, 'actual_tokens': None, 'timestamp': _now()})


def worker_budget(task, worker):
    v = task.get('verification_layer')
    if not v:
        return
    if task['worker_attempt_count'] > v['policy']['max_revision_rounds']:
        raise ValueError('verification revision budget exhausted; Commander takeover')
    allowance = v['worker_reservation']
    reserve_budget(v, 'worker', f"worker:{task['worker_attempt_count']+1}", allowance['cost_usd'], allowance['tokens'])


def acceptance_gate(task, kind='worker'):
    v = task.get('verification_layer')
    if not v:
        return
    rows = v['reservations']; limits = v['policy']['budgets']
    if any(r.get('unconverted_cost') is not None for r in rows) or sum(max(r['cost_reserved'],r.get('actual_cost') or 0) for r in rows) > limits['max_total_cost'] or sum(max(r['tokens_reserved'],r.get('actual_tokens') or 0) for r in rows) > limits['max_total_tokens']:
        raise ValueError('resource overrun requires escalation; cannot accept')
    sessions = [s for s in v['sessions'] if s['attempt_number'] == task['worker_attempt_count'] and s['kind'] == kind]
    if not sessions or sessions[-1]['status'] != 'COMPLETE':
        raise ValueError('completed verification required before acceptance')
    session = sessions[-1]
    _, current = snapshot(task['workspace'], v['artifact_paths'])
    if current != session['artifact_digest']:
        raise ValueError('artifacts changed after verification')
    status = session['judge']['status']
    if status not in ('PASS', 'HUMAN_APPROVAL_REQUIRED'):
        raise ValueError('verification judge has not cleared acceptance')
    if v['policy']['tiers'][v['risk']['tier']]['human_approval']:
        approval = session.get('human_approval')
        if not approval or not approval['approved'] or approval['artifact_digest'] != current:
            raise ValueError('human approval required for current verified artifacts')


class VerificationMixin:
    def verify(self, task_id, kind='worker'):
        from routing.service import commander_only, resolve, event
        from routing.verification_rules import select_reviewers, judge
        from routing.reviewer_runtime import build_blind_packet, run_reviewer, run_command
        commander_only()
        if kind not in ('worker', 'takeover'):
            raise ValueError('invalid verification kind')
        initial = self.inspect(task_id)
        v = initial.get('verification_layer')
        if not v:
            raise ValueError('task has no verification policy snapshot')
        allowed = ('AWAITING_REVIEW',) if kind == 'worker' else ('TAKEOVER_REQUIRED', 'BLOCKED', 'RETRY_READY')
        if initial['status'] not in allowed or not initial['attempts']:
            raise ValueError('task not ready for verification')
        artifacts, digest = snapshot(initial['workspace'], v['artifact_paths'])
        def start(state):
            task = resolve(state, task_id); layer = task['verification_layer']
            if task['status'] != initial['status'] or task['worker_attempt_count'] != initial['worker_attempt_count']:
                raise ValueError('task changed before verification')
            previous = [s for s in layer['sessions'] if s['attempt_number'] == task['worker_attempt_count'] and s['kind'] == kind]
            if any(s['status'] == 'RUNNING' for s in layer['sessions']):
                raise ValueError('verification already running; recover explicitly if interrupted')
            if len(previous) >= 2:
                raise ValueError('two verification sessions exhausted; escalate')
            reserve_budget(layer, 'verification', f'session:{len(layer["sessions"])+1}', 0, 0)
            sid = f"{task['logical_task_id']}:{task['worker_attempt_count']}:{kind}:{len(previous)+1}"
            session = {'session_id': sid, 'attempt_number': task['worker_attempt_count'], 'kind': kind,
                       'status': 'RUNNING', 'started_at': _now(), 'artifact_digest': digest,
                       'artifacts': [{k: a[k] for k in ('path', 'sha256')} for a in artifacts],
                       'checks': [], 'reviews': [], 'selection': None, 'judge': None, 'human_approval': None}
            layer['sessions'].append(session)
            event(state, 'VERIFICATION_STARTED', task, session_id=sid, risk=layer['risk'])
            return sid
        sid = self.store.transaction(start)
        started = time.monotonic()
        checks, reviews = [], []
        selection = {'selected': [], 'missing_roles': [], 'reason': 'deterministic checks first'}
        fatal = None
        def remaining():
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(v['created_at'])).total_seconds()
            return max(0, v['policy']['budgets']['max_wall_time'] - elapsed)
        try:
            for spec in v['check_specs']:
                timeout = min(spec.get('timeout_seconds', 30), remaining())
                if timeout <= 0:
                    checks.append({'id': spec['id'], 'status': 'not_run', 'required': spec.get('required', True), 'observation': 'wall-time budget exhausted'})
                    continue
                code, output, error = run_command(spec['argv'], '', timeout, cwd=initial['workspace'])
                checks.append({'id': spec['id'], 'status': 'passed' if code == 0 and not error else 'failed',
                               'required': spec.get('required', True), 'observation': output[:16000] or error or f'exit {code}',
                               'exit_code': code, 'error_code': error, 'argv': spec['argv']})
            _, after_checks = snapshot(initial['workspace'], v['artifact_paths'])
            if after_checks != digest:
                raise ValueError('artifacts changed during checks')
            if all(c['status'] == 'passed' for c in checks if c['required']):
                state = self.store.read()
                selection = select_reviewers(initial['task_signature'], initial['attempts'][-1]['worker'],
                                             state.get('reviewer_experiences', []), v['policy'], v['risk'])
                # No partial committee if the configured required roles cannot be covered.
                if not selection['missing_roles']:
                    for index, candidate in enumerate(selection['selected']):
                        reviewer = candidate['reviewer']; rid = f'{sid}:review:{index+1}'
                        def reserve(state):
                            task = resolve(state, task_id)
                            if task['status'] != initial['status'] or task['verification_layer']['sessions'][-1]['session_id'] != sid or task['verification_layer']['sessions'][-1]['status'] != 'RUNNING':
                                raise ValueError('task changed during review')
                            reserve_budget(task['verification_layer'], 'reviewer', rid, reviewer['max_cost_usd'], reviewer['max_tokens'])
                        self.store.transaction(reserve)
                        packet = build_blind_packet(initial, artifacts,
                            [{'name': c['id'], 'status': c['status'], 'summary': c['observation']} for c in checks],
                            candidate['role'], v['context'])
                        result = run_reviewer(reviewer, packet, timeout=min(reviewer['timeout_seconds'], remaining()))
                        review = {'reviewer_id': reviewer['reviewer_id'], 'model_id': reviewer['model_id'],
                                  'provider': reviewer['provider'], 'model_revision': reviewer.get('model_revision'),
                                  'role': candidate['role'], 'reliability': candidate['reliability'],
                                  'independence_score': candidate['independence_score'], 'reservation_id': rid, **result}
                        reviews.append(review)
                        def save_review(state):
                            task = resolve(state, task_id); layer = task['verification_layer']
                            session = next(s for s in layer['sessions'] if s['session_id'] == sid)
                            if session['status'] != 'RUNNING':
                                raise ValueError('verification session no longer running')
                            session['reviews'] = deepcopy(reviews)
                            reservation = next(r for r in layer['reservations'] if r['id'] == rid)
                            usage = result.get('usage') or {}
                            reservation['actual_cost'] = usage.get('cost_usd')
                            reservation['actual_tokens'] = usage.get('total_tokens')
                            event(state, 'INDEPENDENT_REVIEW_REPORTED', task, session_id=sid, reviewer_id=reviewer['reviewer_id'], role=candidate['role'], result_status=result['status'])
                        self.store.transaction(save_review)
                        usage = result.get('usage') or {}
                        if (usage.get('cost_usd') is not None and usage['cost_usd'] > reviewer['max_cost_usd']) or (usage.get('total_tokens') is not None and usage['total_tokens'] > reviewer['max_tokens']):
                            raise ValueError('reviewer exceeded declared resource ceiling')
            decision = judge(v['risk'], checks, reviews, selection, v['policy'],
                             worker_failure_rate=v['risk']['features']['worker_historical_failure_rate'])
        except Exception as exc:
            # External failures never turn into a pass, and cannot reset reservations.
            fatal = type(exc).__name__
            decision = {'status': 'ESCALATE', 'recommended_action': 'high_risk_uncertainty',
                        'reasons': ['verification interrupted or invalid; inspect checks and resource reservations'], 'error_code': fatal}
        def finish(state):
            task = resolve(state, task_id); layer = task['verification_layer']
            session = next(s for s in layer['sessions'] if s['session_id'] == sid)
            if session['status'] != 'RUNNING' or task['status'] != initial['status'] or task['worker_attempt_count'] != initial['worker_attempt_count']:
                raise ValueError('stale verification session cannot complete')
            try:
                _, current = snapshot(task['workspace'], layer['artifact_paths'])
            except (OSError, ValueError):
                current = None
            if current != digest or remaining() <= 0:
                decision.update(status='ESCALATE', recommended_action='high_risk_uncertainty', reasons=['artifacts changed or wall-time exhausted'])
            session.update(status='COMPLETE', checks=checks, reviews=reviews, selection=selection,
                           judge=decision, finished_at=_now(), duration_seconds=time.monotonic()-started)
            event(state, 'VERIFICATION_JUDGED', task, session_id=sid, decision=decision)
            return session
        return self.store.transaction(finish)

    def verification_approve(self, task_id, record):
        from routing.service import commander_only, resolve, require_text, event
        commander_only()
        if type(record.get('approved')) is not bool:
            raise ValueError('explicit human decision required')
        require_text(record.get('actor'), 'human actor')
        require_text(record.get('reason'), 'human approval reason')
        def apply(state):
            task = resolve(state, task_id); v = task.get('verification_layer')
            if not v or not v['sessions']:
                raise ValueError('verification session required')
            session = v['sessions'][-1]
            if record.get('session_id') != session['session_id'] or session['status'] != 'COMPLETE' or session['judge']['status'] != 'HUMAN_APPROVAL_REQUIRED':
                raise ValueError('approval must target the current critical verification session')
            _, digest = snapshot(task['workspace'], v['artifact_paths'])
            if digest != session['artifact_digest']:
                raise ValueError('cannot approve changed artifacts')
            session['human_approval'] = {**deepcopy(record), 'artifact_digest': digest, 'timestamp': _now(), 'authentication': 'operator_attested_not_authenticated'}
            event(state, 'HUMAN_VERIFICATION_DECISION', task, session_id=session['session_id'], approved=record['approved'], actor=record['actor'])
            return session
        return self.store.transaction(apply)

    def verification_recover(self, task_id, reason):
        from routing.service import commander_only, resolve, require_text, event
        commander_only(); require_text(reason, 'recovery reason')
        def apply(state):
            task = resolve(state, task_id); session = task['verification_layer']['sessions'][-1]
            if session['status'] != 'RUNNING':
                raise ValueError('only a running verification can be recovered')
            session.update(status='ABANDONED', recovery_reason=reason, finished_at=_now())
            event(state, 'VERIFICATION_ABANDONED', task, session_id=session['session_id'])
            return session
        return self.store.transaction(apply)

    def verification_feedback(self, task_id, feedback):
        from routing.service import commander_only, resolve, evidence_checked, require_text, event
        commander_only()
        def apply(state):
            task = resolve(state, task_id)
            if task['status'] not in ('ACCEPTED', 'TAKEOVER_REQUIRED', 'BLOCKED', 'RETRY_READY'):
                raise ValueError('Commander outcome required before reviewer feedback')
            record = next((r for r in state.get('reviewer_experiences', []) if r['experience_id'] == feedback.get('experience_id') and r['logical_task_id'] == task['logical_task_id']), None)
            if not record or type(feedback.get('correct')) is not bool:
                raise ValueError('matching reviewer experience and correctness required')
            if feedback.get('basis') not in ('deterministic', 'human', 'commander_artifact_review'):
                raise ValueError('feedback must be grounded, not reviewer agreement')
            evidence = evidence_checked(feedback.get('evidence'), task['workspace'])
            require_text(feedback.get('reason'), 'feedback rationale')
            require_text(feedback.get('actor'), 'feedback actor')
            if record.get('confirmed'):
                raise ValueError('feedback already confirmed; do not overwrite history')
            record.update(correct=feedback['correct'], confirmed=True, evidence=evidence,
                          basis=feedback['basis'], reason=feedback['reason'], adjudicator=feedback['actor'], adjudicated_at=_now())
            event(state, 'REVIEWER_EXPERIENCE_CONFIRMED', task, experience_id=record['experience_id'])
            return record
        return self.store.transaction(apply)


def record_verification_experience(state, task):
    """Descriptive reviewer history is NOT automatically ground truth."""
    v = task.get('verification_layer')
    if not v:
        return
    rows = state.setdefault('reviewer_experiences', [])
    existing = {r['experience_id'] for r in rows}
    for session in v['sessions']:
        if session['attempt_number'] != task['worker_attempt_count']:
            continue
        for index, review in enumerate(session['reviews']):
            identity = f"{session['session_id']}:experience:{index+1}"
            if identity in existing:
                continue
            rows.append({'experience_id': identity, 'logical_task_id': task['logical_task_id'],
                         'attempt_number': task['worker_attempt_count'], 'session_id': session['session_id'],
                         'timestamp': _now(), 'task_signature': deepcopy(task['task_signature']),
                         'risk_level': v['risk']['tier'], 'reviewer_id': review['reviewer_id'],
                         'model_id': review['model_id'], 'provider': review['provider'],
                         'model_revision': review.get('model_revision') or review.get('resolved_model'),
                         'resolved_model': review.get('resolved_model'),
                         'worker_model_id': task['attempts'][session['attempt_number']-1]['worker']['model'],
                         'role': review['role'], 'review': deepcopy(review),
                         'judge_result': deepcopy(session['judge']), 'deterministic_checks': deepcopy(session['checks']),
                         'human_override': deepcopy(session.get('human_approval')), 'final_outcome': task['final_status'],
                         'source_kind': task['source_kind'], 'valid': session['status'] == 'COMPLETE' and review['status'] == 'REPORTED' and not task['attempts'][session['attempt_number']-1].get('review', {}).get('invalid_task', False),
                         'confirmed': False, 'correct': None})
    for row in rows:
        if row['logical_task_id'] == task['logical_task_id']:
            row['final_outcome'] = task['final_status']
    if task['attempts']:
        exp = next((e for e in state['experiences'] if e['experience_id'] == task['attempts'][-1].get('experience_id')), None)
        if exp:
            exp['deliberation'] = {'risk': deepcopy(v['risk']), 'sessions': deepcopy(v['sessions']),
                                   'resources': deepcopy(v['reservations']), 'worker_revision_count': max(0, task['worker_attempt_count']-1),
                                   'final_outcome': task['final_status']}


def validate_verification_state(state, task):
    """Cross-check recorded gates, identities and reports; not proof of honesty."""
    from routing.verification_rules import validate_policy, assess_risk, judge
    from routing.reviewer_runtime import validate_review
    v = task.get('verification_layer')
    if v is None:
        return
    policy = validate_policy(v['policy'])
    if assess_risk(v['risk']['features'], policy) != v['risk']:
        raise ValueError('risk assessment inconsistent with frozen policy')
    if not isinstance(v['reservations'], list) or not isinstance(v['sessions'], list):
        raise ValueError('invalid verification collections')
    ids = set()
    for row in v['reservations']:
        if row['id'] in ids or row['kind'] not in ('worker','reviewer','verification'):
            raise ValueError('duplicate/invalid resource reservation')
        ids.add(row['id'])
        for key in ('cost_reserved','tokens_reserved'):
            _num(row[key], key)
        for key in ('actual_cost','actual_tokens'):
            if row.get(key) is not None: _num(row[key],key)
    if sum(r['cost_reserved'] for r in v['reservations']) > policy['budgets']['max_total_cost'] or sum(r['tokens_reserved'] for r in v['reservations']) > policy['budgets']['max_total_tokens']:
        raise ValueError('reservation ceiling violated')
    if sum(r['kind']=='reviewer' for r in v['reservations']) > policy['budgets']['max_reviewer_calls']:
        raise ValueError('reviewer call ceiling violated')
    seen = set(); counts = {}
    for s in v['sessions']:
        if s['session_id'] in seen or s['kind'] not in ('worker','takeover') or s['status'] not in ('RUNNING','COMPLETE','ABANDONED'):
            raise ValueError('invalid verification session identity/status')
        seen.add(s['session_id'])
        if type(s['attempt_number']) is not int or not 1 <= s['attempt_number'] <= task['worker_attempt_count']:
            raise ValueError('verification attempt identity mismatch')
        key=(s['attempt_number'],s['kind']);counts[key]=counts.get(key,0)+1
        if counts[key]>2: raise ValueError('verification session limit violated')
        manifest=s['artifacts']
        if [a['path'] for a in manifest] != v['artifact_paths']:
            raise ValueError('verification artifact scope mismatch')
        if hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()!=s['artifact_digest']:
            raise ValueError('artifact manifest digest mismatch')
        for review in s['reviews']:
            if review['reservation_id'] not in ids:
                raise ValueError('unreserved reviewer report')
            if review['status']=='REPORTED': validate_review(review['result'],review['role'])
            elif review['status']!='ERROR': raise ValueError('invalid reviewer report state')
        if s['status']=='COMPLETE':
            check_ids={c['id'] for c in s['checks']}
            expected={c['id'] for c in v['check_specs']}
            if not check_ids.issubset(expected): raise ValueError('unexpected deterministic check')
            if s['judge']['status'] in ('PASS','HUMAN_APPROVAL_REQUIRED'):
                if check_ids != expected or len(s['checks'])!=len(expected): raise ValueError('missing deterministic check')
                required={c['id']:c.get('required',True) for c in v['check_specs']}
                if any(c['required']!=required[c['id']] for c in s['checks']): raise ValueError('required check downgraded')
                replay=judge(v['risk'],s['checks'],s['reviews'],s['selection'],policy,worker_failure_rate=v['risk']['features']['worker_historical_failure_rate'])
                if replay['status']!=s['judge']['status']: raise ValueError('judge result inconsistent with evidence')
    if task['status']=='ACCEPTED':
        acceptance_gate(task,'takeover' if task.get('takeover') else 'worker')
    for row in state.get('reviewer_experiences',[]):
        if row['logical_task_id'] != task['logical_task_id']: continue
        session=next((s for s in v['sessions'] if s['session_id']==row['session_id']),None)
        if not session or row['attempt_number']!=session['attempt_number'] or row['source_kind']!=task['source_kind']:
            raise ValueError('reviewer experience lineage mismatch')
        if not any(r['reviewer_id']==row['reviewer_id'] and r['role']==row['role'] and r['model_id']==row['model_id'] for r in session['reviews']):
            raise ValueError('reviewer experience has no matching report')
        worker_model = task['attempts'][session['attempt_number']-1]['worker']['model']
        if row.get('worker_model_id') != worker_model or row.get('risk_level') != v['risk']['tier']:
            raise ValueError('reviewer experience Worker/risk identity mismatch')
        report = next(r for r in session['reviews'] if r['reviewer_id']==row['reviewer_id'] and r['role']==row['role'])
        if row.get('provider') != report.get('provider') or row.get('resolved_model') != report.get('resolved_model'):
            raise ValueError('reviewer experience provider identity mismatch')
        if row.get('confirmed') and (type(row.get('correct')) is not bool or not row.get('evidence') or row.get('basis') not in ('deterministic','human','commander_artifact_review')):
            raise ValueError('reviewer reliability feedback lacks adjudication')
