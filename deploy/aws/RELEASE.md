# Build and send the private Neon release

These helpers do not provision AWS resources. Use them only after reviewing and applying the Terraform plan, confirming the correct credit-bearing AWS account, and waiting for the instance to appear Online in Systems Manager.

From the project root, use the application's Python environment:

```bash
venv/bin/python deploy/aws/package.py --host HOSTNAME_FROM_TERRAFORM --check-only
venv/bin/python deploy/aws/package.py --host HOSTNAME_FROM_TERRAFORM
```

The second command creates a new ignored `deploy/aws/.local/<release>/` directory. Its JSON output contains paths, not secrets:

- `resolve.tar.gz`: private release, including the production `.env` and existing GCP key.
- `server.env`: protected production settings; no local AWS credentials or profile settings are copied.
- `credentials.json`: generated demo and Grafana administrator passwords, mode 0600. Keep these private and copy them into your password manager.

The release keeps the existing pooled Neon URL and `ticket_analytics_live`. It excludes local databases, `.git`, venvs, node_modules, `.next`, frontend env files, caches, Terraform state, and the generated credentials file. No database dump or database restore is required.

Upload the selected archive to **your private Terraform-created S3 bucket**:

```bash
aws s3 cp deploy/aws/.local/RELEASE/resolve.tar.gz s3://PRIVATE_BUCKET/releases/resolve.tar.gz --sse AES256 --profile resolve-deploy --region us-east-1
```

This upload deliberately transfers the production application's service credentials to your private AWS account. Never upload it to a public bucket, GitHub, or a chat.

Review the installer plan without running it:

```bash
venv/bin/python deploy/aws/send_deploy.py --instance-id INSTANCE_ID --bucket PRIVATE_BUCKET
```

Then submit the installation through Systems Manager:

```bash
venv/bin/python deploy/aws/send_deploy.py --instance-id INSTANCE_ID --bucket PRIVATE_BUCKET --send
```

The command receipt contains an SSM command ID. Check it with:

```bash
aws ssm get-command-invocation --command-id COMMAND_ID --instance-id INSTANCE_ID --profile resolve-deploy --region us-east-1
```

The server installer validates archive paths, preserves `/opt/resolve/data`, builds the backend and frontend sequentially on EC2, starts the Neon deployment, waits for API health, and downloads/verifies the public embedding model cache. It never starts PostgreSQL. The Mac performs only archive creation and small CLI calls.

Do not call the deployment complete until public HTTPS has a valid certificate, the generated demo login works, a live ticket is stored in Neon, and **the Grafana panels render in a browser**. Backend data-source queries alone do not validate the Grafana frontend plugin.

If Terraform or another older SDK cannot consume `aws login` credentials, use AWS's documented `credential_process` bridge in a separate profile, pointing to `aws configure export-credentials --profile resolve-deploy --format process`. Never copy temporary AWS access keys into the application env or release archive.
