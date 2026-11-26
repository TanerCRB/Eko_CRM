# Operator seed

The operator seed (EKO-3-06, SEED-1) loads the committed synthetic dataset `seed-v1` — three
shares of 200 customers — for three existing rep subjects. The design is the EKO-3-06 addendum to
ADR-0003, ADR-0004 and ADR-0005
([draft](../architecture/decisions/EKO-3-06-operator-seed-adr0003-adr0004-adr0005-addendum-draft-2026-11-25.md)).

## Command

The seed runs only as a one-off of `worker`, from the directory of `compose.yaml`, with the same
`--env-file` and project name as the running composition:

```
docker compose run --rm --no-deps worker python -m app.seed <subject> <subject> <subject>
```

The i-th subject owns the i-th share.

## Before the run: the synthetic-only declaration

The environment file holds the line:

```
APP_SYNTHETIC_DATA_ONLY=declared
```

Without it, or with any other value, the seed exits non-zero with
`seed refused to start: the target is not declared synthetic-only (APP_SYNTHETIC_DATA_ONLY does not hold the accepted value)`
and writes nothing.

- In a shared environment, the IT department adds the line only after the human's dated
  ADR-0005-C16 statement for that environment exists, and removes it when the statement is
  withdrawn.
- In developer and test environments, adding it is the developer's own statement.
- Production does not set it before the GDPR impact assessment.
- Never pass the declaration with `-e` or through the shell: it belongs to the environment file.
  Compose cannot prevent a per-run override, so this rule is the only guard against it.

## Subjects

Exactly three distinct subjects, each 1 to 255 printable ASCII characters. They are compared
byte-wise and are not checked against Keycloak. A seeded rep appears in the manager's owner
selector only after that rep's first login.

## Schema

The seed never migrates. It refuses a database whose revision is not its code's head
(`seed refused to start: database revision …`); run `migrate` first.

## Output

JSON lines on stderr (process `worker`, logger `app.seed`; the form is in
[log-format.md](log-format.md)).

- Each refused record is a line `record <dataset key> refused: <rule family> (<field>)`.
- The summary is `seed finished: N records, A added, L already loaded, R refused`, with
  `; nothing was added` on a re-run.
- Exit 0 means every record is loaded or already loaded; anything else is non-zero.
- No customer value is written to the output.

## Re-running

A re-run is safe. It adds only what is missing and changes no loaded record or owner, also when it
names other subjects. Running two seeds at once is not supported (EKO-3-06, G-6).
