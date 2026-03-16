"""Custom Collector — Generic HTTP endpoint collector for any model serving platform."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class CustomCollector:
    """Collects model inference data from any HTTP endpoint.

    Supports configurable request/response mapping to extract features,
    predictions, confidences, embeddings, and queries from arbitrary APIs.
    """

    def __init__(
        self,
        base_url: str,
        headers: Optional[dict[str, str]] = None,
        auth_token: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
        self.timeout = timeout

    async def collect(
        self,
        endpoint_path: str = "/metrics",
        method: str = "GET",
        body: Optional[dict] = None,
        field_mapping: Optional[dict[str, str]] = None,
        max_records: int = 1000,
    ) -> dict[str, Any]:
        """Collect inference data from a custom HTTP endpoint.

        Parameters
        ----------
        endpoint_path : str
            Path appended to base_url for the metrics endpoint.
        method : str
            HTTP method (GET or POST).
        body : dict, optional
            Request body for POST requests.
        field_mapping : dict, optional
            Maps DriftGuard fields to response JSON paths.
            Example: {"features": "data.inputs", "predictions": "data.outputs.score"}
        max_records : int
            Maximum records to collect.

        Returns
        -------
        dict with extracted data.
        """
        mapping = field_mapping or {
            "features": "features",
            "predictions": "predictions",
            "confidences": "confidences",
            "embeddings": "embeddings",
            "queries": "queries",
        }

        url = f"{self.base_url}{endpoint_path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method.upper() == "POST":
                    response = await client.post(url, headers=self.headers, json=body or {})
                else:
                    response = await client.get(url, headers=self.headers, params=body)

                response.raise_for_status()
                raw_data = response.json()

        except httpx.HTTPError as exc:
            logger.error("Custom endpoint collection failed: %s", exc)
            raise RuntimeError(f"Failed to collect from {url}: {exc}") from exc

        # Handle paginated responses
        records = raw_data
        if isinstance(raw_data, dict):
            # Try common pagination patterns
            for key in ("data", "records", "items", "results"):
                if key in raw_data and isinstance(raw_data[key], list):
                    records = raw_data[key]
                    break

        if isinstance(records, list):
            records = records[:max_records]
            return self._extract_from_records(records, mapping)
        else:
            return self._extract_from_single(raw_data, mapping)

    async def collect_batch(
        self,
        endpoint_path: str = "/inference/logs",
        params: Optional[dict] = None,
        field_mapping: Optional[dict[str, str]] = None,
        page_size: int = 100,
        max_pages: int = 10,
    ) -> dict[str, Any]:
        """Collect with pagination support.

        Parameters
        ----------
        endpoint_path : str
            API path for paginated log retrieval.
        params : dict, optional
            Additional query parameters.
        field_mapping : dict, optional
            Field mapping configuration.
        page_size : int
            Records per page.
        max_pages : int
            Maximum pages to fetch.

        Returns
        -------
        dict with combined data across all pages.
        """
        mapping = field_mapping or {}
        all_features: list[list[float]] = []
        all_predictions: list[float] = []
        all_confidences: list[float] = []
        all_embeddings: list[list[float]] = []
        all_queries: list[str] = []

        url = f"{self.base_url}{endpoint_path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(max_pages):
                request_params = {**(params or {}), "page": page, "page_size": page_size}

                try:
                    response = await client.get(url, headers=self.headers, params=request_params)
                    response.raise_for_status()
                    raw_data = response.json()
                except httpx.HTTPError as exc:
                    logger.warning("Page %d collection failed: %s", page, exc)
                    break

                # Extract records from response
                records = raw_data
                if isinstance(raw_data, dict):
                    for key in ("data", "records", "items", "results"):
                        if key in raw_data and isinstance(raw_data[key], list):
                            records = raw_data[key]
                            break

                if not isinstance(records, list) or not records:
                    break

                extracted = self._extract_from_records(records, mapping)
                all_features.extend(extracted.get("features", []))
                all_predictions.extend(extracted.get("predictions", []))
                all_confidences.extend(extracted.get("confidences", []))
                all_embeddings.extend(extracted.get("embeddings", []))
                all_queries.extend(extracted.get("queries", []))

                if len(records) < page_size:
                    break

        result: dict[str, Any] = {"metadata": {
            "base_url": self.base_url,
            "endpoint_path": endpoint_path,
            "pages_fetched": min(page + 1, max_pages),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }}

        if all_features:
            result["features"] = all_features
        if all_predictions:
            result["predictions"] = all_predictions
        if all_confidences:
            result["confidences"] = all_confidences
        if all_embeddings:
            result["embeddings"] = all_embeddings
        if all_queries:
            result["queries"] = all_queries

        return result

    def _extract_from_records(self, records: list[dict], mapping: dict) -> dict[str, Any]:
        """Extract fields from a list of records using the field mapping."""
        features: list[list[float]] = []
        predictions: list[float] = []
        confidences: list[float] = []
        embeddings: list[list[float]] = []
        queries: list[str] = []

        for record in records:
            feat = self._resolve_path(record, mapping.get("features", "features"))
            if feat is not None and isinstance(feat, list):
                if feat and isinstance(feat[0], (int, float)):
                    features.append([float(v) for v in feat])
                elif feat and isinstance(feat[0], list):
                    features.extend([[float(v) for v in row] for row in feat])

            pred = self._resolve_path(record, mapping.get("predictions", "predictions"))
            if pred is not None:
                if isinstance(pred, (int, float)):
                    predictions.append(float(pred))
                elif isinstance(pred, list):
                    predictions.extend([float(v) for v in pred])

            conf = self._resolve_path(record, mapping.get("confidences", "confidences"))
            if conf is not None:
                if isinstance(conf, (int, float)):
                    confidences.append(float(conf))
                elif isinstance(conf, list):
                    confidences.extend([float(v) for v in conf])

            emb = self._resolve_path(record, mapping.get("embeddings", "embeddings"))
            if emb is not None and isinstance(emb, list):
                if emb and isinstance(emb[0], (int, float)):
                    embeddings.append([float(v) for v in emb])

            query = self._resolve_path(record, mapping.get("queries", "queries"))
            if query is not None:
                if isinstance(query, str):
                    queries.append(query)
                elif isinstance(query, list):
                    queries.extend([str(q) for q in query])

        result: dict[str, Any] = {}
        if features:
            result["features"] = features
        if predictions:
            result["predictions"] = predictions
        if confidences:
            result["confidences"] = confidences
        if embeddings:
            result["embeddings"] = embeddings
        if queries:
            result["queries"] = queries

        return result

    def _extract_from_single(self, data: dict, mapping: dict) -> dict[str, Any]:
        """Extract fields from a single response object."""
        result: dict[str, Any] = {"metadata": {
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }}

        for field_name in ("features", "predictions", "confidences", "embeddings", "queries"):
            path = mapping.get(field_name, field_name)
            value = self._resolve_path(data, path)
            if value is not None:
                result[field_name] = value

        return result

    @staticmethod
    def _resolve_path(obj: Any, path: str) -> Any:
        """Resolve a dot-separated path on a nested dict/list."""
        if not path:
            return None
        parts = path.split(".")
        current = obj
        for part in parts:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            else:
                return None
        return current

    async def test_connection(self) -> dict[str, Any]:
        """Test connectivity to the custom endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers=self.headers,
                )
                return {
                    "status": "connected" if response.status_code < 400 else "error",
                    "base_url": self.base_url,
                    "http_status": response.status_code,
                }
        except httpx.HTTPError as exc:
            return {
                "status": "error",
                "base_url": self.base_url,
                "error": str(exc),
            }
