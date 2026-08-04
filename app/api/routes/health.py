from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    payload = {
        "status": "healthy",
        "service": "multi-cloud-ai-agent",
    }
    try:
        from app.llm.model_router import routing_summary

        payload["model_routing"] = routing_summary()
    except Exception:
        payload["model_routing"] = None
    return payload


@router.get("/ping")
async def ping():
    return {"message": "pong"}
