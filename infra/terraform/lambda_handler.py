"""Lambda Handler — Scheduled drift detection runner.

Invoked by EventBridge on a schedule (every 15 minutes).
Queries all active monitors whose next_run_at is in the past,
runs drift detection, stores results, and sends alerts.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda entry point for scheduled drift detection.

    Parameters
    ----------
    event : dict
        EventBridge event payload.
    context : LambdaContext
        AWS Lambda context object.
    """
    logger.info("Drift detection scheduled run started: %s", json.dumps(event))
    result = asyncio.get_event_loop().run_until_complete(_run_scheduled_checks())
    return result


async def _run_scheduled_checks() -> dict:
    """Run all due drift detection monitors."""
    # Import here to ensure Lambda environment variables are set
    from src.storage.postgres import PostgresStorage
    from src.storage.dynamo import DynamoStorage
    from src.detectors.data_drift import DataDriftDetector
    from src.detectors.embedding_drift import EmbeddingDriftDetector
    from src.detectors.response_drift import ResponseDriftDetector
    from src.detectors.confidence_drift import ConfidenceDriftDetector
    from src.detectors.query_drift import QueryPatternDriftDetector
    from src.alerting.engine import AlertEngine

    import uuid

    pg = PostgresStorage()
    dynamo = DynamoStorage()
    alert_engine = AlertEngine()

    detectors = {
        "data_drift": DataDriftDetector(),
        "embedding_drift": EmbeddingDriftDetector(),
        "response_drift": ResponseDriftDetector(),
        "confidence_drift": ConfidenceDriftDetector(),
        "query_drift": QueryPatternDriftDetector(),
    }

    now = datetime.now(timezone.utc)
    checks_run = 0
    drift_detected = 0
    errors = 0

    # Fetch all active monitors that are due to run
    # Using service-level access (not user-scoped)
    try:
        result = (
            pg.client.table("monitors")
            .select("*, model_endpoints!inner(workspace_id)")
            .eq("status", "active")
            .lte("next_run_at", now.isoformat())
            .execute()
        )
        due_monitors = result.data or []
    except Exception as exc:
        logger.error("Failed to fetch due monitors: %s", exc)
        # Fallback: get all active monitors
        result = (
            pg.client.table("monitors")
            .select("*, model_endpoints!inner(workspace_id)")
            .eq("status", "active")
            .execute()
        )
        due_monitors = result.data or []

    logger.info("Found %d monitors due for checking", len(due_monitors))

    for monitor in due_monitors:
        monitor_id = monitor["id"]
        workspace_id = monitor.get("model_endpoints", {}).get("workspace_id", monitor.get("workspace_id"))
        drift_type = monitor["drift_type"]
        model_endpoint_id = monitor["model_endpoint_id"]

        config = monitor.get("config", {})
        if isinstance(config, str):
            config = json.loads(config)

        detector = detectors.get(drift_type)
        if not detector:
            logger.warning("Unknown drift type %s for monitor %s", drift_type, monitor_id)
            continue

        try:
            # Get baseline
            baseline = await pg.get_baseline(model_endpoint_id, drift_type, workspace_id)
            if not baseline:
                logger.info("No baseline for monitor %s, skipping", monitor_id)
                continue

            # Get recent data
            window_size = config.get("window_size", 1000)
            recent_data = await dynamo.get_recent_metrics(
                model_endpoint_id=model_endpoint_id,
                workspace_id=workspace_id,
                limit=window_size,
            )

            if not recent_data:
                logger.info("No recent data for monitor %s, skipping", monitor_id)
                continue

            # Run detection
            detection_result = detector.detect(
                baseline_data=baseline["data"],
                current_data=recent_data,
                config=config,
            )

            checks_run += 1

            # Store result
            result_id = str(uuid.uuid4())
            await pg.store_drift_result(
                id=result_id,
                monitor_id=monitor_id,
                workspace_id=workspace_id,
                drift_type=drift_type,
                is_drifted=detection_result["is_drifted"],
                score=detection_result["score"],
                details=detection_result["details"],
            )

            if detection_result["is_drifted"]:
                drift_detected += 1
                logger.warning(
                    "Drift detected: monitor=%s, type=%s, score=%.4f",
                    monitor_id,
                    drift_type,
                    detection_result["score"],
                )

                # Send alerts
                await alert_engine.evaluate_and_send(
                    workspace_id=workspace_id,
                    model_endpoint_id=model_endpoint_id,
                    drift_result={
                        "id": result_id,
                        "monitor_id": monitor_id,
                        "drift_type": drift_type,
                        "score": detection_result["score"],
                        "details": detection_result["details"],
                    },
                    pg=pg,
                )

            # Update monitor next_run_at
            schedule_minutes = monitor.get("schedule_minutes", 60)
            from datetime import timedelta
            next_run = now + timedelta(minutes=schedule_minutes)
            pg.client.table("monitors").update({
                "last_run_at": now.isoformat(),
                "next_run_at": next_run.isoformat(),
            }).eq("id", monitor_id).execute()

        except Exception as exc:
            errors += 1
            logger.error("Monitor %s failed: %s", monitor_id, exc, exc_info=True)

    summary = {
        "status": "completed",
        "timestamp": now.isoformat(),
        "monitors_checked": len(due_monitors),
        "checks_run": checks_run,
        "drift_detected": drift_detected,
        "errors": errors,
    }
    logger.info("Drift detection run completed: %s", json.dumps(summary))
    return summary
