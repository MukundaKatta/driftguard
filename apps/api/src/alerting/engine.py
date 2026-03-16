"""Alert Evaluation Engine — Evaluates drift results and dispatches alerts."""

import logging
from datetime import datetime, timezone
from typing import Any
import uuid

from .slack import SlackNotifier
from .pagerduty import PagerDutyNotifier
from .email import EmailNotifier

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class AlertEngine:
    """Evaluates drift detection results against alert configurations and dispatches notifications.

    Supports multiple channels: Slack, PagerDuty, Email, and AWS SNS.
    Implements deduplication, severity thresholds, and cooldown periods.
    """

    def __init__(self):
        self.slack = SlackNotifier()
        self.pagerduty = PagerDutyNotifier()
        self.email = EmailNotifier()

    async def evaluate_and_send(
        self,
        workspace_id: str,
        model_endpoint_id: str,
        drift_result: dict[str, Any],
        pg: Any,
    ) -> list[dict[str, Any]]:
        """Evaluate a drift result against all matching alert configs and send alerts.

        Parameters
        ----------
        workspace_id : str
        model_endpoint_id : str
        drift_result : dict
            The drift detection result containing id, monitor_id, drift_type, score, details.
        pg : PostgresStorage
            Database access for alert configs and history.

        Returns
        -------
        list of sent alert records
        """
        configs = await pg.list_alert_configs(workspace_id, model_endpoint_id=model_endpoint_id)
        if not configs:
            return []

        severity = self._determine_severity(drift_result)
        sent_alerts: list[dict[str, Any]] = []

        for config in configs:
            config_severity = config.get("severity_threshold", "warning")
            if SEVERITY_ORDER.get(severity, 0) < SEVERITY_ORDER.get(config_severity, 1):
                continue

            # Check cooldown: prevent duplicate alerts within cooldown window
            cooldown_minutes = config.get("config", {}).get("cooldown_minutes", 30)
            recent_alert = await pg.get_recent_alert(
                config_id=config["id"],
                workspace_id=workspace_id,
                cooldown_minutes=cooldown_minutes,
            )
            if recent_alert:
                logger.info(
                    "Skipping alert for config %s (cooldown active, last sent: %s)",
                    config["id"],
                    recent_alert.get("created_at"),
                )
                continue

            message = self._format_message(drift_result, severity, model_endpoint_id)
            channel = config["channel"]
            destination = config["destination"]

            success = False
            error_msg = None

            try:
                if channel == "slack":
                    success = await self.slack.send(
                        webhook_url=destination,
                        message=message,
                        severity=severity,
                        config=config.get("config", {}),
                    )
                elif channel == "pagerduty":
                    success = await self.pagerduty.send(
                        routing_key=destination,
                        message=message,
                        severity=severity,
                        drift_result=drift_result,
                        config=config.get("config", {}),
                    )
                elif channel == "email":
                    success = await self.email.send(
                        to_address=destination,
                        message=message,
                        severity=severity,
                        drift_result=drift_result,
                        config=config.get("config", {}),
                    )
                elif channel == "sns":
                    success = await self._send_sns(
                        topic_arn=destination,
                        message=message,
                        severity=severity,
                    )
                else:
                    logger.warning("Unknown alert channel: %s", channel)
                    continue
            except Exception as exc:
                logger.error("Alert dispatch failed for channel %s: %s", channel, exc)
                error_msg = str(exc)
                success = False

            alert_record = {
                "id": str(uuid.uuid4()),
                "workspace_id": workspace_id,
                "alert_config_id": config["id"],
                "model_endpoint_id": model_endpoint_id,
                "drift_result_id": drift_result["id"],
                "channel": channel,
                "destination": destination,
                "severity": severity,
                "message": message["title"],
                "success": success,
                "error": error_msg,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            await pg.store_alert_history(alert_record)
            sent_alerts.append(alert_record)

        return sent_alerts

    def _determine_severity(self, drift_result: dict[str, Any]) -> str:
        """Determine alert severity based on drift score and type."""
        score = drift_result.get("score", 0)
        drift_type = drift_result.get("drift_type", "")

        # Higher scores = more severe drift
        if score >= 0.8:
            return "critical"
        elif score >= 0.4:
            return "warning"
        else:
            return "info"

    def _format_message(
        self,
        drift_result: dict[str, Any],
        severity: str,
        model_endpoint_id: str,
    ) -> dict[str, str]:
        """Format a human-readable alert message."""
        drift_type = drift_result.get("drift_type", "unknown")
        score = drift_result.get("score", 0)
        details = drift_result.get("details", {})

        severity_emoji = {"critical": "[CRITICAL]", "warning": "[WARNING]", "info": "[INFO]"}
        prefix = severity_emoji.get(severity, "[ALERT]")

        title = f"{prefix} Drift detected: {drift_type} (score: {score:.4f})"
        body_lines = [
            f"Model Endpoint: {model_endpoint_id}",
            f"Drift Type: {drift_type}",
            f"Drift Score: {score:.6f}",
            f"Severity: {severity.upper()}",
            f"Detected At: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "Details:",
        ]

        for key, value in details.items():
            if not isinstance(value, (list, dict)):
                body_lines.append(f"  {key}: {value}")

        return {
            "title": title,
            "body": "\n".join(body_lines),
            "severity": severity,
            "drift_type": drift_type,
            "score": str(score),
        }

    async def _send_sns(self, topic_arn: str, message: dict[str, str], severity: str) -> bool:
        """Send alert via AWS SNS."""
        import boto3

        try:
            sns = boto3.client("sns")
            response = sns.publish(
                TopicArn=topic_arn,
                Subject=message["title"][:100],
                Message=message["body"],
                MessageAttributes={
                    "severity": {"DataType": "String", "StringValue": severity},
                    "drift_type": {"DataType": "String", "StringValue": message.get("drift_type", "unknown")},
                },
            )
            return response.get("MessageId") is not None
        except Exception as exc:
            logger.error("SNS publish failed: %s", exc)
            raise
