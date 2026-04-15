from fastapi import APIRouter

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/hello")
async def hello() -> dict[str, str]:
    return {"message": "Hello from Verida-Backend"}
