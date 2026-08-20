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
    CIDR blocks allowed for SSH (22, app EC2) and direct Postgres access (5432,
    RDS). Use your IP (/32) or VPN CIDR — never 0.0.0.0/0. The app's own HTTP
    port (var.app_port) is intentionally NOT restricted by this -- it's a
    public web app. See infra/README.md.
  EOT
  type        = list(string)
}

variable "rds_publicly_accessible" {
  description = <<-EOT
    Whether RDS gets a public IP. Default false -- the app reaches it over
    the private network (see aws_security_group.rds). If true (e.g. direct
    access from your own machine), access is still gated by
    allowed_management_cidr_blocks.
  EOT
  type        = bool
  default     = false
}

variable "app_port" {
  description = "Port the travel_booking app listens on and is reachable from the internet on"
  type        = number
  default     = 8200
}
