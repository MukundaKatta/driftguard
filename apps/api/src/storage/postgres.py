"""Supabase/Postgres Storage — Configuration, models, monitors, results, and alerts."""

import json
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from supabase import create_client, Client

logger = logging.getLogger(__name__)


class PostgresStorage:
    """Manages all relational data in Supabase Postgres.

    Tables: workspaces, model_endpoints, monitors, baselines,
    drift_results, alert_configs, alert_history.
    """

    def __init__(self):
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        self._client: Optional[Client] = None
        self._url = url
        self._key = key

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = create_client(self._url, self._key)
        return self._client

    # ------------------------------------------------------------------
    # Auth / Workspace
    # ------------------------------------------------------------------

    async def get_workspace_from_token(self, token: str) -> Optional[dict]:
        """Validate a JWT token and return the associated workspace."""
        try:
            user_response = self.client.auth.get_user(token)
            user = user_response.user
            if not user:
                return None

            result = (
                self.client.table("workspaces")
                .select("*")
                .eq("owner_id", user.id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]

            # Auto-create workspace for new users
            workspace = {
                "owner_id": user.id,
                "name": user.email or "Default Workspace",
                "plan": "free",
            }
            create_result = self.client.table("workspaces").insert(workspace).execute()
            return create_result.data[0] if create_result.data else None
        except Exception as exc:
            logger.error("Token validation failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Model Endpoints
    # ------------------------------------------------------------------

    async def create_model_endpoint(
        self,
        id: str,
        workspace_id: str,
        name: str,
        platform: str,
        endpoint_url: Optional[str],
        metadata: dict,
        api_key: str,
    ) -> dict:
        record = {
            "id": id,
            "workspace_id": workspace_id,
            "name": name,
            "platform": platform,
            "endpoint_url": endpoint_url,
            "metadata": json.dumps(metadata),
            "api_key": api_key,
            "status": "active",
        }
        result = self.client.table("model_endpoints").insert(record).execute()
        return result.data[0] if result.data else record

    async def list_model_endpoints(self, workspace_id: str) -> list[dict]:
        result = (
            self.client.table("model_endpoints")
            .select("*")
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def get_model_endpoint(self, model_id: str, workspace_id: str) -> Optional[dict]:
        result = (
            self.client.table("model_endpoints")
            .select("*")
            .eq("id", model_id)
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def delete_model_endpoint(self, model_id: str, workspace_id: str) -> None:
        self.client.table("model_endpoints").delete().eq("id", model_id).eq("workspace_id", workspace_id).execute()

    # ------------------------------------------------------------------
    # Monitors
    # ------------------------------------------------------------------

    async def create_monitor(
        self,
        id: str,
        workspace_id: str,
        model_endpoint_id: str,
        drift_type: str,
        config: dict,
        schedule_minutes: int,
    ) -> dict:
        record = {
            "id": id,
            "workspace_id": workspace_id,
            "model_endpoint_id": model_endpoint_id,
            "drift_type": drift_type,
            "config": json.dumps(config),
            "schedule_minutes": schedule_minutes,
            "status": "active",
        }
        result = self.client.table("monitors").insert(record).execute()
        return result.data[0] if result.data else record

    async def list_monitors(self, workspace_id: str) -> list[dict]:
        result = (
            self.client.table("monitors")
            .select("*")
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .execute()
        )
        rows = result.data or []
        for row in rows:
            if isinstance(row.get("config"), str):
                row["config"] = json.loads(row["config"])
        return rows

    async def get_monitor(self, monitor_id: str, workspace_id: str) -> Optional[dict]:
        result = (
            self.client.table("monitors")
            .select("*")
            .eq("id", monitor_id)
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        if isinstance(row.get("config"), str):
            row["config"] = json.loads(row["config"])
        return row

    async def delete_monitor(self, monitor_id: str, workspace_id: str) -> None:
        self.client.table("monitors").delete().eq("id", monitor_id).eq("workspace_id", workspace_id).execute()

    # ------------------------------------------------------------------
    # Baselines
    # ------------------------------------------------------------------

    async def upsert_baseline(
        self,
        id: str,
        workspace_id: str,
        model_endpoint_id: str,
        drift_type: str,
        data: dict,
    ) -> dict:
        record = {
            "id": id,
            "workspace_id": workspace_id,
            "model_endpoint_id": model_endpoint_id,
            "drift_type": drift_type,
            "data": json.dumps(data),
        }
        # Delete existing baseline for this model/drift_type combo
        self.client.table("baselines").delete().eq(
            "workspace_id", workspace_id
        ).eq(
            "model_endpoint_id", model_endpoint_id
        ).eq(
            "drift_type", drift_type
        ).execute()

        result = self.client.table("baselines").insert(record).execute()
        return result.data[0] if result.data else record

    async def get_baseline(self, model_endpoint_id: str, drift_type: str, workspace_id: str) -> Optional[dict]:
        result = (
            self.client.table("baselines")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("model_endpoint_id", model_endpoint_id)
            .eq("drift_type", drift_type)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        if isinstance(row.get("data"), str):
            row["data"] = json.loads(row["data"])
        return row

    # ------------------------------------------------------------------
    # Drift Results
    # ------------------------------------------------------------------

    async def store_drift_result(
        self,
        id: str,
        monitor_id: str,
        workspace_id: str,
        drift_type: str,
        is_drifted: bool,
        score: float,
        details: dict,
    ) -> dict:
        record = {
            "id": id,
            "monitor_id": monitor_id,
            "workspace_id": workspace_id,
            "drift_type": drift_type,
            "is_drifted": is_drifted,
            "score": score,
            "details": json.dumps(details),
        }
        result = self.client.table("drift_results").insert(record).execute()
        return result.data[0] if result.data else record

    async def list_drift_results(
        self,
        workspace_id: str,
        model_endpoint_id: Optional[str] = None,
        monitor_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = (
            self.client.table("drift_results")
            .select("*, monitors!inner(model_endpoint_id)")
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if monitor_id:
            query = query.eq("monitor_id", monitor_id)
        if model_endpoint_id:
            query = query.eq("monitors.model_endpoint_id", model_endpoint_id)

        result = query.execute()
        rows = result.data or []
        for row in rows:
            if isinstance(row.get("details"), str):
                row["details"] = json.loads(row["details"])
        return rows

    async def get_drift_result(self, result_id: str, workspace_id: str) -> Optional[dict]:
        result = (
            self.client.table("drift_results")
            .select("*")
            .eq("id", result_id)
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        if isinstance(row.get("details"), str):
            row["details"] = json.loads(row["details"])
        return row

    async def get_drift_results_for_period(
        self,
        workspace_id: str,
        model_endpoint_id: str,
        days: int = 30,
    ) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = (
            self.client.table("drift_results")
            .select("*, monitors!inner(model_endpoint_id)")
            .eq("workspace_id", workspace_id)
            .eq("monitors.model_endpoint_id", model_endpoint_id)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .execute()
        )
        rows = result.data or []
        for row in rows:
            if isinstance(row.get("details"), str):
                row["details"] = json.loads(row["details"])
        return rows

    # ------------------------------------------------------------------
    # Alert Configs
    # ------------------------------------------------------------------

    async def create_alert_config(
        self,
        id: str,
        workspace_id: str,
        model_endpoint_id: str,
        channel: str,
        destination: str,
        severity_threshold: str,
        config: dict,
    ) -> dict:
        record = {
            "id": id,
            "workspace_id": workspace_id,
            "model_endpoint_id": model_endpoint_id,
            "channel": channel,
            "destination": destination,
            "severity_threshold": severity_threshold,
            "config": json.dumps(config),
        }
        result = self.client.table("alert_configs").insert(record).execute()
        return result.data[0] if result.data else record

    async def list_alert_configs(
        self, workspace_id: str, model_endpoint_id: Optional[str] = None
    ) -> list[dict]:
        query = (
            self.client.table("alert_configs")
            .select("*")
            .eq("workspace_id", workspace_id)
        )
        if model_endpoint_id:
            query = query.eq("model_endpoint_id", model_endpoint_id)
        result = query.execute()
        rows = result.data or []
        for row in rows:
            if isinstance(row.get("config"), str):
                row["config"] = json.loads(row["config"])
        return rows

    async def delete_alert_config(self, config_id: str, workspace_id: str) -> None:
        self.client.table("alert_configs").delete().eq("id", config_id).eq("workspace_id", workspace_id).execute()

    # ------------------------------------------------------------------
    # Alert History
    # ------------------------------------------------------------------

    async def store_alert_history(self, record: dict) -> dict:
        result = self.client.table("alert_history").insert(record).execute()
        return result.data[0] if result.data else record

    async def get_recent_alert(
        self, config_id: str, workspace_id: str, cooldown_minutes: int = 30
    ) -> Optional[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)).isoformat()
        result = (
            self.client.table("alert_history")
            .select("*")
            .eq("alert_config_id", config_id)
            .eq("workspace_id", workspace_id)
            .eq("success", True)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def list_alert_history(
        self,
        workspace_id: str,
        model_endpoint_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = (
            self.client.table("alert_history")
            .select("*")
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if model_endpoint_id:
            query = query.eq("model_endpoint_id", model_endpoint_id)
        result = query.execute()
        return result.data or []
