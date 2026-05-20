# """"
# PinTrace IDE Backend
# Provides endpoints to compile + run C code through Intel Pin tool memtrace.
# Falls back to a simulation engine if Pin is not installed (cloud demo).
# Also serves the updated Pin tool source + Windows setup README as downloads.
# """
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

from sim_engine import simulate_pin_run, build_csv_report
from pin_runner import try_real_pin_run

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="PinTrace IDE")
api_router = APIRouter(prefix="/api")

PINTOOL_DIR = ROOT_DIR / "pintool"


# ---------------- Models ---------------- #
class RunRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str
    filename: Optional[str] = "main.c"
    use_real_pin: Optional[bool] = False  # if True and PIN_ROOT set, attempts real Pin run


class LeakMarker(BaseModel):
    line: int
    col: int
    end_line: int
    end_col: int
    severity: str  # "error" | "warning" | "info"
    message: str
    size: int
    address: str
    caller_ip: str


class AllocationEvent(BaseModel):
    op: str            # malloc | calloc | realloc | free | aligned_alloc | posix_memalign
    line: int
    address: str
    size: int
    caller_ip: str
    leaked: bool
    timestamp_ms: int


class RunResponse(BaseModel):
    id: str
    success: bool
    mode: str  # "real-pin" | "simulation"
    memtrace_out: str
    csv_report: str
    stdout: str
    stderr: str
    stats: Dict[str, Any]
    events: List[AllocationEvent]
    markers: List[LeakMarker]
    per_callsite: List[Dict[str, Any]]
    leaks: List[Dict[str, Any]]


# ---------------- Routes ---------------- #
@api_router.get("/")
async def root():
    return {"service": "PinTrace IDE", "status": "online"}


@api_router.get("/health")
async def health():
    pin_available = bool(os.environ.get('PIN_ROOT'))
    return {"ok": True, "pin_available": pin_available}


@api_router.post("/run", response_model=RunResponse)
async def run_code(req: RunRequest):
    if not req.code or not req.code.strip():
        raise HTTPException(status_code=400, detail="Empty code")

    run_id = str(uuid.uuid4())
    pin_root = os.environ.get('PIN_ROOT')

    real_attempted = False
    real_result = None
    print(pin_root)
    if pin_root:
        print("yea we tried")
        real_attempted = True
        try:
            print("yea we tried p2")
            real_result = try_real_pin_run(req.code, run_id, pin_root)
        except Exception as e:
            print("fail")
            real_result = None
            logging.exception("Real pin run failed: %s", e)

    if real_result is not None:
        print("good thing!")
        result = real_result
        mode = "real-pin"
    else:
        print("bad thing!")
        result = simulate_pin_run(req.code)
        mode = "simulation"

    csv = build_csv_report(result)

    # Persist a small record (no _id leaks)
    try:
        await db.runs.insert_one({
            "id": run_id,
            "filename": req.filename,
            "mode": mode,
            "stats": result["stats"],
            "leak_count": len(result["leaks"]),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    return RunResponse(
        id=run_id,
        success=True,
        mode=mode,
        memtrace_out=result["memtrace_out"],
        csv_report=csv,
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        stats=result["stats"],
        events=[AllocationEvent(**e) for e in result["events"]],
        markers=[LeakMarker(**m) for m in result["markers"]],
        per_callsite=result["per_callsite"],
        leaks=result["leaks"],
    )


@api_router.get("/recent-runs")
async def recent_runs():
    docs = await db.runs.find({}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return docs


@api_router.get("/pintool/source", response_class=PlainTextResponse)
async def get_pintool_source():
    p = PINTOOL_DIR / "memtrace.cpp"
    if not p.exists():
        raise HTTPException(404, "Pin tool source missing")
    return p.read_text()


@api_router.get("/pintool/readme", response_class=PlainTextResponse)
async def get_pintool_readme():
    p = PINTOOL_DIR / "README_WINDOWS.md"
    if not p.exists():
        raise HTTPException(404, "README missing")
    return p.read_text()


@api_router.get("/pintool/makefile", response_class=PlainTextResponse)
async def get_pintool_makefile():
    p = PINTOOL_DIR / "makefile.rules"
    if not p.exists():
        raise HTTPException(404, "Makefile missing")
    return p.read_text()


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
