# Tommy repository instructions

## Product contract

Tommy is an agent-first sales-roleplay package. Preserve this artifact lifecycle:

```text
template + optional deal → practice → attempt → review → report → targeted drill
```

- Templates define simulated behavior; deals contain supplied facts. Never silently turn inference into deal history.
- Every CLI command emits one versioned JSON envelope to stdout. Logs belong on stderr.
- Local preparation, external execution, and result registration must remain distinct commands.
- Previewing must not deploy. Deployment requires explicit confirmation.
- Model execution belongs to `ep run`; Tommy prepares native Jobs and registers native Results.
- Preserve attempts and reviews rather than overwriting prior practice evidence.
- Review evidence must cite valid transcript turn IDs. Keep observed evidence, interpretation, and suggested alternatives distinct.
- AI buyer behavior is practice evidence, not a prediction of how a real buyer will behave.
- `tommy agent next` is the canonical control surface. It must remain deterministic and read-only,
  recommend one state-derived action, and expose tokenized argv, unresolved inputs, artifacts,
  expected transitions, and mutation/network/spending/approval flags.
- Human users should supply sales context and consequential approvals, not operate the CLI or
  invent internal identifiers. Agents choose stable IDs and rerun `agent next` after mutations.

## Engineering workflow

- Use Python 3.11 or newer.
- Keep EDSL imports lazy so local artifact commands work without the optional dependency.
- Use native `.ep` artifacts for Survey, Jobs, and Results, including save/load verification.
- Add stable error codes for recoverable failures and test them.
- Run `python -m ruff check src tests` and `python -m pytest -q` before handoff.
- Do not perform live deployment or paid inference in tests.
