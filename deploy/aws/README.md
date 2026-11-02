# AWS deployment — prepared, not deployed

This bundle runs the Next.js UI, FastAPI, PostgreSQL, Grafana, and a Caddy HTTPS proxy on one `t3.medium` EC2 host. It uses an EC2 instance role for Bedrock, without storing AWS access keys on the server. Only ports 80 and 443 are published; administration uses AWS Systems Manager Session Manager instead of SSH.

Full operational tickets live in PostgreSQL on the encrypted EC2 root EBS volume. The root volume is retained if the instance is terminated. BigQuery contains analytics and optional full-ticket snapshots; the current BigQuery sandbox expires its data after at most 60 days, so it is **not** the permanent source of truth. Back up PostgreSQL to the private, encrypted, versioned S3 bucket.

## Current blocker

No AWS resources were created. The working application profile can invoke Bedrock but cannot describe or create EC2 resources. The saved `infra-deploy` credentials fail authentication. Deployment requires restoring access to an AWS account/profile with EC2, IAM, S3, Elastic IP, and SSM deployment permissions. If account MFA is unavailable, recover account access through AWS support; do not disable or bypass MFA.

A temporary tunnel to the local app is a preview, not this deployment. The Mac must remain online for a tunnel to work.

## 1. Review and provision

From the project root, after recovering a valid deployment profile:

```bash
aws sts get-caller-identity --profile infra-deploy --region us-east-1
cd deploy/aws
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: replace the example visitor CIDR and select the profile.
terraform init
terraform plan -out=review.tfplan
terraform apply review.tfplan
terraform output
```

`web_cidrs` is required and has no default-open value. For a public password-protected demonstration, explicitly choose `["0.0.0.0/0"]` for HTTP/HTTPS **only**. Never expose PostgreSQL or the backend API port. Public certificate authorities need to reach Caddy on port 80 or 443; a private visitor allowlist also needs a separately configured DNS certificate challenge.

The outputs include a stable Elastic IP, instance ID, private S3 bucket, and a suggested `IP.sslip.io` hostname. This third-party DNS name avoids purchasing a domain for an initial demo; it has no availability guarantee. Caddy obtains a public certificate when the name resolves correctly and public ACME validation succeeds. If validation is rate-limited, use a domain you control. Do not bypass browser certificate warnings.

The bootstrap installs Docker, Compose, AWS CLI, and a small swap file for the first build. Check `/var/log/cloud-init-output.log` through Session Manager if setup is incomplete.

## 2. Prepare server secrets locally

Create an ignored staging directory under `deploy/aws/.local/`. The release archive must contain the application source plus a **production** `.env` and `secrets/gcp-key.json` at the project root.

Start with `.env.example` and copy the working Azure, Pinecone, BigQuery, and optional LangSmith values from your local `.env`. Set:

```dotenv
ENV=production
AWS_REGION=us-east-1
APP_HOST=REPLACE_WITH_TERRAFORM_SUGGESTED_HOSTNAME
DEMO_USER=demo
DEMO_PASSWORD_HASH='REPLACE_WITH_CADDY_BCRYPT_HASH'
POSTGRES_PASSWORD=REPLACE_WITH_RANDOM_ALPHANUMERIC_SECRET
GRAFANA_ADMIN_PASSWORD=REPLACE_WITH_DIFFERENT_RANDOM_SECRET
NEXT_PUBLIC_API_URL=/backend
NEXT_PUBLIC_GRAFANA_URL=/grafana
GOOGLE_APPLICATION_CREDENTIALS=/srv/gcp-key.json
```

Do not copy `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE`, `AWS_SHARED_CREDENTIALS_FILE`, or `AWS_CONFIG_FILE` into the server environment. The instance role supplies AWS credentials. The production Compose file supplies the database URL.

Generate a strong demo password and its hash using Caddy's `caddy hash-password` command; keep the plaintext password in your password manager. Put the hash in single quotes in `.env` so its `$` characters are not expanded. Create `secrets/gcp-key.json` using the existing working GCP key. Never commit the production `.env`, keys, archive, database dump, Terraform state, or plan.

The server bundle layout is:

```text
/opt/resolve/
  .env
  secrets/gcp-key.json
  app/ domains/ frontend/ grafana/
  Dockerfile requirements.txt seed_kb.py
  deploy/aws/compose.yml
  deploy/aws/Caddyfile
  data/                       # server data; never overwrite during releases
```

Package only these application files and the reviewed secrets. Exclude `.git`, local `venv`, `node_modules`, `.next`, caches, local `.env` backups, and local databases. Upload the archive to the private Terraform bucket at `releases/resolve.tar.gz` with `aws s3 cp --sse AES256`. This deliberately transmits the production service credentials to **your private AWS bucket**. Keep access restricted to the deployer and instance role.

## 3. Install through Session Manager

```bash
aws ssm start-session --target INSTANCE_ID --profile infra-deploy --region us-east-1
```

In the server shell:

```bash
sudo -i
cd /opt/resolve
aws s3 cp s3://RELEASE_BUCKET/releases/resolve.tar.gz /tmp/resolve.tar.gz
# Review the archive's paths before extraction; it must not replace data/.
tar -tzf /tmp/resolve.tar.gz
tar -xzf /tmp/resolve.tar.gz -C /opt/resolve
chmod 600 .env secrets/gcp-key.json
mkdir -p data/grafana
chown 472:472 data/grafana
docker compose --env-file .env -f deploy/aws/compose.yml config --quiet
docker compose --env-file .env -f deploy/aws/compose.yml build backend
docker compose --env-file .env -f deploy/aws/compose.yml build frontend
docker compose --env-file .env -f deploy/aws/compose.yml up -d postgres
docker compose --env-file .env -f deploy/aws/compose.yml ps
```

Build services sequentially on this small host, as shown above. The first model download can be slow; model files persist under `data/models/` for later starts.

After the migration step below (or after skipping migration for a fresh workspace), run `docker compose --env-file .env -f deploy/aws/compose.yml up -d`. Open `https://APP_HOST`, enter the demo credentials, create a ticket, and open Analytics. The backend, database, and Grafana have no direct public host ports. Caddy protects the application and Grafana with one demo password boundary. Grafana's anonymous viewer setting is only reachable through that boundary; its administrator password is separate. This is a single-workspace demo, not a multi-tenant authentication system.

## 4. Move the existing tickets and verify

On your Mac, export the existing Compose PostgreSQL database:

```bash
docker compose exec -T postgres pg_dump -U ticket_admin -d tickets_db -Fc > deploy/aws/.local/tickets.dump
```

Upload the dump to `backups/initial/tickets.dump` in the private S3 bucket. On the server, download it and restore into a **fresh empty** database before accepting new tickets:

```bash
aws s3 cp s3://RELEASE_BUCKET/backups/initial/tickets.dump /tmp/tickets.dump
docker compose --env-file .env -f deploy/aws/compose.yml exec -T postgres pg_restore -U ticket_admin -d tickets_db --no-owner --no-acl < /tmp/tickets.dump
docker compose --env-file .env -f deploy/aws/compose.yml up -d
```

Do not restore over a populated database without a migration plan. For a fresh install, import the dump before starting the backend for the first time so its automatic table creation does not conflict with the dump.

Verify the inbox shows the migrated IDs, submit a new synthetic ticket, inspect its complete response and agent activity, and query BigQuery for that ticket's event and snapshot. Open all four Grafana views and check that their selected time range includes the test.

## 5. Back up and stop costs

On the EC2 host, after setting the actual bucket name:

```bash
cd /opt/resolve
install -d -m 0700 data/backups
backup_file="data/backups/tickets-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose --env-file .env -f deploy/aws/compose.yml exec -T postgres pg_dump -U ticket_admin -d tickets_db -Fc > "$backup_file"
aws s3 cp "$backup_file" "s3://RELEASE_BUCKET/backups/$backup_file" --sse AES256
```

Automate this command only after testing a restore. Monitor disk space, S3 versions, and successful backup timestamps. PostgreSQL data, Caddy certificates, Grafana state, and embedding models live under `/opt/resolve/data` and must survive application releases.

Stopping EC2 stops compute charges but EBS, Elastic IP, and S3 can still incur charges. Terraform intentionally retains the root disk on termination and refuses to delete a nonempty S3 bucket; review retained resources during cleanup. Snapshot/export data before deleting anything.

AWS promotional credits apply only to eligible AWS charges, subject to their terms, expiry, and balance. They do not cover Azure, Pinecone, or Google Cloud charges. Check the Billing Credits page and create a budget alert before launch. EC2, EBS, public IPv4, S3, transfer, and Bedrock usage must be included in the budget.
