"""DriftGuard API - ML Model Monitoring & Drift Detection Engine."""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .detectors.data_drift import DataDriftDetector
from .detectors.embedding_drift import EmbeddingDriftDetector
from .detectors.response_drift import ResponseDriftDetector
from .detectors.confidence_drift import ConfidenceDriftDetector
from .detectors.query_drift import QueryPatternDriftDetector
from .alerting.engine import AlertEngine
from .storage.postgres import PostgresStorage
from .storage.dynamo import DynamoStorage

app = FastAPI(
    title="DriftGuard API",
    version="1.0.0",
    description="ML Model Monitoring & Drift Detection Engine",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pg = PostgresStorage()
dynamo = DynamoStorage()
alert_engine = AlertEngine()

data_drift_detector = DataDriftDetector()
embedding_drift_detector = EmbeddingDriftDetector()
response_drift_detector = ResponseDriftDetector()
confidence_drift_detector = ConfidenceDriftDetector()
query_drift_detector = QueryPatternDriftDetector()

DETECTORS = {
    "data_drift": data_drift_detector,
    "embedding_drift": embedding_drift_detector,
    "response_drift": response_drift_detector,
    "confidence_drift": confidence_drift_detector,
    "query_drift": query_drift_detector,
}


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

async def get_workspace_id(authorization: str = Header(...)) -> str:
    """Extract workspace id from a bearer token via Supabase JWT."""
    token = authorization.replace("Bearer ", "")
    workspace = await pg.get_workspace_from_token(token)
    if not workspace:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return workspace["id"]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RegisterModelRequest(BaseModel):
    name: str
    platform: str = Field(..., description="bedrock | sagemaker | openai | custom")
    endpoint_url: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class RegisterModelResponse(BaseModel):
    id: str
    name: str
    platform: str
    api_key: str


class CreateMonitorRequest(BaseModel):
    model_endpoint_id: str
    drift_type: str = Field(..., description="data_drift | embedding_drift | response_drift | confidence_drift | query_drift")
    config: dict = Field(default_factory=dict)
    schedule_minutes: int = 60


class CreateMonitorResponse(BaseModel):
    id: str
    model_endpoint_id: str
    drift_type: str
    status: str


class IngestRequest(BaseModel):
    model_endpoint_id: str
    features: Optional[list[list[float]]] = None
    embeddings: Optional[list[list[float]]] = None
    predictions: Optional[list[float]] = None
    confidences: Optional[list[float]] = None
    queries: Optional[list[str]] = None
    timestamp: Optional[str] = None


class RunDriftRequest(BaseModel):
    monitor_id: str


class SetBaselineRequest(BaseModel):
    model_endpoint_id: str
    drift_type: str
    features: Optional[list[list[float]]] = None
    embeddings: Optional[list[list[float]]] = None
    predictions: Optional[list[float]] = None
    confidences: Optional[list[float]] = None
    queries: Optional[list[str]] = None


class AlertConfigRequest(BaseModel):
    model_endpoint_id: str
    channel: str = Field(..., description="slack | pagerduty | email | sns")
    destination: str
    severity_threshold: str = "warning"
    config: dict = Field(default_factory=dict)


class DriftResultResponse(BaseModel):
    id: str
    monitor_id: str
    drift_type: str
    is_drifted: bool
    score: float
    details: dict
    created_at: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Model endpoints
# ---------------------------------------------------------------------------

@app.post("/api/v1/models", response_model=RegisterModelResponse)
async def register_model(
    req: RegisterModelRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    model_id = str(uuid.uuid4())
    api_key = f"dg_{uuid.uuid4().hex}"
    await pg.create_model_endpoint(
        id=model_id,
        workspace_id=workspace_id,
        name=req.name,
        platform=req.platform,
        endpoint_url=req.endpoint_url,
        metadata=req.metadata,
        api_key=api_key,
    )
    return RegisterModelResponse(id=model_id, name=req.name, platform=req.platform, api_key=api_key)


@app.get("/api/v1/models")
async def list_models(workspace_id: str = Depends(get_workspace_id)):
    models = await pg.list_model_endpoints(workspace_id)
    return {"models": models}


@app.get("/api/v1/models/{model_id}")
async def get_model(model_id: str, workspace_id: str = Depends(get_workspace_id)):
    model = await pg.get_model_endpoint(model_id, workspace_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@app.delete("/api/v1/models/{model_id}")
async def delete_model(model_id: str, workspace_id: str = Depends(get_workspace_id)):
    await pg.delete_model_endpoint(model_id, workspace_id)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Monitors
# ---------------------------------------------------------------------------

@app.post("/api/v1/monitors", response_model=CreateMonitorResponse)
async def create_monitor(
    req: CreateMonitorRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    if req.drift_type not in DETECTORS:
        raise HTTPException(status_code=400, detail=f"Unknown drift type: {req.drift_type}")
    monitor_id = str(uuid.uuid4())
    await pg.create_monitor(
        id=monitor_id,
        workspace_id=workspace_id,
        model_endpoint_id=req.model_endpoint_id,
        drift_type=req.drift_type,
        config=req.config,
        schedule_minutes=req.schedule_minutes,
    )
    return CreateMonitorResponse(
        id=monitor_id,
        model_endpoint_id=req.model_endpoint_id,
        drift_type=req.drift_type,
        status="active",
    )


@app.get("/api/v1/monitors")
async def list_monitors(workspace_id: str = Depends(get_workspace_id)):
    monitors = await pg.list_monitors(workspace_id)
    return {"monitors": monitors}


@app.get("/api/v1/monitors/{monitor_id}")
async def get_monitor(monitor_id: str, workspace_id: str = Depends(get_workspace_id)):
    monitor = await pg.get_monitor(monitor_id, workspace_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


@app.delete("/api/v1/monitors/{monitor_id}")
async def delete_monitor(monitor_id: str, workspace_id: str = Depends(get_workspace_id)):
    await pg.delete_monitor(monitor_id, workspace_id)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

@app.post("/api/v1/baselines")
async def set_baseline(
    req: SetBaselineRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    baseline_id = str(uuid.uuid4())
    payload: dict = {
        "features": req.features,
        "embeddings": req.embeddings,
        "predictions": req.predictions,
        "confidences": req.confidences,
        "queries": req.queries,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    await pg.upsert_baseline(
        id=baseline_id,
        workspace_id=workspace_id,
        model_endpoint_id=req.model_endpoint_id,
        drift_type=req.drift_type,
        data=payload,
    )
    return {"id": baseline_id, "status": "created"}


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

@app.post("/api/v1/ingest")
async def ingest_data(req: IngestRequest, workspace_id: str = Depends(get_workspace_id)):
    ts = req.timestamp or datetime.now(timezone.utc).isoformat()
    record_id = str(uuid.uuid4())
    payload: dict = {
        "features": req.features,
        "embeddings": req.embeddings,
        "predictions": req.predictions,
        "confidences": req.confidences,
        "queries": req.queries,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    await dynamo.put_metrics(
        record_id=record_id,
        model_endpoint_id=req.model_endpoint_id,
        workspace_id=workspace_id,
        timestamp=ts,
        data=payload,
    )
    return {"id": record_id, "status": "ingested"}


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

@app.post("/api/v1/drift/run", response_model=DriftResultResponse)
async def run_drift_detection(
    req: RunDriftRequest,
    background_tasks: BackgroundTasks,
    workspace_id: str = Depends(get_workspace_id),
):
    monitor = await pg.get_monitor(req.monitor_id, workspace_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    drift_type = monitor["drift_type"]
    detector = DETECTORS.get(drift_type)
    if not detector:
        raise HTTPException(status_code=400, detail=f"No detector for type: {drift_type}")

    baseline = await pg.get_baseline(monitor["model_endpoint_id"], drift_type, workspace_id)
    if not baseline:
        raise HTTPException(status_code=400, detail="No baseline set for this model/drift type")

    recent_data = await dynamo.get_recent_metrics(
        model_endpoint_id=monitor["model_endpoint_id"],
        workspace_id=workspace_id,
        limit=monitor.get("config", {}).get("window_size", 1000),
    )
    if not recent_data:
        raise HTTPException(status_code=400, detail="No recent data to compare against baseline")

    result = detector.detect(
        baseline_data=baseline["data"],
        current_data=recent_data,
        config=monitor.get("config", {}),
    )

    result_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await pg.store_drift_result(
        id=result_id,
        monitor_id=req.monitor_id,
        workspace_id=workspace_id,
        drift_type=drift_type,
        is_drifted=result["is_drifted"],
        score=result["score"],
        details=result["details"],
    )

    if result["is_drifted"]:
        background_tasks.add_task(
            alert_engine.evaluate_and_send,
            workspace_id=workspace_id,
            model_endpoint_id=monitor["model_endpoint_id"],
            drift_result={
                "id": result_id,
                "monitor_id": req.monitor_id,
                "drift_type": drift_type,
                "score": result["score"],
                "details": result["details"],
            },
            pg=pg,
        )

    return DriftResultResponse(
        id=result_id,
        monitor_id=req.monitor_id,
        drift_type=drift_type,
        is_drifted=result["is_drifted"],
        score=result["score"],
        details=result["details"],
        created_at=now,
    )


@app.get("/api/v1/drift/results")
async def list_drift_results(
    model_endpoint_id: Optional[str] = None,
    monitor_id: Optional[str] = None,
    limit: int = 50,
    workspace_id: str = Depends(get_workspace_id),
):
    results = await pg.list_drift_results(
        workspace_id=workspace_id,
        model_endpoint_id=model_endpoint_id,
        monitor_id=monitor_id,
        limit=limit,
    )
    return {"results": results}


@app.get("/api/v1/drift/results/{result_id}")
async def get_drift_result(result_id: str, workspace_id: str = Depends(get_workspace_id)):
    result = await pg.get_drift_result(result_id, workspace_id)
    if not result:
        raise HTTPException(status_code=404, detail="Drift result not found")
    return result


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@app.post("/api/v1/alerts/config")
async def create_alert_config(
    req: AlertConfigRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    config_id = str(uuid.uuid4())
    await pg.create_alert_config(
        id=config_id,
        workspace_id=workspace_id,
        model_endpoint_id=req.model_endpoint_id,
        channel=req.channel,
        destination=req.destination,
        severity_threshold=req.severity_threshold,
        config=req.config,
    )
    return {"id": config_id, "status": "created"}


@app.get("/api/v1/alerts/config")
async def list_alert_configs(workspace_id: str = Depends(get_workspace_id)):
    configs = await pg.list_alert_configs(workspace_id)
    return {"configs": configs}


@app.delete("/api/v1/alerts/config/{config_id}")
async def delete_alert_config(config_id: str, workspace_id: str = Depends(get_workspace_id)):
    await pg.delete_alert_config(config_id, workspace_id)
    return {"status": "deleted"}


@app.get("/api/v1/alerts/history")
async def list_alert_history(
    model_endpoint_id: Optional[str] = None,
    limit: int = 50,
    workspace_id: str = Depends(get_workspace_id),
):
    history = await pg.list_alert_history(
        workspace_id=workspace_id,
        model_endpoint_id=model_endpoint_id,
        limit=limit,
    )
    return {"history": history}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@app.get("/api/v1/reports/{model_endpoint_id}")
async def get_drift_report(
    model_endpoint_id: str,
    days: int = 30,
    workspace_id: str = Depends(get_workspace_id),
):
    results = await pg.get_drift_results_for_period(
        workspace_id=workspace_id,
        model_endpoint_id=model_endpoint_id,
        days=days,
    )
    summary: dict = {
        "model_endpoint_id": model_endpoint_id,
        "period_days": days,
        "total_checks": len(results),
        "drift_detected_count": sum(1 for r in results if r["is_drifted"]),
        "by_type": {},
    }
    for r in results:
        dt = r["drift_type"]
        if dt not in summary["by_type"]:
            summary["by_type"][dt] = {"checks": 0, "drifted": 0, "avg_score": 0.0, "scores": []}
        summary["by_type"][dt]["checks"] += 1
        if r["is_drifted"]:
            summary["by_type"][dt]["drifted"] += 1
        summary["by_type"][dt]["scores"].append(r["score"])

    for dt_info in summary["by_type"].values():
        scores = dt_info.pop("scores")
        dt_info["avg_score"] = round(sum(scores) / len(scores), 4) if scores else 0.0

    return summary
