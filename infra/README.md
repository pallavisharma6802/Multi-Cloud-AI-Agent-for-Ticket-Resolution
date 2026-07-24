# Infrastructure (optional / legacy)

**Prefer the root `docker-compose.yml`** for local Postgres, Ollama, Grafana,
backend, and frontend. This Terraform is an optional/deprecated path for a
real cloud deployment (AWS RDS + EC2 Ollama, Azure Text Analytics). It is
not required and is not exercised by CI.

- `infra/aws/` — RDS Postgres + EC2 Ollama. Alternative to the Compose
  `postgres` / `ollama` services.
- `infra/azure/` — Azure Text Analytics (Cognitive Services). Needed for
  real NER/sentiment; no local equivalent. Uses the `F0` (free tier) SKU.

## Security notice

1. **Security groups must not be `0.0.0.0/0`.** Postgres (5432), SSH (22),
   and Ollama (11434) require an explicit `allowed_management_cidr_blocks`
   (no default — `terraform plan` fails until set to your IP/VPN CIDR).
   RDS `publicly_accessible` defaults to `false`.
2. **Never commit real `*.tfvars`.** `terraform.tfvars` files are gitignored;
   use `*.tfvars.example` templates. If an old password was ever committed
   and applied publicly, rotate the RDS password and consider purging it
   from git history.

## Usage

```bash
cd infra/aws   # or infra/azure
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with real values — never commit this file
terraform init
terraform plan
terraform apply
```
