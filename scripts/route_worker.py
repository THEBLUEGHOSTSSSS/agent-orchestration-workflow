"""Explicit commander CLI for adaptive worker routing. No daemon or auto-review."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routing.service import Workflow, commander_only
from routing.models import profile_task
from routing.jev import read_packet


def read_json(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path.cwd() / '.work/worker-routing/state.json')
    parser.add_argument('--config', type=Path)
    sub = parser.add_subparsers(dest='operation', required=True)
    p = sub.add_parser('profile'); p.add_argument('signature'); p.add_argument('--repo-context')
    p = sub.add_parser('create'); p.add_argument('spec')
    for name in ('route', 'run'):
        p = sub.add_parser(name); p.add_argument('task_id'); p.add_argument('--worker')
        if name == 'run': p.add_argument('--timeout', type=float)
    for name in ('review', 'takeover'):
        p = sub.add_parser(name); p.add_argument('task_id'); p.add_argument('record')
    p = sub.add_parser('recover'); p.add_argument('task_id'); p.add_argument('--reason', required=True)
    p = sub.add_parser('inspect'); p.add_argument('task_id', nargs='?')
    p = sub.add_parser('screen'); p.add_argument('task_id'); p.add_argument('packet')
    p.add_argument('--mode', choices=('OFF', 'SHADOW', 'ASSIST'), default='OFF')
    p = sub.add_parser('verify'); p.add_argument('task_id'); p.add_argument('--kind', choices=('worker', 'takeover'), default='worker')
    for name in ('verification-approve', 'verification-feedback'):
        p = sub.add_parser(name); p.add_argument('task_id'); p.add_argument('record')
    p = sub.add_parser('verification-recover'); p.add_argument('task_id'); p.add_argument('--reason', required=True)
    sub.add_parser('validate')
    args = parser.parse_args()
    try:
        commander_only()
        if args.operation == 'profile':
            result = profile_task(read_json(args.signature), read_json(args.repo_context) if args.repo_context else None)
        else:
            workflow = Workflow(args.state, args.config)
            if args.operation == 'create': result = workflow.create(read_json(args.spec))
            elif args.operation == 'route': result = workflow.preview(args.task_id, args.worker)
            elif args.operation == 'run': result = workflow.run(args.task_id, args.worker, args.timeout)
            elif args.operation == 'screen': result = workflow.screen(args.task_id, read_packet(args.packet), args.mode)
            elif args.operation == 'verify': result = workflow.verify(args.task_id, args.kind)
            elif args.operation == 'verification-approve': result = workflow.verification_approve(args.task_id, read_json(args.record))
            elif args.operation == 'verification-feedback': result = workflow.verification_feedback(args.task_id, read_json(args.record))
            elif args.operation == 'verification-recover': result = workflow.verification_recover(args.task_id, args.reason)
            elif args.operation == 'review': result = workflow.review(args.task_id, read_json(args.record))
            elif args.operation == 'takeover': result = workflow.takeover(args.task_id, read_json(args.record))
            elif args.operation == 'recover': result = workflow.recover(args.task_id, args.reason)
            elif args.operation == 'inspect': result = workflow.inspect(args.task_id)
            else:
                from routing.validation import validate_ledger
                errors = validate_ledger(workflow.inspect())
                if errors: raise ValueError('; '.join(errors))
                result = {'status': 'STATIC_CHECKED', 'semantic_review': 'commander responsibility'}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if args.operation == 'screen' and result['status'] == 'UNKNOWN' else 0
    except (OSError, ValueError, KeyError, TypeError, PermissionError, RecursionError) as exc:
        print(json.dumps({'error': str(exc), 'status': 'REFUSED'}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
