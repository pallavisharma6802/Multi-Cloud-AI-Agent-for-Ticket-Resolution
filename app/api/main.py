from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import tickets, health
from app.config import settings
import logging

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
    logger.info(f"Ollama URL: {settings.ollama_base_url}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
