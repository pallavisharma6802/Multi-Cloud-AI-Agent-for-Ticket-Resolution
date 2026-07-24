import os
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = Field(default="dev", description="Environment name")
    project_name: str = Field(default="multi-cloud-ai-agent")

    # AWS / Azure account IDs (Terraform / infra only; unused at runtime)
    aws_region: Optional[str] = Field(default=None, description="AWS region (Terraform-only; unused at runtime)")
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS access key (Terraform-only; unused at runtime)")
    aws_secret_access_key: Optional[str] = Field(default=None, description="AWS secret key (Terraform-only; unused at runtime)")
    aws_bedrock_model_id: Optional[str] = Field(None, description="Bedrock model ID if used")

    azure_subscription_id: Optional[str] = Field(default=None, description="Azure subscription ID (Terraform-only; unused at runtime)")
    azure_resource_group: Optional[str] = Field(default=None, description="Azure resource group (Terraform-only; unused at runtime)")
    azure_location: str = Field(default="eastus", description="Azure region")
    # Required at runtime for Azure Text Analytics
    azure_text_analytics_endpoint: str = Field(..., description="Azure Text Analytics endpoint URL")
    azure_text_analytics_key: str = Field(..., description="Azure Text Analytics API key")

    # Fallback GCP project for the opt-in BigQuery sink
    gcp_project_id: Optional[str] = Field(default=None, description="GCP project ID (used by the opt-in BigQuery sink)")
    gcp_region: str = Field(default="us-central1", description="GCP region")
    # Optional path; ADC also reads GOOGLE_APPLICATION_CREDENTIALS from the env
    google_application_credentials: Optional[str] = Field(default=None, description="Path to GCP service account key (optional)")
    
    pinecone_api_key: str = Field(..., description="Pinecone API key")
    pinecone_environment: str = Field(..., description="Pinecone environment")
    pinecone_index_name: str = Field(default="ticket-kb", description="Pinecone index name")
    
    ollama_base_url: str = Field(..., description="Ollama server URL on EC2")
    
    database_url: str = Field(..., description="PostgreSQL connection string")
    
    kb_backend: str = Field(default="local", description="Knowledge base backend type")
    kb_path: str = Field(default="./knowledge_base", description="Path to local KB files")
    
    log_level: str = Field(default="INFO", description="Logging level")
    request_timeout_seconds: int = Field(default=30, description="HTTP request timeout")

    # Domain pack
    domain_pack: str = Field(
        default="it_saas",
        description="Active domain pack id (directory name under domains/)",
    )
    domains_root: str = Field(default="domains", description="Root directory holding domain packs")

    # Per-role models (swap one agent without touching others)
    model_intent_priority: str = Field(default="qwen2.5:3b")
    model_grader: str = Field(default="qwen2.5:3b")
    model_judge: str = Field(default="qwen2.5:3b")
    model_continuation: str = Field(default="qwen2.5:3b")
    model_drafting: str = Field(default="qwen2.5:3b")
    model_supervisor: str = Field(default="qwen2.5:3b")

    # Hard caps on cost/latency if a graph loop runs away (not business rules)
    max_iterations: int = Field(
        default=10, description="Absolute hard ceiling on graph loop iterations per ticket"
    )
    max_wall_clock_seconds: int = Field(
        default=300, description="Absolute hard ceiling on wall-clock time per ticket"
    )

    # BigQuery analytics sink
    enable_bigquery: bool = Field(default=False, description="Enable async BigQuery event sink")
    bigquery_project_id: Optional[str] = Field(default=None)
    bigquery_dataset: str = Field(default="ticket_analytics")
    bigquery_table: str = Field(default="fact_ticket_events")

    @field_validator("google_application_credentials")
    def validate_gcp_credentials(cls, v):
        if v and not os.path.exists(v):
            raise ValueError(f"GCP credentials file not found at {v}")
        return v
    
    @field_validator("log_level")
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
