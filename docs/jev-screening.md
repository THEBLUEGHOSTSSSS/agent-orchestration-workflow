# Optional Jev evidence screening

Jev is an advisory decision service, not an execution Worker or Commander. The
existing Human → Commander → Worker authority and two-attempt limit remain intact.
OFF is the default. SHADOW records predictions; ASSIST allows the Commander to
use them to prioritize review. Both retain every claim and its evidence and require
actual Commander review. Neither drops items, accepts work, diagnoses model blame,
spends a Worker attempt, or adds Worker suitability experience.

## Use in an existing task

Set `OPENROUTER_API_KEY` in the invoking terminal environment. Do not put a key in
configuration, prompts, packets or source control. Only send authorized project
material. The fixed backend is OpenRouter Decisions API, `typesafe/jev-1.13`;
returned resolved model and actual usage/cost are recorded. This optional backend
does not constrain Commander/Worker host or model choices.

After Worker execution returns and the task is `AWAITING_REVIEW`, prepare a JSON
packet with the canonical logical task ID and only these fields:

```json
{
  "logical_task_id": "TASK_ID",
  "items": [
    {
      "id": "C1",
      "claim": "All tests passed.",
      "evidence": "The test command was not run because dependencies were missing."
    }
  ]
}
```

Use the same registry and ledger as the execution:

```sh
python3 scripts/route_worker.py --config my-routing.json --state .work/worker-routing/state.json screen TASK_ID packet.json --mode SHADOW
# Inspect all original artifacts, test evidence and advisory results yourself.
python3 scripts/route_worker.py --config my-routing.json --state .work/worker-routing/state.json review TASK_ID REVIEW.json
```

The result is appended to the reported attempt's `advisory_screens`; an event
records its status and packet hash. The ordinary `review` command remains mandatory.
Screening does not modify acceptance, execution count, retry routing or experience
records. A concurrent change to review state prevents attachment. No network call
runs while holding the ledger lock. Evidence truth and packet completeness remain
Commander responsibilities: copied strings are not cryptographic artifact provenance.

For an offline packet or a deliberately separate probe:

```sh
python3 scripts/screen_evidence.py --mode OFF --input packet.json --output screening.json
# Explicit paid opt-in; choose a fresh output file:
python3 scripts/screen_evidence.py --mode SHADOW --input packet.json --output screening-live.json
```

Exit 0 means DISABLED or SCREENED, not accepted. Operational failures return
UNKNOWN (exit 2); Commander continues the original review without treating that as
a pass. Invalid arguments/identity are refused. One request, no automatic retries,
30-second socket timeout, bounded request/response sizes and a maximum of 32 items.
There is no cumulative account spending cap; repeated explicit screens still cost
money. Set provider-side spending limits separately. No background service runs.

Inputs and responses are validated; redirects are refused; provider error bodies
and credentials are omitted. OFF reads no API key and makes no request. Role flags
are cooperative guards, not a sandbox or reviewer authentication. The provider may
round probabilities, so the three-way sum tolerates up to 0.015 rounding error.
Confidence is not a calibrated guarantee of correctness in your project.

## Validation and current adoption

The [pilot](../experiments/jev-pilot-20260925/REPORT.md) uses this repository's code,
with explicit seeded false/unsupported claims. Jev matched 16/18 fixed labels;
both errors were insufficient → contradicted, including a high-confidence error.
After the user topped up, Astra alone and Jev-assisted Astra each matched 18/18;
assisted API cost was 21.62% higher. Each arm has one successful observation,
not a statistically established performance estimate. The previous credit failures
are retained. No auto-accept was tested. Keep default OFF; all pilot data is
`probe`, not Worker training evidence. Explicit SHADOW remains available for
separately justified experiments. No background activation occurs.

Reference: [OpenRouter official interface](https://openrouter.ai/blog/tutorials/how-to-use-jev/).
