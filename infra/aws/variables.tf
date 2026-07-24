variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "multi-cloud-ai-agent"
}

variable "db_username" {
  description = "RDS database username"
  type        = string
  default     = "postgres_admin"
  sensitive   = true
}

variable "db_password" {
  description = "RDS database password"
  type        = string
  sensitive   = true
}

# No default: forces an explicit CIDR so plan fails instead of opening 0.0.0.0/0.
variable "allowed_management_cidr_blocks" {
  description = <<-EOT
    CIDR blocks allowed for SSH (22), Ollama (11434), and Postgres (5432).
    Use your IP (/32) or VPN CIDR — never 0.0.0.0/0. Optional/legacy stack;
    prefer docker-compose.yml for local use. See infra/README.md.
  EOT
  type        = list(string)
}

variable "rds_publicly_accessible" {
  description = <<-EOT
    Whether RDS gets a public IP. Default false. If true (e.g. local backend
    against remote RDS), access is still gated by allowed_management_cidr_blocks.
  EOT
  type        = bool
  default     = false
}
