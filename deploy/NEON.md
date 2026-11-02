# Move the ticket database to Neon

Neon provides the managed Postgres database. AWS hosts the application; AWS credits do not pay third-party providers. Choose Neon's Free plan for the MVP and review its current storage/compute limits in your account.

1. Create a Neon project in a region near the AWS app. Keep its password private. Copy the **direct, unpooled** PostgreSQL connection string for migration.
2. Add it to the root project's gitignored `.env` as `CLOUD_DATABASE_URL`. The migration always requires TLS (`sslmode=require`). Never put it in a shell command, a frontend variable, Git, or chat.
3. Keep the local Postgres container running. Pause ticket creation while moving data so the app cannot add new local records after the migration snapshot.
4. From the project root, check connectivity and counts without changing either database:

   ```bash
   venv/bin/python deploy/migrate_postgres.py --check-only
   ```

5. Copy the records into the empty Neon database:

   ```bash
   venv/bin/python deploy/migrate_postgres.py --apply
   ```

   This preserves IDs, timestamps, JSON traces, ticket responses, and agent decisions. All target table creation and inserts happen in one transaction. A count or content-hash mismatch rolls the transaction back. The source is never deleted or updated. If the target already contains the exact same records, the command reports completion without inserting duplicates. If it contains different records, the command refuses to overwrite them.

6. Confirm `verified_identical: true`, then configure the backend's `DATABASE_URL` from `CLOUD_DATABASE_URL` and restart only the backend. The application must be switched after verification; copying data alone does not change which database it uses.
7. Submit one new ticket, confirm it appears in the Neon console, and verify the app can still show older ticket details. Re-run check-only **before** accepting new remote writes if you need a final identical-snapshot check. Once the app starts writing to Neon, a later migration check against the old local source will correctly report different data and refuse to copy over it.

Defaults match local Compose: `127.0.0.1:5433`, user `ticket_admin`, database `tickets_db`; the password comes from `POSTGRES_PASSWORD` or the local-development default. If your source uses a different address, set `MIGRATION_SOURCE_DATABASE_URL` in `.env`. The script uses only the application's three SQLAlchemy tables (`tickets`, `agent_decisions`, `drafted_responses`).

Keep the local database until the remote app has been verified. For rollback, stop accepting writes first; pointing back to the unchanged local database omits any newer Neon-only records, so migrate or export those records before switching back.

## Keep the Mac responsive

The local stack has per-service CPU and memory limits. Start only PostgreSQL for migration, then stop the local database once Neon has been verified. Avoid parallel Docker image builds; ordinary startup reuses built images. Backend model inference runs one ticket at a time.
