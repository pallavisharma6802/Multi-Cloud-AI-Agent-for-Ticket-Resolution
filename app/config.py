from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional
import os


class Settings(BaseSettings):
    
    env: str = Field(default="dev", description="Environment name")
    project_name: str = Field(default="multi-cloud-ai-agent")
    
    aws_region: str = Field(..., description="AWS region for resources")
    aws_access_key_id: str = Field(..., description="AWS access key")
    aws_secret_access_key: str = Field(..., description="AWS secret key")
    aws_bedrock_model_id: Optional[str] = Field(None, description="Bedrock model ID if used")
    
    azure_subscription_id: str = Field(..., description="Azure subscription ID")
    azure_resource_group: str = Field(..., description="Azure resource group")
    azure_location: str = Field(default="eastus", description="Azure region")
    azure_text_analytics_endpoint: str = Field(..., description="Azure Text Analytics endpoint URL")
    azure_text_analytics_key: str = Field(..., description="Azure Text Analytics API key")
    
    gcp_project_id: str = Field(..., description="GCP project ID")
    gcp_region: str = Field(default="us-central1", description="GCP region")
    google_application_credentials: str = Field(..., description="Path to GCP service account key")
    
    pinecone_api_key: str = Field(..., description="Pinecone API key")
    pinecone_environment: str = Field(..., description="Pinecone environment")
    pinecone_index_name: str = Field(default="ticket-kb", description="Pinecone index name")
    
    ollama_base_url: str = Field(..., description="Ollama server URL on EC2")
    
    database_url: str = Field(..., description="PostgreSQL connection string")
    
    kb_backend: str = Field(default="local", description="Knowledge base backend type")
    kb_path: str = Field(default="./knowledge_base", description="Path to local KB files")
    
    log_level: str = Field(default="INFO", description="Logging level")
    request_timeout_seconds: int = Field(default=30, description="HTTP request timeout")
    
    @field_validator("google_application_credentials")
    def validate_gcp_credentials(cls, v):
        if not os.path.exists(v):
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
