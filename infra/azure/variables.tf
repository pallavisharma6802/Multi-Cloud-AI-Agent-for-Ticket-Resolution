variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Azure resource group name"
  type        = string
  default     = "ai-agent-rg"
}

variable "azure_location" {
  description = "Azure location"
  type        = string
  default     = "eastus"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "multi-cloud-ai-agent"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}
