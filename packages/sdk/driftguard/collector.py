"""DriftGuard Client & Collector — Buffer and send prediction data to the DriftGuard API."""

import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("driftguard.collector")


class DriftGuardClient:
    """Client for the DriftGuard API.

    Handles authentication, data ingestion, and baseline management.

    Parameters
    ----------
    api_key : str
        DriftGuard API key (starts with "dg_").
    endpoint : str
        Base URL of the DriftGuard API.
    timeout : float
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://api.driftguard.io",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self._http_client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.Client(
                base_url=self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        return self._http_client

    @property
    def async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                base_url=self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        return self._async_client

    def collector(self, model_id: str, batch_size: int = 50) -> "Collector":
        """Create a Collector for a specific model endpoint.

        Parameters
        ----------
        model_id : str
            The registered model endpoint ID.
        batch_size : int
            Number of records to buffer before auto-flushing.

        Returns
        -------
        Collector instance.
        """
        return Collector(client=self, model_id=model_id, batch_size=batch_size)

    @contextmanager
    def monitor_context(self, model_id: str, batch_size: int = 50):
        """Context manager that auto-flushes on exit.

        Usage::

            with client.monitor_context("my-model") as collector:
                for batch in data_loader:
                    result = model.predict(batch)
                    collector.log(features=batch, prediction=result)
        """
        coll = self.collector(model_id, batch_size=batch_size)
        try:
            yield coll
        finally:
            coll.flush()

    def set_baseline(
        self,
        model_id: str,
        drift_type: str,
        features: Optional[list[list[float]]] = None,
        embeddings: Optional[list[list[float]]] = None,
        predictions: Optional[list[float]] = None,
        confidences: Optional[list[float]] = None,
        queries: Optional[list[str]] = None,
    ) -> dict:
        """Set a drift detection baseline for a model endpoint.

        Parameters
        ----------
        model_id : str
        drift_type : str
            One of: data_drift, embedding_drift, response_drift,
            confidence_drift, query_drift.
        features, embeddings, predictions, confidences, queries
            Baseline data corresponding to the drift type.

        Returns
        -------
        dict with baseline ID and status.
        """
        payload: dict[str, Any] = {
            "model_endpoint_id": model_id,
            "drift_type": drift_type,
        }
        if features is not None:
            payload["features"] = features
        if embeddings is not None:
            payload["embeddings"] = embeddings
        if predictions is not None:
            payload["predictions"] = predictions
        if confidences is not None:
            payload["confidences"] = confidences
        if queries is not None:
            payload["queries"] = queries

        response = self.http_client.post("/api/v1/baselines", json=payload)
        response.raise_for_status()
        return response.json()

    def create_monitor(
        self,
        model_id: str,
        drift_type: str,
        config: Optional[dict] = None,
        schedule_minutes: int = 60,
    ) -> dict:
        """Create a drift monitor for a model endpoint.

        Parameters
        ----------
        model_id : str
        drift_type : str
        config : dict, optional
            Detector-specific configuration.
        schedule_minutes : int
            How often to run drift detection.

        Returns
        -------
        dict with monitor ID and status.
        """
        payload = {
            "model_endpoint_id": model_id,
            "drift_type": drift_type,
            "config": config or {},
            "schedule_minutes": schedule_minutes,
        }
        response = self.http_client.post("/api/v1/monitors", json=payload)
        response.raise_for_status()
        return response.json()

    def run_drift_check(self, monitor_id: str) -> dict:
        """Manually trigger a drift detection run.

        Parameters
        ----------
        monitor_id : str

        Returns
        -------
        dict with drift detection result.
        """
        response = self.http_client.post("/api/v1/drift/run", json={"monitor_id": monitor_id})
        response.raise_for_status()
        return response.json()

    def get_drift_results(
        self,
        model_id: Optional[str] = None,
        monitor_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Retrieve drift detection results.

        Parameters
        ----------
        model_id : str, optional
        monitor_id : str, optional
        limit : int

        Returns
        -------
        list of drift result dicts.
        """
        params: dict[str, Any] = {"limit": limit}
        if model_id:
            params["model_endpoint_id"] = model_id
        if monitor_id:
            params["monitor_id"] = monitor_id

        response = self.http_client.get("/api/v1/drift/results", params=params)
        response.raise_for_status()
        return response.json().get("results", [])

    def close(self) -> None:
        """Close HTTP clients."""
        if self._http_client and not self._http_client.is_closed:
            self._http_client.close()
        if self._async_client and not self._async_client.is_closed:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_client.aclose())
            except RuntimeError:
                asyncio.run(self._async_client.aclose())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Collector:
    """Buffers and sends prediction data to the DriftGuard API.

    Designed for high-throughput use with batched, non-blocking uploads.
    Thread-safe for use in concurrent serving environments.

    Parameters
    ----------
    client : DriftGuardClient
    model_id : str
    batch_size : int
        Records to buffer before auto-flush.
    """

    def __init__(self, client: DriftGuardClient, model_id: str, batch_size: int = 50):
        self.client = client
        self.model_id = model_id
        self.batch_size = batch_size
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def buffer_size(self) -> int:
        with self._lock:
            return len(self._buffer)

    def log(
        self,
        features: Optional[list[float] | list[list[float]]] = None,
        prediction: Optional[float] = None,
        confidence: Optional[float] = None,
        embeddings: Optional[list[float] | list[list[float]]] = None,
        query: Optional[str] = None,
        latency_ms: Optional[float] = None,
        error: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Log a single prediction record.

        Parameters
        ----------
        features : list
            Input feature vector(s).
        prediction : float
            Model output value.
        confidence : float
            Confidence/probability score.
        embeddings : list
            Embedding vector(s).
        query : str
            Input query string.
        latency_ms : float
            Prediction latency in milliseconds.
        error : str
            Error message if prediction failed.
        extra : dict
            Additional metadata.
        """
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if features is not None:
            record["features"] = [features] if features and isinstance(features[0], (int, float)) else features
        if prediction is not None:
            record["predictions"] = [prediction]
        if confidence is not None:
            record["confidences"] = [confidence]
        if embeddings is not None:
            record["embeddings"] = [embeddings] if embeddings and isinstance(embeddings[0], (int, float)) else embeddings
        if query is not None:
            record["queries"] = [query]
        if latency_ms is not None:
            record["latency_ms"] = latency_ms
        if error is not None:
            record["error"] = error
        if extra:
            record["extra"] = extra

        with self._lock:
            self._buffer.append(record)

            if len(self._buffer) >= self.batch_size:
                self._flush_buffer()

    def flush(self) -> None:
        """Flush all buffered records to the API."""
        with self._lock:
            self._flush_buffer()

    async def flush_async(self) -> None:
        """Async version of flush."""
        with self._lock:
            records = list(self._buffer)
            self._buffer.clear()

        if not records:
            return

        payload = self._merge_records(records)
        try:
            response = await self.client.async_client.post("/api/v1/ingest", json=payload)
            response.raise_for_status()
            logger.debug("Flushed %d records for model %s", len(records), self.model_id)
        except Exception as exc:
            logger.error("Async flush failed for model %s: %s", self.model_id, exc)
            # Re-buffer on failure
            with self._lock:
                self._buffer = records + self._buffer

    def _flush_buffer(self) -> None:
        """Internal flush (must be called with lock held)."""
        if not self._buffer:
            return

        records = list(self._buffer)
        self._buffer.clear()

        payload = self._merge_records(records)

        # Send in background thread to avoid blocking
        thread = threading.Thread(target=self._send, args=(payload, records), daemon=True)
        thread.start()

    def _send(self, payload: dict, records: list[dict]) -> None:
        """Send payload to API (runs in background thread)."""
        try:
            response = self.client.http_client.post("/api/v1/ingest", json=payload)
            response.raise_for_status()
            logger.debug("Flushed %d records for model %s", len(records), self.model_id)
        except Exception as exc:
            logger.error("Flush failed for model %s: %s", self.model_id, exc)
            # Re-buffer on failure
            with self._lock:
                self._buffer = records + self._buffer

    def _merge_records(self, records: list[dict]) -> dict:
        """Merge individual records into a single ingest payload."""
        merged: dict[str, Any] = {"model_endpoint_id": self.model_id}

        all_features: list = []
        all_predictions: list = []
        all_confidences: list = []
        all_embeddings: list = []
        all_queries: list = []

        for r in records:
            if "features" in r:
                all_features.extend(r["features"])
            if "predictions" in r:
                all_predictions.extend(r["predictions"])
            if "confidences" in r:
                all_confidences.extend(r["confidences"])
            if "embeddings" in r:
                all_embeddings.extend(r["embeddings"])
            if "queries" in r:
                all_queries.extend(r["queries"])

        if all_features:
            merged["features"] = all_features
        if all_predictions:
            merged["predictions"] = all_predictions
        if all_confidences:
            merged["confidences"] = all_confidences
        if all_embeddings:
            merged["embeddings"] = all_embeddings
        if all_queries:
            merged["queries"] = all_queries

        return merged

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.flush()
