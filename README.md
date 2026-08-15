# tommy

![Tommy, a green parrot salesperson in a plaid suit](docs/assets/tommy-artwork.png)

`tommy` is a control surface for coding agents that prepare realistic sales roleplays with Expected Parrot, preserve attempts, register transcript-grounded reviews, and produce self-contained coaching reports. It is not designed as a human-operated wizard: the agent repeatedly asks Tommy what state exists and what single action comes next.

**Documentation:** [Work through the voice-practice tutorial](https://expectedparrot.github.io/tommy/)

Templates contain simulation behavior. Deals contain supplied facts. A practice combines them without silently turning agent inference into deal history.

## Agent control loop

An agent can navigate the complete workflow from these two commands:

```bash
tommy agent guide
tommy agent next
```

`agent next` is deterministic and read-only. It returns one `recommended_action` and at most three alternatives. Each action contains a stable ID, absolute `cwd`, tokenized `argv`, structured unresolved inputs, artifact prerequisites and outputs, an expected state transition, and explicit flags for local mutation, network use, spending, and required user approval.

The agent resolves placeholders from conversation or project evidence, executes the returned `argv` without shell interpolation, and calls `tommy agent next` after every material change. The shorter `tommy next` remains an alias.

## Copyable agent instructions

Copy this block into a coding agent that has shell access to a Tommy project:

```text
Install Tommy with Expected Parrot support:

python -m pip install 'tommy[edsl] @ git+https://github.com/expectedparrot/tommy.git'

Then run:

tommy agent next
```

## Example local workflow

```bash
pip install -e '.[edsl]'
tommy init demo --name "Sales practice"
cd demo

tommy scorecard add ../examples/enterprise-pricing/scorecard.json
tommy template add ../examples/enterprise-pricing/template.json
tommy deal add ../examples/enterprise-pricing/deal.json

tommy practice prepare \
  --template enterprise-pricing \
  --deal acme-research \
  --id jordan-pricing

tommy practice build --practice jordan-pricing --output-dir runs/jordan-pricing
tommy practice instructions --practice jordan-pricing
tommy practice preview --practice jordan-pricing
tommy practice deploy --practice jordan-pricing --confirm
```

After a call, retrieve its transcript directly from Expected Parrot:

```bash
tommy attempt fetch \
  --practice jordan-pricing \
  --uuid <human-survey-uuid> \
  --rep "Alex Rivera" \
  --buyer "Jordan Chen" \
  --id alex-round-1 \
  --output-dir runs/alex-round-1
```

An exported text or JSON transcript can also be imported:

```bash
tommy attempt import \
  --practice jordan-pricing \
  --transcript transcript.json \
  --rep "Alex Rivera" \
  --id alex-round-1
```

Prepare one auditable evaluator call, execute it explicitly, and register the native Results:

```bash
tommy review prepare \
  --attempt alex-round-1 \
  --model gpt-5.4-mini \
  --output-dir runs/alex-round-1
ep run \
  --jobs runs/alex-round-1/review.jobs.ep \
  --output runs/alex-round-1/review.results.ep
tommy review register \
  --attempt alex-round-1 \
  --results runs/alex-round-1/review.results.ep
tommy report --attempt alex-round-1 --output-dir runs/alex-round-1
```

Turn the weakest scorecard criterion into a focused five-minute drill, then compare reviewed attempts:

```bash
tommy drill prepare --attempt alex-round-1 --id alex-closing-drill
tommy practice build --practice alex-closing-drill --output-dir runs/alex-closing-drill

tommy compare --attempt alex-round-1 --attempt alex-round-2
```

The generated report is standalone HTML with a searchable visual transcript, coaching summary, expandable scorecard, objection analysis, and evidence links that jump to exact transcript turns. The structured review remains canonical.

## Boundaries

- `practice build` creates and verifies a native EDSL Survey artifact.
- `practice preview` does not launch a respondent study.
- `practice deploy --confirm` explicitly creates a private Expected Parrot study.
- `review prepare` creates native Jobs and reports one expected model call; `ep run` remains explicit.
- `review register --results` imports and validates completed native Results.
- Roleplays are practice evidence, not claims about how a real buyer will behave.

Run `tommy guide` for the complete lifecycle and `tommy next` for an artifact-based recommendation.
