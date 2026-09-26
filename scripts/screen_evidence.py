"""Optional commander-only Jev screening; defaults OFF and never updates a ledger.

Exit 0: DISABLED or SCREENED (neither means accepted).
Exit 2: UNKNOWN (including invalid local input) or REFUSED worker-role invocation.
SHADOW and ASSIST both preserve every item and require human/commander review;
ASSIST permits using the advisory answers to prioritize that review only.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routing.jev import MODES, commander_only, read_packet, screen_evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=MODES, default='OFF')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        commander_only()
    except PermissionError:
        print('{"status":"REFUSED","error_code":"commander_only"}', file=sys.stderr)
        return 2
    try:
        packet = read_packet(args.input)
        # Reserve a fresh result before a paid call; never truncate evidence,
        # existing output, a symlink or a hardlink, even if paths differ.
        with args.output.open('x') as stream:
            os.fchmod(stream.fileno(), 0o600)
            result = screen_evidence(packet, args.mode)
            stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        print('{"status":"UNKNOWN","error_code":"input_or_output_error","commander_review_required":true}', file=sys.stderr)
        return 2
    print(json.dumps({'status': result['status'], 'commander_review_required': True}))
    return 2 if result['status'] == 'UNKNOWN' else 0


if __name__ == '__main__':
    raise SystemExit(main())
