"""PagerDuty Notifier — Create incidents and send alerts via PagerDuty Events API v2."""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EVENTS_API_URL = "https://events.pagerduty.com/v2/enqueue"

SEVERITY_MAP = {
    "critical": "critical",
    "warning": "warning",
    "info": "info",
}


class PagerDutyNotifier:
    """Creates PagerDuty incidents for drift alerts via the Events API v2."""

    async def send(
        self,
        routing_key: str,
        message: dict[str, str],
        severity: str = "warning",
        drift_result: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Send an alert to PagerDuty.

        Parameters
        ----------
        routing_key : str
            PagerDuty Events API v2 routing key (integration key).
        message : dict
            Must contain "title" and "body".
        severity : str
            One of: info, warning, critical.
        drift_result : dict, optional
            Full drift result for custom details.
        config : dict, optional
            Additional config: source, component, group, class_type, dedup_key.

        Returns
        -------
        bool indicating success.
        """
        config = config or {}
        drift_result = drift_result or {}

        pd_severity = SEVERITY_MAP.get(severity, "warning")

        dedup_key = config.get("dedup_key")
        if not dedup_key:
            monitor_id = drift_result.get("monitor_id", "unknown")
            drift_type = drift_result.get("drift_type", "unknown")
            dedup_key = f"driftguard-{monitor_id}-{drift_type}"

        custom_details: dict[str, Any] = {
            "drift_type": drift_result.get("drift_type", "unknown"),
            "drift_score": drift_result.get("score", 0),
            "monitor_id": drift_result.get("monitor_id", "unknown"),
            "result_id": drift_result.get("id", "unknown"),
        }

        details = drift_result.get("details", {})
        for key, value in details.items():
            if not isinstance(value, (list, dict)):
                custom_details[key] = value

        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "dedup_key": dedup_key,
            "payload": {
                "summary": message["title"][:1024],
                "source": config.get("source", "driftguard"),
                "severity": pd_severity,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "component": config.get("component", "drift-detection"),
                "group": config.get("group", "ml-monitoring"),
                "class": config.get("class_type", drift_result.get("drift_type", "drift")),
                "custom_details": custom_details,
            },
        }

        if config.get("dashboard_url"):
            payload["links"] = [
                {
                    "href": config["dashboard_url"],
                    "text": "View in DriftGuard Dashboard",
                },
            ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(EVENTS_API_URL, json=payload)
                if response.status_code == 202:
                    resp_data = response.json()
                    logger.info(
                        "PagerDuty incident created: dedup_key=%s, status=%s",
                        dedup_key,
                        resp_data.get("status"),
                    )
                    return True
                else:
                    logger.error(
                        "PagerDuty API returned status %d: %s",
                        response.status_code,
                        response.text,
                    )
                    return False
        except httpx.HTTPError as exc:
            logger.error("PagerDuty notification failed: %s", exc)
            raise

    async def resolve(
        self,
        routing_key: str,
        dedup_key: str,
    ) -> bool:
        """Resolve a previously triggered PagerDuty incident.

        Parameters
        ----------
        routing_key : str
            PagerDuty routing key.
        dedup_key : str
            Deduplication key of the incident to resolve.

        Returns
        -------
        bool indicating success.
        """
        payload = {
            "routing_key": routing_key,
            "event_action": "resolve",
            "dedup_key": dedup_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(EVENTS_API_URL, json=payload)
                if response.status_code == 202:
                    logger.info("PagerDuty incident resolved: dedup_key=%s", dedup_key)
                    return True
                else:
                    logger.error(
                        "PagerDuty resolve returned status %d: %s",
                        response.status_code,
                        response.text,
                    )
                    return False
        except httpx.HTTPError as exc:
            logger.error("PagerDuty resolve failed: %s", exc)
            raise
