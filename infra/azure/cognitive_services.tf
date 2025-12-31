terraform {
  required_version = ">= 1.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.azure_subscription_id
}

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.azure_location
}

resource "azurerm_cognitive_account" "text_analytics" {
  name                = "ai-nlp-agent"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  kind                = "TextAnalytics"
  sku_name            = "F0"

  tags = {
    Environment = var.environment
  }
}

output "text_analytics_endpoint" {
  value       = azurerm_cognitive_account.text_analytics.endpoint
  description = "Azure Text Analytics endpoint"
}

output "text_analytics_key" {
  value       = azurerm_cognitive_account.text_analytics.primary_access_key
  description = "Azure Text Analytics API key"
  sensitive   = true
}
