"""One project-local, atomic JSON ledger. POSIX; no network/database service."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import tempfile


class StateError(ValueError):
    pass


def empty_state():
    return {'schema_version': 1, 'revision': 0, 'tasks': {}, 'aliases': {},
            'work_keys': {}, 'experiences': [], 'events': []}


def check_state(state):
    from routing.models import MAX_WORKER_ATTEMPTS
    if not isinstance(state, dict) or state.get('schema_version') != 1:
        raise StateError('unsupported or corrupted ledger; never reset automatically')
    if type(state.get('revision')) is not int or state['revision'] < 0:
        raise StateError('invalid revision')
    for field in ('tasks', 'aliases', 'work_keys'):
        if not isinstance(state.get(field), dict):
            raise StateError(f'invalid {field}')
    for field in ('experiences', 'events'):
        if not isinstance(state.get(field), list):
            raise StateError(f'invalid {field}')
    for key, task in state['tasks'].items():
        attempts = task.get('attempts', [])
        if (type(task.get('worker_attempt_count')) is not int or task.get('logical_task_id') != key or not isinstance(attempts, list)
                or len(attempts) > MAX_WORKER_ATTEMPTS
                or task.get('worker_attempt_count') != len(attempts)):
            raise StateError('task identity or attempt invariant violated')
        for number, attempt in enumerate(attempts, 1):
            if (type(attempt.get('attempt_number')) is not int
                    or attempt['attempt_number'] != number
                    or attempt.get('logical_task_id') != key):
                raise StateError('attempt lineage invalid')
    for target in list(state['aliases'].values()) + list(state['work_keys'].values()):
        if target not in state['tasks']:
            raise StateError('dangling task identity')
    ids = [e.get('experience_id') for e in state['experiences']]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise StateError('invalid or duplicate experience id')
    return state


class Store:
    def __init__(self, path):
        self.path = Path(path).absolute()
        self.lock = self.path.with_suffix(self.path.suffix + '.lock')

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink() or self.lock.is_symlink():
            raise StateError('ledger and lock must not be symlinks')
        fd = os.open(self.lock, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _load(self):
        if not self.path.exists():
            return empty_state()
        try:
            state = json.loads(self.path.read_text(), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
            return check_state(state)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise StateError(f'ledger invalid; manual investigation required: {exc}') from exc

    def read(self):
        with self._locked():
            return deepcopy(self._load())

    def transaction(self, mutator):
        with self._locked():
            state = self._load()
            result = mutator(state)
            check_state(state)
            state['revision'] += 1
            content = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
            fd, name = tempfile.mkstemp(prefix='.ledger-', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w') as file:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(name, self.path)
                directory = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            return deepcopy(result)
