"""Real Claude Code client bridge for providers restricted to that client."""
import json
from pathlib import Path


def validate_adapter(adapter):
    for key in ('executable','settings_file'):
        if not isinstance(adapter.get(key),str) or not adapter[key]:
            raise ValueError('explicit_claude_client_configuration_required')
    from routing.anthropic_reviewer import validate_adapter as validate_provider
    validate_provider(dict(adapter, max_output_tokens=1))
    if adapter.get('proxy_url') is not None:
        from routing.reviewer_runtime import validate_proxy
        validate_proxy(adapter['proxy_url'])


def review_schema(role):
    evidence={'type':'array','items':{'type':'string'},'minItems':1}
    issue={'type':'object','additionalProperties':False,'properties':{
        'id':{'type':'string'},'severity':{'type':'string','enum':['low','medium','high','critical']},
        'description':{'type':'string'},'evidence':evidence},'required':['id','severity','description','evidence']}
    properties={'verdict':{'type':'string','enum':['PASS','FAIL','UNCERTAIN']},
        'confidence':{'type':'number','minimum':0,'maximum':1},'issues':{'type':'array','items':issue},
        'evidence':evidence,'recommended_action':{'type':'string','enum':['accept','minor_fix','strategy_failure','worker_mismatch','ambiguous_task','high_risk_uncertainty']},
        'reviewer_specialty':{'type':'string','enum':[role]}}
    return {'type':'object','additionalProperties':False,'properties':properties,'required':list(properties)}


def request_claude(reviewer, packet, instructions, deadline):
    from routing.reviewer_runtime import run_command, strict_json
    adapter=reviewer['adapter'];validate_adapter(adapter)
    from routing.anthropic_reviewer import provider_settings
    base, env = provider_settings(adapter)
    key = env.get('ANTHROPIC_API_KEY') or env.get('ANTHROPIC_AUTH_TOKEN')
    if not isinstance(key,str) or not key: raise ValueError('missing_provider_credential')
    provider_env = {'ANTHROPIC_API_KEY':key,'ANTHROPIC_BASE_URL':base,'HOME':str(Path.home())}
    if env.get('ANTHROPIC_AUTH_TOKEN'):
        provider_env['ANTHROPIC_AUTH_TOKEN']=env['ANTHROPIC_AUTH_TOKEN']
    argv=[adapter['executable'],'--print','--bare','--setting-sources','',
          '--model',reviewer['model_id'],'--effort','low','--output-format','json',
          '--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
          '--disable-slash-commands','--no-session-persistence','--max-turns','2',
          '--json-schema',json.dumps(review_schema(packet['reviewer_role'])),
          '--max-budget-usd',str(reviewer['max_cost_usd']),'--system-prompt',instructions]
    import tempfile
    with tempfile.TemporaryDirectory(prefix='claude-blind-review-') as directory:
        code,raw,error=run_command(argv,json.dumps(packet,ensure_ascii=False),deadline,cwd=directory,proxy_url=adapter.get('proxy_url'),provider_environment=provider_env)
    try:
        data=strict_json(raw)
    except (ValueError, TypeError):
        raise ValueError('claude_client_'+(error or 'invalid_json')) from None
    if not isinstance(data,dict):raise ValueError('invalid_claude_envelope')
    models=data.get('modelUsage',{})
    model=next(iter(models)) if isinstance(models,dict) and len(models)==1 else None
    usage=data.get('usage') or {}
    counts=[usage.get(k,0) for k in ('input_tokens','output_tokens','cache_creation_input_tokens','cache_read_input_tokens')]
    tokens=sum(counts) if usage and all(type(n)is int and n>=0 for n in counts) else None
    structured=data.get('structured_output')
    text=json.dumps(structured) if isinstance(structured,dict) else data.get('result','')
    stats=data.get('subagent_stats') or {}
    valid=(not error and not data.get('is_error',True) and data.get('subtype')=='success'
           and isinstance(text,str) and type(data.get('num_turns')) is int and 1<=data['num_turns']<=2 and stats.get('spawned',0)==0)
    # CLI token prices are estimates, not the intermediary's actual bill.
    return {'model':model,'usage':{'cost_usd':None,'total_tokens':tokens},
            'choices':[{'finish_reason':'stop' if valid else 'invalid','message':{'content':text}}]}
