"""Static cross-checks, not authenticity or sandbox guarantees."""
from routing.models import MAX_WORKER_ATTEMPTS, validate_signature, validate_diagnosis
from routing.store import check_state


def _checks(task, record, accepted):
    expected = {c['id'] for c in task['acceptance_criteria']}
    checks = record.get('criteria', [])
    if not isinstance(checks, list) or len(checks) != len(expected) or {c['id'] for c in checks} != expected:
        raise ValueError('original acceptance criteria mismatch')
    if any(c.get('status') not in ('passed', 'failed', 'not_run') or not isinstance(c.get('observation'), str) or not c['observation'].strip() for c in checks):
        raise ValueError('invalid check evidence')
    if accepted and (any(c['status'] != 'passed' for c in checks) or record.get('static_checker_result') not in ('passed', 'not_applicable')):
        raise ValueError('accepted work requires all checks passed')


def validate_ledger(state):
    errors = []
    try:
        check_state(state)
        experiences = {e['experience_id']: e for e in state['experiences']}
        linked = set()
        for task in state['tasks'].values():
            validate_signature(task['task_signature'])
            for attempt in task['attempts']:
                number = attempt['attempt_number']
                decision = attempt['routing']
                required = ('selected_worker', 'reasoning_effort', 'selection_mode', 'routing_reason',
                            'historical_sample_count', 'historical_confidence', 'alternative_worker')
                if any(k not in decision for k in required): raise ValueError('routing fields missing')
                if decision['selected_worker'] != attempt['worker']['worker_id'] or decision['reasoning_effort'] != attempt['worker']['reasoning_effort']:
                    raise ValueError('routing/actual worker mismatch')
                if number == 2:
                    h = attempt.get('handoff') or {}
                    if h.get('logical_task_id') != task['logical_task_id'] or h.get('attempt_number') != 2 or h.get('max_attempts') != MAX_WORKER_ATTEMPTS:
                        raise ValueError('switch/reset handoff violation')
                if attempt['status'] == 'RUNNING':
                    if task['status'] != 'RUNNING': raise ValueError('inconsistent running state')
                    continue
                exp = experiences.get(attempt.get('experience_id'))
                if not exp: raise ValueError('execution experience missing')
                linked.add(exp['experience_id'])
                if exp['logical_task_id'] != task['logical_task_id'] or exp['attempt_number'] != number:
                    raise ValueError('experience identity mismatch')
                if exp['worker'] != attempt['worker'] or exp['source_kind'] != task['source_kind'] or exp['execution'] != attempt['execution']:
                    raise ValueError('experience source/worker/execution mismatch')
                validate_signature(exp['task_signature'])
                if exp['task_signature'] != task['task_signature']: raise ValueError('experience signature mismatch')
                if attempt['status'] == 'REVIEWED':
                    review = attempt['review']
                    validate_diagnosis(exp['diagnosis'], exp['outcome']['accepted'])
                    _checks(task, review, review['accepted'])
                    if exp['outcome']['accepted'] != review['accepted'] or exp['diagnosis'] != review['diagnosis']:
                        raise ValueError('experience/review decision mismatch')
                    v = exp['verification']
                    if v.get('reviewer_result') != ('accepted' if review['accepted'] else 'rejected') or v.get('reviewer') != review['reviewer']:
                        raise ValueError('missing or inconsistent experience reviewer')
                    if not v.get('evidence') or v['evidence'] != review['evidence'] or v.get('tests_run') != review['criteria']:
                        raise ValueError('review evidence inconsistent')
                    if number == MAX_WORKER_ATTEMPTS and not review['accepted']:
                        if task['status'] not in ('TAKEOVER_REQUIRED', 'ACCEPTED') or review['action'] == 'retry':
                            raise ValueError('attempt 2 failure requires takeover')
            if task['status'] == 'ACCEPTED':
                from routing.service import evidence_checked
                if task.get('takeover'):
                    final = task['takeover']
                    if task['final_status'] != 'accepted_after_takeover': raise ValueError('takeover status mismatch')
                else:
                    final = task['attempts'][-1]['review']
                    if not final['accepted']: raise ValueError('acceptance requires commander review')
                _checks(task, final, True)
                evidence_checked(final['evidence'], task['workspace'])
        if linked != set(experiences): raise ValueError('orphan experience records')
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OSError) as exc:
        errors.append(f'invalid routing ledger: {exc}')
    return errors
