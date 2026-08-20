# Infrastructure

`infra/azure/` provisions Azure Text Analytics (Cognitive Services), used
by this app for NER/sentiment. Uses the `F0` (free tier) SKU. Not used by
the app's own Compose stack (`docker-compose.yml`), which handles the
rest locally with Bedrock for inference.

## Security notice

1. **Security groups must not be `0.0.0.0/0`.** Any exposed port requires
   an explicit CIDR allowlist — never a default-open rule.
2. **Never commit real `*.tfvars` or `*.pem` files.** Both are gitignored;
   use the `*.tfvars.example` templates. If a real password was ever
   committed and applied publicly, rotate it and consider purging it from
   git history.

## Usage

```bash
cd infra/azure
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with real values — never commit this file
terraform init
terraform plan
terraform apply
```
