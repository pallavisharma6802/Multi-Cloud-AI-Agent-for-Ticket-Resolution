import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, tickets
from app.config import settings

logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.project_name,
    description="Multi-Cloud AI Agent for Automated Ticket Resolution",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(tickets.router, prefix="/api/v1", tags=["Tickets"])


@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.project_name} in {settings.env} environment")
    logger.info(f"Azure endpoint: {settings.azure_text_analytics_endpoint}")
    logger.info(f"Bedrock region: {settings.aws_region}")

    # Bridge the parsed .env value into the real process env var -- google-cloud
    # libraries' ADC resolution reads os.environ directly, not pydantic-settings.
    if settings.google_application_credentials:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.google_application_credentials)

    # Create missing tables (idempotent).
    from app.db.init_db import init_db

    init_db()
    logger.info("Database schema verified/created")

    try:
        from app.llm.model_router import routing_summary

        summary = routing_summary()
        logger.info(
            f"LLM backend={summary['backend']} region={summary['region']} "
            f"assignments={summary['assignments']}"
        )
    except Exception as e:
        logger.warning(f"Model routing summary unavailable: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
