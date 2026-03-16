"""AWS Bedrock Collector — Collect inference data from AWS Bedrock models."""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class BedrockCollector:
    """Collects model inference data from AWS Bedrock for drift analysis.

    Pulls invocation logs from CloudWatch and extracts features,
    predictions, and confidence scores from Bedrock model invocations.
    """

    def __init__(
        self,
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        session_kwargs: dict[str, Any] = {"region_name": region_name}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self.session = boto3.Session(**session_kwargs)
        self.bedrock_runtime = self.session.client("bedrock-runtime")
        self.cloudwatch_logs = self.session.client("logs")
        self.region = region_name

    async def collect(
        self,
        model_id: str,
        log_group: str,
        lookback_minutes: int = 60,
        max_records: int = 1000,
    ) -> dict[str, Any]:
        """Collect recent inference data from Bedrock model invocations.

        Parameters
        ----------
        model_id : str
            Bedrock model identifier (e.g., "anthropic.claude-3-sonnet-20240229-v1:0").
        log_group : str
            CloudWatch log group where Bedrock invocation logs are stored.
        lookback_minutes : int
            How far back to look for logs.
        max_records : int
            Maximum number of records to collect.

        Returns
        -------
        dict with keys: queries, predictions, confidences, embeddings, metadata
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=lookback_minutes)

        queries: list[str] = []
        predictions: list[float] = []
        confidences: list[float] = []
        embeddings: list[list[float]] = []
        raw_records: list[dict] = []

        try:
            paginator = self.cloudwatch_logs.get_paginator("filter_log_events")
            page_iterator = paginator.paginate(
                logGroupName=log_group,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                filterPattern=f'{{ $.modelId = "{model_id}" }}',
                PaginationConfig={"MaxItems": max_records},
            )

            for page in page_iterator:
                for event in page.get("events", []):
                    try:
                        record = json.loads(event["message"])
                        parsed = self._parse_invocation_record(record, model_id)
                        if parsed:
                            if parsed.get("query"):
                                queries.append(parsed["query"])
                            if parsed.get("prediction") is not None:
                                predictions.append(parsed["prediction"])
                            if parsed.get("confidence") is not None:
                                confidences.append(parsed["confidence"])
                            if parsed.get("embedding"):
                                embeddings.append(parsed["embedding"])
                            raw_records.append(record)
                    except (json.JSONDecodeError, KeyError) as exc:
                        logger.warning("Failed to parse Bedrock log event: %s", exc)

        except ClientError as exc:
            logger.error("CloudWatch query failed: %s", exc)
            raise RuntimeError(f"Failed to collect Bedrock logs: {exc}") from exc

        result: dict[str, Any] = {"metadata": {
            "model_id": model_id,
            "log_group": log_group,
            "lookback_minutes": lookback_minutes,
            "records_collected": len(raw_records),
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

    def _parse_invocation_record(self, record: dict, model_id: str) -> Optional[dict]:
        """Parse a single Bedrock invocation log record.

        Handles different model families:
        - Anthropic Claude: extract prompt, completion, stop_reason
        - Amazon Titan: extract inputText, results, embeddings
        - Cohere: extract prompt, generations, likelihoods
        - Meta Llama: extract prompt, generation, stop_reason
        """
        input_body = record.get("input", {})
        output_body = record.get("output", {})

        if isinstance(input_body, str):
            try:
                input_body = json.loads(input_body)
            except json.JSONDecodeError:
                input_body = {}

        if isinstance(output_body, str):
            try:
                output_body = json.loads(output_body)
            except json.JSONDecodeError:
                output_body = {}

        parsed: dict[str, Any] = {}

        # Anthropic Claude models
        if "anthropic" in model_id.lower():
            messages = input_body.get("messages", [])
            if messages:
                last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
                if last_user:
                    content = last_user.get("content", "")
                    parsed["query"] = content if isinstance(content, str) else json.dumps(content)

            if output_body.get("content"):
                text_blocks = [b.get("text", "") for b in output_body["content"] if b.get("type") == "text"]
                parsed["prediction"] = len(" ".join(text_blocks).split()) / 100.0  # normalized length

            stop_reason = output_body.get("stop_reason", "")
            if stop_reason == "end_turn":
                parsed["confidence"] = 0.9
            elif stop_reason == "max_tokens":
                parsed["confidence"] = 0.5
            else:
                parsed["confidence"] = 0.7

        # Amazon Titan models
        elif "titan" in model_id.lower():
            parsed["query"] = input_body.get("inputText", "")

            if "embedding" in model_id.lower():
                emb = output_body.get("embedding", [])
                if emb:
                    parsed["embedding"] = emb
            else:
                results = output_body.get("results", [])
                if results:
                    parsed["prediction"] = len(results[0].get("outputText", "").split()) / 100.0
                    parsed["confidence"] = results[0].get("completionReason") == "FINISH" and 0.9 or 0.6

        # Cohere models
        elif "cohere" in model_id.lower():
            parsed["query"] = input_body.get("prompt", "")
            generations = output_body.get("generations", [])
            if generations:
                gen = generations[0]
                parsed["prediction"] = len(gen.get("text", "").split()) / 100.0
                likelihood = gen.get("likelihood")
                if likelihood is not None:
                    parsed["confidence"] = min(max(likelihood, 0.0), 1.0)

        # Meta Llama models
        elif "meta" in model_id.lower():
            parsed["query"] = input_body.get("prompt", "")
            generation = output_body.get("generation", "")
            if generation:
                parsed["prediction"] = len(generation.split()) / 100.0
            stop_reason = output_body.get("stop_reason", "")
            parsed["confidence"] = 0.85 if stop_reason == "stop" else 0.6

        return parsed if parsed else None

    async def test_connection(self, model_id: str) -> dict[str, Any]:
        """Test connectivity to Bedrock and validate the model ID."""
        try:
            bedrock = self.session.client("bedrock")
            response = bedrock.get_foundation_model(modelIdentifier=model_id)
            model_details = response.get("modelDetails", {})
            return {
                "status": "connected",
                "model_id": model_id,
                "model_name": model_details.get("modelName", "unknown"),
                "provider": model_details.get("providerName", "unknown"),
                "region": self.region,
            }
        except ClientError as exc:
            return {
                "status": "error",
                "model_id": model_id,
                "error": str(exc),
                "region": self.region,
            }
