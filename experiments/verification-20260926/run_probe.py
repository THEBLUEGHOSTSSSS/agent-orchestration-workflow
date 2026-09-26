"""Explicit paid smoke probe. Four calls at most; never production learning."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from routing.reviewer_runtime import build_blind_packet, run_reviewer

ROOT = Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'live-results.json')
    output=parser.parse_args().output
    # Refuse to overwrite prior evidence before any paid call.
    with output.open('x') as stream:
        stream.write('[]\n')
    models = [('openai', 'gpt', 'openai/gpt-6-sol'), ('anthropic', 'claude', 'anthropic/claude-haiku-4.5')]
    results=[]
    for stage, expression in [('hidden_bug','a-b'),('corrected','a+b')]:
        for provider, family, model in models:
            cfg={'reviewer_id':family+'-probe','provider':provider,'family':family,'model_id':model,'enabled':True,
                 'roles_supported':['correctness_reviewer'],'max_cost_usd':.20,'max_tokens':6000,'timeout_seconds':45,
                 'adapter':{'kind':'openrouter','api_key_env':'OPENROUTER_API_KEY','max_output_tokens':1600}}
            packet=build_blind_packet({'objective':'Implement add(a,b) for ordinary integer inputs.',
                'acceptance_criteria':[{'id':'C1','check':'add(a,b) must equal the mathematical sum of a and b for positive, negative and zero integers.'}]},
                [{'path':'maths.py','content':'def add(a,b):\n    return '+expression+'\n'}],
                [{'name':'import','status':'passed','summary':'Module syntax and import pass. No numerical assertions were run.'}], 'correctness_reviewer')
            report=run_reviewer(cfg,packet)
            results.append({'stage':stage,'requested_model':model,'source_kind':'probe','report':report})
            output.write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
            print(json.dumps({'stage':stage,'model':model,'status':report['status'],'verdict':(report.get('result') or {}).get('verdict'),'usage':report['usage'],'error':report['error_code']}),flush=True)
            if report['status']!='REPORTED':
                return 1
    return 0
if __name__=='__main__':
    raise SystemExit(main())
