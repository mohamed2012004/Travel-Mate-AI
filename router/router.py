from pathlib import Path
import traceback

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database.base_database import RateLimitRecord, UserRecord
from utils.auth import get_current_user
from utils.backend_helpers import run_travel_agent
from utils.rate_limit import RATE_LIMIT_REQUESTS, enforce_rate_limit

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


class TravelRequest(BaseModel):
    message: str
    thread_id: str | None = None
    run_id: str | None = None


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@router.post("/api/travel")
async def travel_planner(
    request_data: TravelRequest,
    current_user: UserRecord = Depends(get_current_user),
    rate_limit: RateLimitRecord = Depends(enforce_rate_limit),
):
    try:
        user_message = request_data.message.strip()
        if not user_message:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Message cannot be empty."
                }
            )
        result = await run_travel_agent(
            user_input=user_message,
            thread_id=request_data.thread_id,
            run_id=request_data.run_id
        )
        return JSONResponse(
            headers={
                "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS),
                "X-RateLimit-Remaining": str(max(0, RATE_LIMIT_REQUESTS - (rate_limit.request_count if rate_limit else 0))),
            },
            content={
                "success": True,
                "thread_id": result["thread_id"],
                "run_id": result["run_id"],
                "intent": result.get("intent", ""),
                "intent_decision": result.get("intent_decision", {}),
                "answer": result["answer"],
                "flight_results": result["flight_results"],
                "hotel_results": result["hotel_results"],
                "itinerary": result["itinerary"],
                "llm_calls": result["llm_calls"],
            }
        )
    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@router.get("/health")
async def health_check(request: Request):
    return {
        "status": "ok",
        "message": "AI Travel Planner API is running",
        "database": getattr(request.app.state, "database_report", {"connected": False})
    }


@router.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})
