"""SageMaker Collector — Collect inference data from SageMaker endpoints."""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class SageMakerCollector:
    """Collects model inference data from SageMaker endpoints.

    Uses CloudWatch Logs and SageMaker Data Capture to extract
    inference inputs, outputs, and metadata for drift analysis.
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
        self.sagemaker = self.session.client("sagemaker")
        self.s3 = self.session.client("s3")
        self.cloudwatch_logs = self.session.client("logs")
        self.region = region_name

    async def collect(
        self,
        endpoint_name: str,
        data_capture_s3_uri: Optional[str] = None,
        lookback_minutes: int = 60,
        max_records: int = 1000,
    ) -> dict[str, Any]:
        """Collect recent inference data from a SageMaker endpoint.

        Parameters
        ----------
        endpoint_name : str
            Name of the SageMaker endpoint.
        data_capture_s3_uri : str, optional
            S3 URI where data capture files are stored.
        lookback_minutes : int
            How far back to look for data.
        max_records : int
            Maximum number of records to collect.

        Returns
        -------
        dict with keys: features, predictions, confidences, metadata
        """
        features: list[list[float]] = []
        predictions: list[float] = []
        confidences: list[float] = []

        if data_capture_s3_uri:
            capture_data = await self._collect_from_data_capture(
                data_capture_s3_uri, lookback_minutes, max_records
            )
            features.extend(capture_data.get("features", []))
            predictions.extend(capture_data.get("predictions", []))
            confidences.extend(capture_data.get("confidences", []))
        else:
            log_data = await self._collect_from_logs(endpoint_name, lookback_minutes, max_records)
            features.extend(log_data.get("features", []))
            predictions.extend(log_data.get("predictions", []))
            confidences.extend(log_data.get("confidences", []))

        result: dict[str, Any] = {"metadata": {
            "endpoint_name": endpoint_name,
            "lookback_minutes": lookback_minutes,
            "records_collected": max(len(features), len(predictions)),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }}

        if features:
            result["features"] = features
        if predictions:
            result["predictions"] = predictions
        if confidences:
            result["confidences"] = confidences

        return result

    async def _collect_from_data_capture(
        self, s3_uri: str, lookback_minutes: int, max_records: int
    ) -> dict[str, Any]:
        """Parse SageMaker Data Capture files from S3."""
        bucket, prefix = self._parse_s3_uri(s3_uri)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

        features: list[list[float]] = []
        predictions: list[float] = []
        confidences: list[float] = []

        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    if obj["LastModified"].replace(tzinfo=timezone.utc) < cutoff:
                        continue
                    if len(features) >= max_records:
                        break

                    try:
                        response = self.s3.get_object(Bucket=bucket, Key=obj["Key"])
                        body = response["Body"].read().decode("utf-8")

                        for line in body.strip().split("\n"):
                            if not line.strip():
                                continue
                            record = json.loads(line)
                            parsed = self._parse_capture_record(record)
                            if parsed.get("features"):
                                features.append(parsed["features"])
                            if parsed.get("prediction") is not None:
                                predictions.append(parsed["prediction"])
                            if parsed.get("confidence") is not None:
                                confidences.append(parsed["confidence"])
                    except (json.JSONDecodeError, ClientError) as exc:
                        logger.warning("Failed to parse capture file %s: %s", obj["Key"], exc)

        except ClientError as exc:
            logger.error("S3 data capture collection failed: %s", exc)

        return {"features": features, "predictions": predictions, "confidences": confidences}

    async def _collect_from_logs(
        self, endpoint_name: str, lookback_minutes: int, max_records: int
    ) -> dict[str, Any]:
        """Collect from CloudWatch endpoint invocation logs."""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=lookback_minutes)
        log_group = f"/aws/sagemaker/Endpoints/{endpoint_name}"

        features: list[list[float]] = []
        predictions: list[float] = []
        confidences: list[float] = []

        try:
            paginator = self.cloudwatch_logs.get_paginator("filter_log_events")
            page_iterator = paginator.paginate(
                logGroupName=log_group,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                PaginationConfig={"MaxItems": max_records},
            )

            for page in page_iterator:
                for event in page.get("events", []):
                    try:
                        record = json.loads(event["message"])
                        if "input" in record:
                            inp = record["input"]
                            if isinstance(inp, list):
                                features.append([float(v) for v in inp])
                        if "output" in record:
                            out = record["output"]
                            if isinstance(out, (int, float)):
                                predictions.append(float(out))
                            elif isinstance(out, dict):
                                if "prediction" in out:
                                    predictions.append(float(out["prediction"]))
                                if "confidence" in out:
                                    confidences.append(float(out["confidence"]))
                    except (json.JSONDecodeError, ValueError, KeyError) as exc:
                        logger.warning("Failed to parse log event: %s", exc)

        except ClientError as exc:
            logger.error("CloudWatch log collection failed: %s", exc)

        return {"features": features, "predictions": predictions, "confidences": confidences}

    def _parse_capture_record(self, record: dict) -> dict:
        """Parse a SageMaker Data Capture record."""
        result: dict[str, Any] = {}

        capture_data = record.get("captureData", {})

        # Input data
        input_data = capture_data.get("endpointInput", {})
        encoding = input_data.get("encoding", "CSV")
        data = input_data.get("data", "")

        if encoding == "CSV" and data:
            try:
                values = [float(v.strip()) for v in data.split(",") if v.strip()]
                result["features"] = values
            except ValueError:
                pass
        elif encoding == "JSON" and data:
            try:
                parsed = json.loads(data)
                if isinstance(parsed, dict) and "instances" in parsed:
                    instances = parsed["instances"]
                    if instances and isinstance(instances[0], list):
                        result["features"] = [float(v) for v in instances[0]]
                elif isinstance(parsed, list):
                    result["features"] = [float(v) for v in parsed]
            except (json.JSONDecodeError, ValueError):
                pass

        # Output data
        output_data = capture_data.get("endpointOutput", {})
        out_encoding = output_data.get("encoding", "CSV")
        out_data = output_data.get("data", "")

        if out_encoding == "CSV" and out_data:
            try:
                values = [float(v.strip()) for v in out_data.split(",") if v.strip()]
                if values:
                    result["prediction"] = values[0]
                    if len(values) > 1:
                        result["confidence"] = values[1]
            except ValueError:
                pass
        elif out_encoding == "JSON" and out_data:
            try:
                parsed = json.loads(out_data)
                if isinstance(parsed, dict):
                    result["prediction"] = float(parsed.get("prediction", parsed.get("score", 0)))
                    if "confidence" in parsed:
                        result["confidence"] = float(parsed["confidence"])
                elif isinstance(parsed, (int, float)):
                    result["prediction"] = float(parsed)
            except (json.JSONDecodeError, ValueError):
                pass

        return result

    @staticmethod
    def _parse_s3_uri(uri: str) -> tuple[str, str]:
        path = uri.replace("s3://", "")
        parts = path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        return bucket, prefix

    async def test_connection(self, endpoint_name: str) -> dict[str, Any]:
        """Test connectivity to a SageMaker endpoint."""
        try:
            response = self.sagemaker.describe_endpoint(EndpointName=endpoint_name)
            return {
                "status": "connected",
                "endpoint_name": endpoint_name,
                "endpoint_status": response.get("EndpointStatus", "unknown"),
                "creation_time": response.get("CreationTime", "").isoformat() if response.get("CreationTime") else None,
                "region": self.region,
            }
        except ClientError as exc:
            return {
                "status": "error",
                "endpoint_name": endpoint_name,
                "error": str(exc),
                "region": self.region,
            }
