# Infrastructure

`infra/aws/` and `infra/azure/` are separate Terraform stacks, applied independently.

- `infra/aws/` — VPC, RDS Postgres, and an EC2 instance that hosts the
  Travel Desk app (see [`../travel_booking/README.md`](../travel_booking/README.md)).
  Not used by the root ticket-resolution app, which runs on the Compose
  stack instead (`docker-compose.yml`) with Bedrock for inference.
- `infra/azure/` — Azure Text Analytics (Cognitive Services), used by the
  ticket-resolution app for NER/sentiment. Uses the `F0` (free tier) SKU.

## Security notice

1. **Security groups must not be `0.0.0.0/0`.** SSH (22) and direct Postgres
   access (5432) require an explicit `allowed_management_cidr_blocks` (no
   default — `terraform plan` fails until it's set to your IP/VPN CIDR).
   RDS `publicly_accessible` defaults to `false`; the app reaches it over
   the private network instead. The app's own HTTP port is intentionally
   open to the internet — it's a public web app.
2. **Never commit real `*.tfvars` or `*.pem` files.** Both are gitignored;
   use the `*.tfvars.example` templates. If a real password was ever
   committed and applied publicly, rotate it and consider purging it from
   git history.

## Usage

```bash
cd infra/aws   # or infra/azure
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with real values — never commit this file
terraform init
terraform plan
terraform apply
```
