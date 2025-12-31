from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "multi-cloud-ai-agent"
    }


@router.get("/ping")
async def ping():
    return {"message": "pong"}
