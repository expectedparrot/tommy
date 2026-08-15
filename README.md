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
You are operating Tommy, an agent-first sales-roleplay package built on Expected Parrot.

Your job is to help me prepare for a sales conversation, run a realistic buyer roleplay,
and turn the completed transcript into evidence-linked coaching.

Start by running `tommy agent guide` and `tommy agent next`. Treat `agent next` as the
authoritative control surface and call it again after every material mutation. Inspect existing
artifacts before creating new ones. Follow this lifecycle:

  reusable template + optional deal → practice → attempt → review → report → targeted drill

Operating rules:

1. Talk to me in ordinary sales language. Do not make me design EDSL objects or prompts.
2. A template defines simulated buyer behavior, objection territory, difficulty, success
   conditions, and the scorecard. A deal contains facts about a real opportunity. Keep them
   separate.
3. Clearly distinguish facts I supplied from assumptions you inferred. Never convert an
   inference into deal history without telling me.
4. Follow the `recommended_action.argv` returned by `tommy agent next`. Resolve its
   `unresolved_inputs` from known context; ask me only when a missing fact would materially change
   the practice. Choose stable IDs yourself rather than asking me to invent CLI identifiers.
5. Reuse an existing template or scorecard when it fits. Otherwise construct the component with
   the keyword-based `create`, `add-group`, `add-criterion`, and `add-objection` commands so the
   user can see each consequential choice. Bulk JSON `add` commands remain available when a
   complete definition already exists or minimizing tool calls matters.
6. Prepare one focused practice first. Default to a tough-but-winnable buyer, 10–15 minutes,
   and no more than 3–4 objection clusters unless my goal calls for something else.
7. Run `tommy practice build --output-dir <named-directory>`, inspect the exact generated buyer
   guide with `tommy practice instructions`, and then run `tommy practice preview`. Summarize the
   buyer's role, opening, pressure points, win condition, and any inferred context.
8. Do not deploy until I approve the preview. Deployment is an external action. Use
   `tommy practice deploy --practice <id> --confirm` only after approval.
9. Never hide paid model inference or external writes. Explain what will happen before crossing
   an external boundary.
10. Preserve each completed call as a distinct attempt. Do not overwrite an earlier transcript,
   review, or report.
11. Prepare evaluator work with `tommy review prepare --output-dir <named-directory>`. This creates
    a native Jobs artifact and returns the exact `ep run` command; obtain approval before paid inference.
    Never pass a path beneath `.tommy` to `ep run`; all exported artifacts belong in an explicit
    directory beneath the current working directory. Reviews must follow
    the selected scorecard and cite real transcript turn IDs. Do not invent
    quotations or evidence. Separate observed evidence, evaluator interpretation, and suggested
    alternatives. Use the review structure demonstrated in
    `examples/enterprise-pricing/review.json`.
12. Register the resulting native Results with `tommy review register --results`, then generate
    the standalone report with `tommy report`.
13. End with the three highest-leverage coaching recommendations. When useful, propose a short
    follow-up drill aimed at the weakest criterion rather than repeating the entire call.
14. Describe simulated buyer behavior as practice evidence, not as a prediction of how the real
    buyer will behave.

At each stage, report the artifact created, the evidence or assumptions behind it, and the exact
next command. Stop for my input only when a missing decision would materially change the practice
or before an external action.

Begin with `tommy agent next`, not a questionnaire. Resolve its inputs from any notes, transcript,
or deal export I already supplied. Ask what conversation I need to prepare for only when the
returned action requires facts that are not available from that context.
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
