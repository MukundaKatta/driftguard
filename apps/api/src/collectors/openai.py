"""OpenAI Collector — Collect inference data from OpenAI API usage."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class OpenAICollector:
    """Collects model inference data from OpenAI API for drift analysis.

    Uses the OpenAI usage API and stored request/response logs to extract
    query patterns, response characteristics, and confidence proxies.
    """

    BASE_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: str, organization: Optional[str] = None):
        self.api_key = api_key
        self.organization = organization
        self.headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if organization:
            self.headers["OpenAI-Organization"] = organization

    async def collect(
        self,
        model: str = "gpt-4",
        stored_logs: Optional[list[dict]] = None,
        max_records: int = 1000,
    ) -> dict[str, Any]:
        """Collect inference data from OpenAI model usage.

        Parameters
        ----------
        model : str
            OpenAI model identifier.
        stored_logs : list[dict], optional
            Pre-collected request/response logs. If not provided,
            collects from the local log store.
        max_records : int
            Maximum records to process.

        Returns
        -------
        dict with keys: queries, predictions, confidences, metadata
        """
        records = stored_logs[:max_records] if stored_logs else []

        queries: list[str] = []
        predictions: list[float] = []
        confidences: list[float] = []
        embeddings: list[list[float]] = []

        for record in records:
            parsed = self._parse_log_record(record)
            if parsed.get("query"):
                queries.append(parsed["query"])
            if parsed.get("prediction") is not None:
                predictions.append(parsed["prediction"])
            if parsed.get("confidence") is not None:
                confidences.append(parsed["confidence"])
            if parsed.get("embedding"):
                embeddings.append(parsed["embedding"])

        result: dict[str, Any] = {"metadata": {
            "model": model,
            "records_collected": len(records),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }}

        if queries:
            result["queries"] = queries
        if predictions:
            result["predictions"] = predictions
        if confidences:
            result["confidences"] = confidences
        if embeddings:
            result["embeddings"] = embeddings

        return result

    async def collect_embeddings(
        self,
        texts: list[str],
        model: str = "text-embedding-3-small",
        batch_size: int = 100,
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts via OpenAI API.

        Parameters
        ----------
        texts : list[str]
            Input texts to embed.
        model : str
            Embedding model to use.
        batch_size : int
            Number of texts per API call.

        Returns
        -------
        list[list[float]] of embedding vectors.
        """
        all_embeddings: list[list[float]] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                try:
                    response = await client.post(
                        f"{self.BASE_URL}/embeddings",
                        headers=self.headers,
                        json={"input": batch, "model": model},
                    )
                    response.raise_for_status()
                    data = response.json()
                    batch_embeddings = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
                    all_embeddings.extend(batch_embeddings)
                except httpx.HTTPError as exc:
                    logger.error("OpenAI embedding request failed: %s", exc)
                    raise RuntimeError(f"OpenAI API error: {exc}") from exc

        return all_embeddings

    def _parse_log_record(self, record: dict) -> dict[str, Any]:
        """Parse a stored OpenAI API request/response log."""
        result: dict[str, Any] = {}

        # Extract query from request
        request = record.get("request", {})
        messages = request.get("messages", [])
        if messages:
            user_messages = [m for m in messages if m.get("role") == "user"]
            if user_messages:
                content = user_messages[-1].get("content", "")
                result["query"] = content if isinstance(content, str) else str(content)

        # Extract prediction/confidence from response
        response = record.get("response", {})
        choices = response.get("choices", [])
        if choices:
            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")

            # Normalized prediction metric: token length ratio
            usage = response.get("usage", {})
            completion_tokens = usage.get("completion_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens", 1)
            result["prediction"] = completion_tokens / max(prompt_tokens, 1)

            # Confidence proxy from finish_reason and logprobs
            finish_reason = choice.get("finish_reason", "")
            logprobs = choice.get("logprobs")

            if logprobs and logprobs.get("content"):
                token_logprobs = [t.get("logprob", 0) for t in logprobs["content"] if "logprob" in t]
                if token_logprobs:
                    import math
                    avg_prob = math.exp(sum(token_logprobs) / len(token_logprobs))
                    result["confidence"] = min(max(avg_prob, 0.0), 1.0)
                else:
                    result["confidence"] = 0.8 if finish_reason == "stop" else 0.5
            else:
                result["confidence"] = 0.8 if finish_reason == "stop" else 0.5

        # Embeddings if present
        embedding_data = response.get("data", [])
        if embedding_data and isinstance(embedding_data, list):
            for item in embedding_data:
                if "embedding" in item:
                    result["embedding"] = item["embedding"]
                    break

        return result

    async def test_connection(self) -> dict[str, Any]:
        """Test connectivity to OpenAI API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers=self.headers,
                )
                response.raise_for_status()
                models = response.json().get("data", [])
                return {
                    "status": "connected",
                    "models_available": len(models),
                    "organization": self.organization,
                }
        except httpx.HTTPError as exc:
            return {
                "status": "error",
                "error": str(exc),
            }
