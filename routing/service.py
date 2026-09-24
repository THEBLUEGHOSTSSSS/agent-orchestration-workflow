"""Commander-controlled lifecycle: reserve -> execute once -> review -> learn."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from routing.models import MAX_WORKER_ATTEMPTS, load_config, validate_signature, validate_diagnosis
from routing.selection import route
from routing.store import Store, StateError

ROLE_ENV = 'ADAPTIVE_WORKER_ROLE'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be nonempty text')
    return value.strip()


def commander_only():
    if os.environ.get(ROLE_ENV) == 'worker':
        raise PermissionError('worker cannot create, route, dispatch, review or reset tasks')


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence_checked(refs, workspace):
    if not isinstance(refs, list) or not refs:
        raise ValueError('commander evidence references required')
    root = Path(workspace).resolve()
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError('invalid evidence reference')
        raw = require_text(ref.get('path'), 'evidence path')
        path = (root / raw).resolve()
        if Path(raw).is_absolute() or not path.is_relative_to(root) or not path.is_file():
            raise ValueError('evidence must be an existing file inside workspace')
        if digest_file(path) != ref.get('sha256'):
            raise ValueError('evidence hash mismatch')
    return deepcopy(refs)


def event(state, kind, task, **details):
    state['events'].append({'timestamp': stamp(), 'event': kind,
                            'logical_task_id': task['logical_task_id'],
                            'worker_attempt_count': task['worker_attempt_count'], **details})


def resolve(state, task_id):
    canonical = state['aliases'].get(task_id, task_id)
    if canonical not in state['tasks']:
        raise ValueError('unknown task')
    return state['tasks'][canonical]


class Workflow:
    def __init__(self, state_path, config_path=None):
        self.store = Store(state_path)
        self.config = load_config(config_path)

    def create(self, spec):
        commander_only()
        task_id = require_text(spec.get('task_id'), 'task_id')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', task_id):
            raise ValueError('task_id must be a short portable identifier')
        workspace = str(Path(require_text(spec.get('workspace'), 'workspace')).resolve(strict=True))
        if not Path(workspace).is_dir():
            raise ValueError('workspace must be a directory')
        objective = require_text(spec.get('objective'), 'objective')
        baseline = require_text(spec.get('baseline'), 'baseline')
        key = ' '.join(require_text(spec.get('work_key'), 'stable work_key').lower().split())
        scope = spec.get('scope')
        if not isinstance(scope, list) or not scope:
            raise ValueError('nonempty allowed file scope required')
        for name in scope:
            path = Path(require_text(name, 'scope path'))
            if path.is_absolute() or '..' in path.parts or path.parts[0] == '.git':
                raise ValueError('scope must stay in project; .git is reserved')
        criteria = spec.get('acceptance_criteria')
        if not isinstance(criteria, list) or not criteria:
            raise ValueError('acceptance criteria required')
        ids = []
        for criterion in criteria:
            ids.append(require_text(criterion.get('id'), 'criterion id'))
            require_text(criterion.get('check'), 'criterion check')
        if len(set(ids)) != len(ids):
            raise ValueError('criterion ids must be unique')
        signature = validate_signature(spec.get('task_signature'))
        source = spec.get('source_kind', 'real')
        if source not in ('real', 'probe', 'synthetic'):
            raise ValueError('source_kind must be real, probe or synthetic')
        fingerprint = hashlib.sha256((workspace + '\n' + key).encode()).hexdigest()

        def create(state):
            parent = spec.get('parent_task_id') or spec.get('logical_task_id')
            existing = state['aliases'].get(task_id) or state['work_keys'].get(fingerprint)
            if parent and not (parent == task_id and parent not in state['aliases']):
                inherited = resolve(state, parent)
                if inherited['workspace'] != workspace:
                    raise ValueError('aliases cannot change workspace')
                if existing and existing != inherited['logical_task_id']:
                    raise ValueError('conflicting lineage')
                existing = inherited['logical_task_id']
            if existing:
                state['aliases'][task_id] = existing
                state['work_keys'][fingerprint] = existing
                event(state, 'ALIAS_BOUND', state['tasks'][existing], alias=task_id)
                return state['tasks'][existing]
            task = {'logical_task_id': task_id, 'task_id': task_id, 'work_key': key,
                    'workspace': workspace, 'baseline': baseline, 'objective': objective,
                    'scope': scope, 'acceptance_criteria': criteria, 'task_signature': signature,
                    'repo_context': deepcopy(spec.get('repo_context', {})),
                    'original_plan': spec.get('original_plan', objective),
                    'new_scope_rationale': spec.get('new_scope_rationale'),
                    'source_kind': source, 'created_at': stamp(), 'status': 'READY',
                    'worker_attempt_count': 0, 'attempts': [], 'final_status': 'pending'}
            state['tasks'][task_id] = task
            state['aliases'][task_id] = task_id
            state['work_keys'][fingerprint] = task_id
            event(state, 'TASK_CREATED', task)
            return task
        return self.store.transaction(create)

    def _decision(self, state, task, manual_worker=None):
        previous = task['attempts'][-1] if task['attempts'] else None
        return route(task['task_signature'], state['experiences'], self.config,
                     previous_worker=previous['worker']['worker_id'] if previous else None,
                     diagnosis=previous.get('review', {}).get('diagnosis') if previous else None,
                     manual_worker=manual_worker)

    def preview(self, task_id, manual_worker=None):
        commander_only()
        state = self.store.read()
        task = resolve(state, task_id)
        self._ready(task)
        return self._decision(state, task, manual_worker)

    @staticmethod
    def _ready(task):
        if task['worker_attempt_count'] >= MAX_WORKER_ATTEMPTS:
            raise ValueError('two worker attempts exhausted; strong commander takeover only')
        if task['status'] not in ('READY', 'RETRY_READY'):
            raise ValueError('task must be ready or reviewed and explicitly approved for retry')

    def handoff(self, task):
        previous = task['attempts'][-1]
        review = previous['review']
        supplied = review.get('handoff', {})
        keys = ('files_inspected', 'files_modified', 'current_diff', 'tests_run', 'test_results',
                'previous_approach', 'what_worked', 'what_failed', 'known_bad_approaches',
                'remaining_work', 'constraints')
        if any(key not in supplied for key in keys):
            raise ValueError('attempt 2 requires full commander handoff package')
        return {'logical_task_id': task['logical_task_id'], 'attempt_number': 2,
                'max_attempts': MAX_WORKER_ATTEMPTS, 'objective': task['objective'],
                'scope': task['scope'], 'acceptance_criteria': task['acceptance_criteria'],
                'original_plan': task['original_plan'], 'repo_context': task['repo_context'],
                'previous_worker': previous['worker'], 'failure_diagnosis': review['diagnosis'],
                **{key: deepcopy(supplied[key]) for key in keys}, 'notice': 'THIS IS WORKER ATTEMPT 2 OF 2.'}

    def reserve(self, task_id, manual_worker=None):
        commander_only()
        def reserve(state):
            task = resolve(state, task_id)
            self._ready(task)
            decision = self._decision(state, task, manual_worker)
            worker = next(w for w in self.config['workers'] if w['worker_id'] == decision['selected_worker'])
            handoff = self.handoff(task) if task['attempts'] else None
            number = task['worker_attempt_count'] + 1
            attempt = {'logical_task_id': task['logical_task_id'], 'attempt_number': number,
                       'worker': deepcopy(worker), 'routing': decision, 'started_at': stamp(),
                       'status': 'RUNNING', 'handoff': handoff, 'review': None}
            task['attempts'].append(attempt)
            task['worker_attempt_count'] = number
            task['status'] = 'RUNNING'
            if number == 2:
                previous = task['attempts'][0]
                for exp in state['experiences']:
                    if exp['experience_id'] == previous.get('experience_id'):
                        exp['retry'].update(next_worker=worker['worker_id'],
                                            action='SAME_WORKER' if previous['worker']['worker_id'] == worker['worker_id'] else 'DIFFERENT_WORKER')
            event(state, 'ATTEMPT_RESERVED', task, attempt_number=number, routing=decision)
            return {'task': task, 'attempt': attempt}
        return self.store.transaction(reserve)

    def _finish(self, task_id, number, execution):
        def finish(state):
            task = resolve(state, task_id)
            attempt = task['attempts'][number - 1]
            if task['status'] != 'RUNNING' or attempt['status'] != 'RUNNING':
                raise ValueError('attempt is not running; cannot rewrite execution')
            attempt.update(status='REPORTED', execution=deepcopy(execution), finished_at=stamp())
            task['status'] = 'AWAITING_REVIEW'
            experience_id = f"{task['logical_task_id']}:{number}"
            attempt['experience_id'] = experience_id
            experience = {'experience_id': experience_id, 'timestamp': stamp(),
                          'logical_task_id': task['logical_task_id'], 'attempt_number': number,
                          'task_signature': task['task_signature'], 'worker': attempt['worker'],
                          'routing': attempt['routing'], 'execution': execution,
                          'verification': {'reviewer_result': 'pending', 'reviewer': None},
                          'outcome': {'accepted': False, 'worker_result_status': 'UNREVIEWED', 'final_quality': None},
                          'diagnosis': {'attribution': 'UNKNOWN', 'failure_type': 'UNKNOWN', 'severity': 'none', 'summary': 'Awaiting commander review'},
                          'retry': {'required': False, 'next_worker': None, 'previous_worker': attempt['worker']['worker_id'], 'action': None},
                          'repair': {'required': False, 'scope': None, 'severity': 'none', 'burden': None, 'takeover': False},
                          'source_kind': task['source_kind'], 'valid': True}
            state['experiences'].append(deepcopy(experience))
            event(state, 'EXECUTION_REPORTED', task, attempt_number=number,
                  exit_code=execution.get('exit_code'), experience_id=experience_id)
            return task
        return self.store.transaction(finish)

    def run(self, task_id, manual_worker=None, timeout=None, executor=None):
        commander_only()
        timeout = timeout if timeout is not None else self.config.get('execution_timeout_seconds', 300)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('positive bounded execution timeout required')
        reservation = self.reserve(task_id, manual_worker)
        task, attempt = reservation['task'], reservation['attempt']
        if executor is not None and task['source_kind'] == 'real':
            # A test executor must never write evidence that looks like a real model call.
            execution = {'exit_code': None, 'error': 'test executor refused for real task', 'invalid': True,
                         'duration_seconds': 0, 'token_usage': None, 'estimated_cost': None,
                         'currency': None, 'tool_calls': None}
        else:
            start = time.monotonic()
            try:
                execution = executor(task, attempt) if executor else self._execute(task, attempt, timeout)
                if not isinstance(execution, dict):
                    raise ValueError('execution result must be an object')
            except Exception as exc:
                execution = {'exit_code': None, 'error': f'{type(exc).__name__}: {exc}'}
            execution.setdefault('duration_seconds', time.monotonic() - start)
            for field in ('token_usage', 'estimated_cost', 'currency', 'tool_calls'):
                execution.setdefault(field, None)
        return self._finish(task_id, attempt['attempt_number'], execution)

    def _execute(self, task, attempt, timeout):
        worker = attempt['worker']
        adapter = worker['adapter']
        command = list(adapter['command'])
        if adapter['kind'] == 'codex_worker':
            command += [task['workspace'], '--model', worker['model'], '--reasoning-effort', worker['reasoning_effort']]
        elif adapter['kind'] == 'command':
            command = [part.replace('{workspace}', task['workspace']).replace('{model}', worker['model']).replace('{reasoning_effort}', worker['reasoning_effort']) for part in command]
        else:
            raise ValueError('unsupported adapter kind')
        directory = self.store.path.parent / 'runs' / task['logical_task_id'] / str(attempt['attempt_number'])
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        prompt = {'role': 'bounded execution worker; no delegation, scope expansion or configuration changes',
                  'logical_task_id': task['logical_task_id'], 'baseline': task['baseline'],
                  'attempt_number': attempt['attempt_number'], 'max_attempts': MAX_WORKER_ATTEMPTS,
                  'objective': task['objective'], 'scope': task['scope'],
                  'acceptance_criteria': task['acceptance_criteria'], 'repo_context': task['repo_context'],
                  'plan': task['original_plan'], 'stop_after_seconds': timeout,
                  'handoff': attempt['handoff'],
                  'output': 'Complete bounded implementation and checks; report artifacts, actual checks, blockers. Commander alone accepts.'}
        payload = json.dumps(prompt, ensure_ascii=False, indent=2)
        (directory / 'prompt.json').write_text(payload)
        env = dict(os.environ)
        env[ROLE_ENV] = 'worker'
        env['ADAPTIVE_LOGICAL_TASK_ID'] = task['logical_task_id']
        env['ADAPTIVE_ATTEMPT_NUMBER'] = str(attempt['attempt_number'])
        started = time.monotonic()
        with (directory / 'output.log').open('w') as output:
            proc = subprocess.Popen(command, cwd=task['workspace'], env=env, stdin=subprocess.PIPE,
                                    stdout=output, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            try:
                proc.communicate(payload, timeout=timeout)
                code, error = proc.returncode, None
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                # The leader may exit while a descendant ignores TERM.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                code, error = proc.returncode, 'timeout; commander must diagnose attribution'
        return {'exit_code': code, 'error': error, 'duration_seconds': time.monotonic() - started,
                'log_path': str(directory / 'output.log'), 'log_sha256': digest_file(directory / 'output.log'),
                'selected_model': worker['model'], 'reasoning_effort': worker['reasoning_effort']}

    def review(self, task_id, review):
        commander_only()
        reviewer = require_text(review.get('reviewer'), 'strong commander reviewer')
        accepted = review.get('accepted')
        if type(accepted) is not bool:
            raise ValueError('accepted must be boolean')
        diagnosis = validate_diagnosis(review.get('diagnosis'), accepted)
        if type(review.get('invalid_task', False)) is not bool:
            raise ValueError('invalid_task must be boolean')
        if review.get('invalid_task'):
            require_text(review.get('invalid_reason'), 'invalid reason')
        quality = review.get('final_quality')
        if quality is not None and (type(quality) not in (int, float) or not math.isfinite(quality) or not 0 <= quality <= 1):
            raise ValueError('final_quality must be null or between zero and one')
        action = review.get('action')
        if action not in ('accept', 'retry', 'takeover', 'blocked') or accepted != (action == 'accept'):
            raise ValueError('review action contradicts acceptance')

        def apply(state):
            task = resolve(state, task_id)
            if task['status'] != 'AWAITING_REVIEW':
                raise ValueError('review requires reported execution; cannot overwrite review')
            evidence = evidence_checked(review.get('evidence'), task['workspace'])
            checks = review.get('criteria', [])
            expected = {c['id'] for c in task['acceptance_criteria']}
            if not isinstance(checks, list) or len(checks) != len(expected) or {c.get('id') for c in checks} != expected:
                raise ValueError('review must account for every original criterion')
            for check in checks:
                if check.get('status') not in ('passed', 'failed', 'not_run'):
                    raise ValueError('invalid criterion status')
                require_text(check.get('observation'), 'criterion observation')
            if accepted and (any(c['status'] != 'passed' for c in checks)
                             or review.get('static_checker_result') not in ('passed', 'not_applicable')):
                raise ValueError('cannot accept without complete verification')
            if action == 'retry' and task['worker_attempt_count'] >= MAX_WORKER_ATTEMPTS:
                raise ValueError('attempt 2 failure requires takeover; no retry permitted')
            if action == 'retry':
                draft = deepcopy(task)
                draft['attempts'][-1]['review'] = review
                self.handoff(draft)
            attempt = task['attempts'][-1]
            repair = deepcopy(review.get('repair', {'required': False, 'scope': None, 'severity': 'none', 'burden': None, 'takeover': False}))
            if repair.get('severity') not in ('none', 'low', 'medium', 'high'):
                raise ValueError('repair severity invalid')
            burden = repair.get('burden')
            if burden is not None and (type(burden) not in (int, float) or not math.isfinite(burden) or burden < 0):
                raise ValueError('repair burden must be nonnegative or null')
            if type(repair.get('required')) is not bool:
                raise ValueError('repair.required must be boolean')
            repair['takeover'] = action == 'takeover' or (not accepted and task['worker_attempt_count'] == 2)
            if accepted:
                status = ('ACCEPTED_AFTER_MAJOR_REVISION' if repair.get('severity') == 'high'
                          else 'ACCEPTED_WITH_MINOR_REVIEW' if repair.get('required')
                          else 'FIRST_PASS_ACCEPTED' if task['worker_attempt_count'] == 1
                          else 'SECOND_PASS_ACCEPTED')
                task.update(status='ACCEPTED', final_status='accepted')
            else:
                status = 'STRONG_MODEL_TAKEOVER_REQUIRED' if repair['takeover'] else 'FAILED'
                task['status'] = 'TAKEOVER_REQUIRED' if repair['takeover'] else 'RETRY_READY' if action == 'retry' else 'BLOCKED'
                task['final_status'] = 'pending' if action == 'retry' else 'blocked'
            frozen = deepcopy(review)
            frozen.update(diagnosis=diagnosis, evidence=evidence, reviewed_at=stamp(), reviewer=reviewer)
            attempt.update(status='REVIEWED', review=frozen)
            exp = next(e for e in state['experiences'] if e['experience_id'] == attempt['experience_id'])
            metrics = review.get('execution_metrics', {})
            if metrics:
                require_text(metrics.get('source'), 'usage/cost evidence source')
                for field in ('estimated_cost', 'duration_seconds', 'tool_calls'):
                    value = metrics.get(field)
                    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                        raise ValueError('invalid execution metric')
                if metrics.get('estimated_cost') is not None:
                    require_text(metrics.get('currency'), 'cost currency')
                for field in ('estimated_cost', 'currency', 'token_usage', 'tool_calls', 'source'):
                    if field in metrics:
                        exp['execution'][field] = deepcopy(metrics[field])
                        attempt['execution'][field] = deepcopy(metrics[field])
            exp.update(verification={'tests_run': checks, 'tests_passed': [c['id'] for c in checks if c['status'] == 'passed'],
                                     'static_checker_result': review.get('static_checker_result', 'not_run'),
                                     'reviewer_result': 'accepted' if accepted else 'rejected', 'reviewer': reviewer, 'evidence': evidence},
                       outcome={'accepted': accepted, 'final_quality': review.get('final_quality'), 'worker_result_status': status},
                       diagnosis=diagnosis, repair=repair,
                       valid=not review.get('invalid_task', False), invalid_reason=review.get('invalid_reason'))
            exp['retry'].update(required=action == 'retry', action=action.upper(), next_worker=None)
            event(state, 'COMMANDER_REVIEW', task, attempt_number=attempt['attempt_number'],
                  reviewer=reviewer, outcome=status, attribution=diagnosis['attribution'], action=action)
            return task
        return self.store.transaction(apply)

    def takeover(self, task_id, record):
        commander_only()
        require_text(record.get('reviewer'), 'reviewer')
        require_text(record.get('summary'), 'commander repair summary')
        def complete(state):
            task = resolve(state, task_id)
            if task['status'] not in ('TAKEOVER_REQUIRED', 'BLOCKED', 'RETRY_READY'):
                raise ValueError('task not available for commander takeover')
            evidence_checked(record.get('evidence'), task['workspace'])
            checks = record.get('criteria', [])
            expected = {c['id'] for c in task['acceptance_criteria']}
            if len(checks) != len(expected) or {c.get('id') for c in checks} != expected or any(c.get('status') != 'passed' for c in checks):
                raise ValueError('takeover must verify all original criteria')
            for check in checks:
                require_text(check.get('observation'), 'takeover criterion observation')
            if record.get('static_checker_result') not in ('passed', 'not_applicable'):
                raise ValueError('takeover requires checker disposition')
            burden = record.get('repair_burden')
            if type(burden) not in (int, float) or not math.isfinite(burden) or burden < 0:
                raise ValueError('nonnegative commander repair burden required')
            task.update(status='ACCEPTED', final_status='accepted_after_takeover', takeover=deepcopy(record))
            for exp in state['experiences']:
                if exp['logical_task_id'] == task['logical_task_id']:
                    exp['outcome']['task_final_status'] = 'accepted_after_takeover'
                    exp['repair']['task_takeover'] = True
            exp = next(e for e in state['experiences'] if e['experience_id'] == task['attempts'][-1]['experience_id'])
            exp['repair'].update(required=True, takeover=True, burden=burden, scope=record['summary'])
            exp['outcome']['worker_result_status'] = 'STRONG_MODEL_TAKEOVER_REQUIRED'
            # Worker acceptance stays false: commander success must never become worker credit.
            event(state, 'COMMANDER_TAKEOVER_VALIDATED', task, reviewer=record['reviewer'], repair_burden=burden)
            return task
        return self.store.transaction(complete)

    def recover(self, task_id, reason):
        commander_only()
        require_text(reason, 'interruption reason')
        task = self.inspect(task_id)
        if task['status'] != 'RUNNING':
            raise ValueError('only a running/uncertain attempt can be recovered')
        # Caller must stop/verify the old process; this operation never starts a replacement.
        return self._finish(task_id, task['worker_attempt_count'],
                            {'exit_code': None, 'error': reason, 'duration_seconds': None,
                             'token_usage': None, 'estimated_cost': None, 'currency': None, 'tool_calls': None})

    def inspect(self, task_id=None):
        state = self.store.read()
        return deepcopy(resolve(state, task_id)) if task_id else state
