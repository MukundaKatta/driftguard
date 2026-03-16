"""Reporter — Generate drift detection reports and summaries."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("driftguard.reporter")


class Reporter:
    """Generates and retrieves drift detection reports from the DriftGuard API.

    Provides methods for fetching drift summaries, generating trend analysis,
    and formatting reports for consumption by dashboards or alerting systems.

    Parameters
    ----------
    api_key : str
        DriftGuard API key.
    endpoint : str
        Base URL of the DriftGuard API.
    """

    def __init__(self, api_key: str, endpoint: str = "https://api.driftguard.io"):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
        return self._client

    def get_model_report(self, model_id: str, days: int = 30) -> dict[str, Any]:
        """Get a drift summary report for a model endpoint.

        Parameters
        ----------
        model_id : str
            Model endpoint ID.
        days : int
            Number of days to cover.

        Returns
        -------
        dict with drift summary including:
        - total_checks: number of drift checks in period
        - drift_detected_count: how many detected drift
        - by_type: breakdown by drift type with avg scores
        """
        response = self.client.get(
            f"/api/v1/reports/{model_id}",
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()

    def get_drift_history(
        self,
        model_id: Optional[str] = None,
        monitor_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get drift detection result history.

        Parameters
        ----------
        model_id : str, optional
        monitor_id : str, optional
        limit : int

        Returns
        -------
        list of drift result records.
        """
        params: dict[str, Any] = {"limit": limit}
        if model_id:
            params["model_endpoint_id"] = model_id
        if monitor_id:
            params["monitor_id"] = monitor_id

        response = self.client.get("/api/v1/drift/results", params=params)
        response.raise_for_status()
        return response.json().get("results", [])

    def get_alert_history(
        self,
        model_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get alert delivery history.

        Parameters
        ----------
        model_id : str, optional
        limit : int

        Returns
        -------
        list of alert history records.
        """
        params: dict[str, Any] = {"limit": limit}
        if model_id:
            params["model_endpoint_id"] = model_id

        response = self.client.get("/api/v1/alerts/history", params=params)
        response.raise_for_status()
        return response.json().get("history", [])

    def generate_summary(
        self,
        model_id: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """Generate a comprehensive drift summary for a model.

        Combines report data, recent results, and alert history into
        a single summary suitable for dashboards or email digests.

        Parameters
        ----------
        model_id : str
        days : int

        Returns
        -------
        dict with comprehensive summary.
        """
        report = self.get_model_report(model_id, days=days)
        recent_results = self.get_drift_history(model_id=model_id, limit=20)
        recent_alerts = self.get_alert_history(model_id=model_id, limit=20)

        # Determine overall health status
        drift_ratio = report.get("drift_detected_count", 0) / max(report.get("total_checks", 1), 1)

        if drift_ratio >= 0.5:
            health_status = "critical"
        elif drift_ratio >= 0.2:
            health_status = "warning"
        elif drift_ratio > 0:
            health_status = "attention"
        else:
            health_status = "healthy"

        # Find the most critical drift type
        most_drifted_type = None
        max_avg_score = 0.0
        by_type = report.get("by_type", {})
        for dt, info in by_type.items():
            if info.get("avg_score", 0) > max_avg_score:
                max_avg_score = info["avg_score"]
                most_drifted_type = dt

        # Recent trend
        recent_scores = [r.get("score", 0) for r in recent_results if r.get("is_drifted")]
        trend = "stable"
        if len(recent_scores) >= 3:
            first_half = recent_scores[:len(recent_scores) // 2]
            second_half = recent_scores[len(recent_scores) // 2:]
            avg_first = sum(first_half) / len(first_half) if first_half else 0
            avg_second = sum(second_half) / len(second_half) if second_half else 0
            if avg_second > avg_first * 1.2:
                trend = "worsening"
            elif avg_second < avg_first * 0.8:
                trend = "improving"

        return {
            "model_endpoint_id": model_id,
            "period_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "health_status": health_status,
            "drift_ratio": round(drift_ratio, 4),
            "total_checks": report.get("total_checks", 0),
            "drift_detected_count": report.get("drift_detected_count", 0),
            "most_drifted_type": most_drifted_type,
            "most_drifted_avg_score": round(max_avg_score, 6),
            "trend": trend,
            "by_type": by_type,
            "recent_results": recent_results[:5],
            "recent_alerts": recent_alerts[:5],
            "alert_count": len(recent_alerts),
        }

    def format_text_report(self, summary: dict[str, Any]) -> str:
        """Format a summary as a plain text report.

        Parameters
        ----------
        summary : dict
            Output from generate_summary().

        Returns
        -------
        Formatted text string.
        """
        lines = [
            "=" * 60,
            "DriftGuard Drift Report",
            "=" * 60,
            f"Model: {summary['model_endpoint_id']}",
            f"Period: Last {summary['period_days']} days",
            f"Generated: {summary['generated_at']}",
            "",
            f"Health Status: {summary['health_status'].upper()}",
            f"Drift Ratio: {summary['drift_ratio']:.1%}",
            f"Total Checks: {summary['total_checks']}",
            f"Drift Detected: {summary['drift_detected_count']}",
            f"Trend: {summary['trend']}",
            "",
            "-" * 60,
            "Breakdown by Drift Type:",
            "-" * 60,
        ]

        for dt, info in summary.get("by_type", {}).items():
            lines.append(f"  {dt}:")
            lines.append(f"    Checks: {info.get('checks', 0)}")
            lines.append(f"    Drifted: {info.get('drifted', 0)}")
            lines.append(f"    Avg Score: {info.get('avg_score', 0):.6f}")
            lines.append("")

        if summary.get("recent_alerts"):
            lines.append("-" * 60)
            lines.append(f"Recent Alerts ({summary['alert_count']} total):")
            lines.append("-" * 60)
            for alert in summary["recent_alerts"]:
                lines.append(f"  [{alert.get('severity', 'N/A').upper()}] {alert.get('message', 'N/A')}")
                lines.append(f"    Channel: {alert.get('channel', 'N/A')}")
                lines.append(f"    Time: {alert.get('created_at', 'N/A')}")
                lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
