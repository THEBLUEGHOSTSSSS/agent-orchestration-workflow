"""Check a completed review ledger. No execution, authorization or semantic proof."""
import argparse
import hashlib
import json
from pathlib import Path


def validate(record, root):
    """Return errors; only a complete, internally consistent ledger may pass."""
    errors = []
    root = Path(root).resolve()

    def require(condition, message):
        if not condition:
            errors.append(message)

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    def file_ref(ref, label):
        if not isinstance(ref, dict) or not text(ref.get('path')):
            errors.append(label + ': missing file reference')
            return
        path = (root / ref['path']).resolve()
        if Path(ref['path']).is_absolute() or not path.is_relative_to(root):
            errors.append(label + ': path must stay inside root')
            return
        if not path.is_file():
            errors.append(label + ': file missing')
            return
        require(hashlib.sha256(path.read_bytes()).hexdigest() == ref.get('sha256'),
                label + ': hash mismatch')

    if not isinstance(record, dict):
        return ['record must be an object']
    for field in ('task_id', 'baseline', 'commander'):
        require(text(record.get(field)), field + ' required')
    require(record.get('status') == 'accepted', 'commander acceptance required')
    require(record.get('unresolved') == [], 'unresolved must be an empty list')
    attempts = record.get('worker_attempts')
    if not isinstance(attempts, list):
        errors.append('worker_attempts must be a list')
        attempts = []
    require(len(attempts) <= 2, 'maximum two worker attempts')
    decisions = []
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict):
            errors.append('attempt must be an object')
            continue
        require(type(attempt.get('number')) is int and attempt['number'] == index,
                'attempts must be consecutive from 1')
        decision = attempt.get('decision')
        decisions.append(decision)
        require(decision in ('accept', 'rework', 'takeover', 'blocked'), 'invalid decision')
        require(decision != 'rework' or index == 1, 'only attempt 1 permits rework')
        require(text(attempt.get('review')), 'commander review required for each attempt')
        file_ref(attempt.get('evidence'), 'attempt evidence')
    if len(attempts) == 2:
        require(decisions[:1] == ['rework'], 'second attempt requires the single rework decision')
    if decisions:
        require(decisions[-1] != 'rework', 'outstanding rework cannot be accepted')
    needs_repair = bool(decisions and decisions[-1] != 'accept')
    repair = record.get('commander_repair')
    if needs_repair or repair is not None:
        require(isinstance(repair, dict), 'commander repair required after failed final attempt')
        if isinstance(repair, dict):
            require(text(repair.get('summary')), 'repair summary required')
            file_ref(repair.get('evidence'), 'commander repair evidence')
    criteria = record.get('criteria')
    require(isinstance(criteria, list) and bool(criteria), 'acceptance criteria required')
    ids = set()
    for criterion in criteria if isinstance(criteria, list) else []:
        if not isinstance(criterion, dict):
            errors.append('criterion must be an object')
            continue
        cid = criterion.get('id')
        require(text(cid), 'criterion id required')
        if text(cid):
            require(cid not in ids, 'duplicate criterion id')
            ids.add(cid)
        require(criterion.get('status') == 'verified', 'every required criterion must be verified')
        require(text(criterion.get('check')), 'actual check description required')
        file_ref(criterion.get('evidence'), 'criterion evidence')
    artifacts = record.get('artifacts')
    require(isinstance(artifacts, list) and bool(artifacts), 'artifact references required')
    for ref in artifacts if isinstance(artifacts, list) else []:
        file_ref(ref, 'artifact')
    file_ref(record.get('experience'), 'mandatory experience')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.record.read_text()), args.root)
    except (OSError, ValueError, RuntimeError) as exc:
        errors = [str(exc)]
    if errors:
        print('NOT ACCEPTED:\n' + '\n'.join('- ' + error for error in errors))
        return 1
    print('PASS: static review ledger consistent; semantic acceptance remains commander responsibility')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
