"""Build trusted runner argv without assuming a model vendor or using a shell."""
import json

KINDS = ('command', 'codex_cli', 'claude_code', 'codex_worker')


def build_command(worker, workspace):
    adapter = worker['adapter']
    command = list(adapter['command'])
    model, effort = worker['model'], worker['reasoning_effort']
    if adapter['kind'] == 'command':
        values = {'workspace': workspace, 'model': model, 'reasoning_effort': effort}
        # Single pass: replacement values cannot introduce additional placeholders.
        import re
        return [re.sub(r'\{(workspace|model|reasoning_effort)\}', lambda m: values[m[1]], part) for part in command]
    if adapter['kind'] == 'codex_worker':
        command.append(workspace)
        if model != 'default': command += ['--model', model]
        if effort != 'default': command += ['--reasoning-effort', effort]
    elif adapter['kind'] == 'codex_cli':
        command += ['exec', '--sandbox', 'workspace-write', '--json']
        if model != 'default': command += ['--model', model]
        if effort != 'default': command += ['--config', 'model_reasoning_effort=' + json.dumps(effort)]
        command.append('-')
    elif adapter['kind'] == 'claude_code':
        command += ['--print', '--output-format', 'json']
        if model != 'default': command += ['--model', model]
        if effort != 'default': command += ['--effort', effort]
    else:
        raise ValueError('unsupported adapter kind')
    return command
