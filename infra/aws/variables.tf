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
