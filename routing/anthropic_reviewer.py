"""Anthropic Messages-compatible review using an explicit trusted CC settings file.

No shell environment fallback: inherited provider/model overrides are ignored.
This module reads credentials only in the Commander invocation process.
"""
import json
from pathlib import Path
import urllib.parse
import urllib.request


def validate_adapter(adapter):
    if not isinstance(adapter.get('settings_file'), str) or not adapter['settings_file']:
        raise ValueError('settings_file_required')
    host = adapter.get('allowed_host')
    if not isinstance(host, str) or not host or any(c in host for c in '/:@?# '):
        raise ValueError('explicit_allowed_host_required')
    if type(adapter.get('max_output_tokens')) is not int or adapter['max_output_tokens'] < 1:
        raise ValueError('invalid_output_limit')


def provider_settings(adapter):
    settings = json.loads(Path(adapter['settings_file']).expanduser().read_text())
    env = settings.get('env', {})
    base = env.get('ANTHROPIC_BASE_URL', '')
    url = urllib.parse.urlsplit(base)
    if (url.scheme != 'https' or url.hostname != adapter['allowed_host'] or url.username
            or url.password or url.query or url.fragment or url.port not in (None, 443)):
        raise ValueError('untrusted_provider_endpoint')
    return base, env


def request_messages(reviewer, packet, instructions, deadline):
    from routing.reviewer_runtime import _canonical, strict_json, _NoRedirect, MAX_BYTES
    adapter = reviewer['adapter']
    validate_adapter(adapter)
    base, env = provider_settings(adapter)
    url = urllib.parse.urlsplit(base)
    path = url.path.rstrip('/')
    endpoint = base.rstrip('/') + ('/messages' if path.endswith('/v1') else '/v1/messages')
    token = env.get('ANTHROPIC_AUTH_TOKEN')
    api_key = env.get('ANTHROPIC_API_KEY')
    headers = {'User-Agent': 'agent-orchestration-workflow/1.0', 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01'}
    if isinstance(token, str) and token:
        headers['Authorization'] = 'Bearer ' + token
    elif isinstance(api_key, str) and api_key:
        headers['x-api-key'] = api_key
    else:
        raise ValueError('missing_provider_credential')
    body = {'model': reviewer['model_id'], 'system': instructions,
            'messages': [{'role': 'user', 'content': _canonical(packet).decode()}],
            'max_tokens': min(adapter['max_output_tokens'], reviewer['max_tokens'])}
    request = urllib.request.Request(endpoint, data=_canonical(body), headers=headers, method='POST')
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=deadline) as response:
        if response.status != 200:
            raise ValueError('provider_status')
        wire = strict_json(response.read(MAX_BYTES + 1))
    if not isinstance(wire, dict):
        raise ValueError('invalid_provider_envelope')
    usage = wire.get('usage') or {}
    counts = [usage.get('input_tokens'), usage.get('output_tokens')]
    counts += [usage.get('cache_creation_input_tokens', 0), usage.get('cache_read_input_tokens', 0)]
    tokens = sum(counts) if all(type(n) is int and n >= 0 for n in counts) else None
    blocks = wire.get('content')
    valid = isinstance(blocks, list) and bool(blocks) and all(isinstance(b, dict) and b.get('type') == 'text' and isinstance(b.get('text'), str) for b in blocks)
    # Normalize only transport shape; the shared runtime validates every review field.
    return {'model': wire.get('model'), 'usage': {'total_tokens': tokens, 'cost_usd': None},
            'choices': [{'finish_reason': 'stop' if wire.get('stop_reason') == 'end_turn' and valid else 'invalid',
                         'message': {'content': ''.join(b['text'] for b in blocks) if valid else ''}}]}
