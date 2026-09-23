# DB Migration Pipeline Training

A small, runnable model of the **Liquibase-gated CI/CD pipeline + config-driven SQS Lambda**
pattern used by `report-transformation-service`. It reimplements the shape of that pipeline
against a generic **"order totals calculation"** domain (`orderId`, `line_item_total`,
`discount_total`, `tax_total`) instead of the real proprietary scoring/reporting logic - the goal
is to teach the *pattern*, safely.

## What This Teaches

1. **Migrations as an append-only, checksummed, environment-gated log.** `db/migration_runner.py`
   is a from-scratch (but faithful) reimplementation of the ideas Liquibase actually provides:
   every changelog file runs at most once, ever (tracked in a `schema_history` table); editing an
   already-applied file is a loud failure (`ChecksumMismatchError`), not a silent divergence
   between environments; and a `-- context: DEV,STAGE` header keeps sample/seed data out of
   production while running the exact same changelog everywhere else.
2. **Pipeline stage ordering that makes bad deploys impossible, not just discouraged.**
   `.gitlab-ci.yml`'s `build -> test -> migrate -> deploy` stages, with each environment's
   `deploy_*` job `needs:` its *own* `migrate_*` job (not just "the migrate stage finished
   somewhere") - GitLab's DAG-mode pipeline refuses to start `deploy_prod` before `migrate_prod`
   has specifically succeeded.
3. **Config-driven execution order via a CSV, not code.** `apps/calc_runner/db_func_config.csv`
   says which calculations run, in what order, and whether they're sequential (`S`) or safe to
   run in parallel (`P`) - reordering or adding a calculation is a data change, not a redeploy.
4. **Real transaction-boundary tradeoffs.** The real service commits after every sequential
   function AND again at the end - not actually atomic. This training's `process_order()` commits
   exactly once, only after every function (sequential and parallel) has succeeded, and rolls
   back everything otherwise - see the exercises below for what changes if you don't.
5. **The "shared connection across parallel threads" gotcha, reproduced on purpose.** The real
   service shares one JDBC connection across `CompletableFuture`s - not thread-safe for a real
   network DB driver. `apps/calc_runner/handler.py` reproduces that same shape (a `threading.Lock`
   serializing access to one shared `sqlite3.Connection`) instead of hiding it, specifically so
   you can see - and fix - the issue.
6. **DLQ + bounded retries + reserved concurrency**, all as CDK constructs asserted on directly
   in `cdk/test/calc_runner_stack.test.ts` - genuine, offline, no-AWS-credentials-needed
   verification that the infrastructure actually has the safety properties it's supposed to.
7. **Fire-and-forget completion notification**, injectable for testing - not a Step Functions
   task-token callback (see `stepfunctions_training` for that pattern instead); this is the
   simpler "tell whoever's listening, best-effort" shape.

## Project Layout

```
migrations/changelog/     001_...sql, 002_...sql, ... - ordered, numbered, checksummed changesets
db/
  migration_runner.py     Changeset/MigrationRunner - load, filter by context, apply, track
  connection.py           environment-driven DB-API connection helper (sqlite3 stands in for a real DB)

apps/calc_runner/
  db_func_config.csv       which calculations run, in what order, sequential vs parallel
  config.py                loads + validates db_func_config.csv
  functions.py              the calculations themselves (stand-ins for real stored procedures)
  notifier.py               fire-and-forget completion notification
  handler.py                the SQS-triggered entry point tying it all together

tests/
  test_migration_runner.py       context filtering, idempotency, checksum-mismatch detection
  test_calc_runner_config.py     CSV parsing/validation
  test_calc_runner_handler.py    sequential-then-parallel execution, rollback-on-failure, SQS batch

cdk/
  lib/calc_runner_stack.ts       SQS queue + DLQ + Lambda + EventSourceMapping
  test/calc_runner_stack.test.ts  Jest + aws-cdk-lib/assertions structural tests

.gitlab-ci.yml            build -> test -> migrate -> deploy, migrate gated per environment
```

## Try It

### Run the migration runner + calc_runner tests
```powershell
cd C:\PythonProjects\db_migration_pipeline_training
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -v
```
13 tests, all offline, using an in-memory sqlite3 database - no real DB, no AWS credentials.

### Apply migrations to a real file yourself
```powershell
.\.venv\Scripts\python -c "
import sqlite3
from pathlib import Path
from db.migration_runner import MigrationRunner, load_changelog
conn = sqlite3.connect('local-dev.db')
changesets = load_changelog(Path('migrations/changelog'))
print(MigrationRunner(conn, context='DEV').run(changesets))
"
```
Run it again - it prints `[]` the second time (idempotent). Try `context='PROD'` instead and
notice `003_seed_dev_sample_data.sql` never applies.

### Type-check + test the CDK stack (no AWS account needed)
```powershell
cd cdk
npm install
npx tsc --noEmit
npx jest
```

### Inspect the synthesized stack
```powershell
npx cdk synth --quiet
```

## Exercises (for training)

1. **Break the checksum guard on purpose.** Edit any line inside
   `001_create_orders_table.sql` after running the migration runner once, run it again, and watch
   `ChecksumMismatchError` fire. Then do it the *right* way: add `005_...sql` instead.
2. **Make the transaction boundary match the real service (and see why it's worse).** Change
   `process_order()` to commit after every sequential function, like the original
   `DbFunctionHandler.executeFunction` does, then write a test where `calc_discount_total` fails
   and confirm `calc_line_item_total`'s update survives anyway - a genuinely partial write.
3. **Fix the shared-connection-across-threads issue for real.** Replace the `threading.Lock`
   workaround in `_run_parallel` with one connection (and one transaction) per worker thread, and
   figure out how the final commit/rollback logic needs to change once there's more than one
   connection involved.
4. **Add a function that must run after the parallel group.** Try adding a `calc_grand_total`
   that depends on both `calc_discount_total` and `calc_tax_total`'s output. The current
   `sequential-then-parallel-with-no-third-phase` design can't express "runs after parallel" -
   sketch (in a comment, or actual code) what a `config.py` change to support an `S2` phase after
   `P` would look like.
5. **Add a `migrate_ot`/`deploy_ot` pair** to `.gitlab-ci.yml`, following the `stage` example
   exactly (copy `.env_stage`, rename to `.env_ot`, add the two jobs with the right `needs:`) -
   the exact motion for onboarding a new deploy target safely.
