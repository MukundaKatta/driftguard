"""DynamoDB Time-Series Storage — High-throughput metric ingestion and retrieval."""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types from DynamoDB."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _convert_floats(obj: Any) -> Any:
    """Recursively convert float values to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_floats(v) for v in obj]
    return obj


def _convert_decimals(obj: Any) -> Any:
    """Recursively convert Decimal values back to float."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(v) for v in obj]
    return obj


class DynamoStorage:
    """Manages time-series metric data in DynamoDB.

    Table schema:
    - Partition key: model_endpoint_id (String)
    - Sort key: timestamp#record_id (String)
    - GSI: workspace_id-timestamp-index for workspace-level queries

    Stores raw ingested data (features, embeddings, predictions,
    confidences, queries) for drift detection comparisons.
    """

    def __init__(self):
        self.table_name = os.getenv("DYNAMO_TABLE_NAME", "driftguard-metrics")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self._resource = None
        self._table = None

    @property
    def resource(self):
        if self._resource is None:
            self._resource = boto3.resource("dynamodb", region_name=self.region)
        return self._resource

    @property
    def table(self):
        if self._table is None:
            self._table = self.resource.Table(self.table_name)
        return self._table

    async def put_metrics(
        self,
        record_id: str,
        model_endpoint_id: str,
        workspace_id: str,
        timestamp: str,
        data: dict[str, Any],
    ) -> dict:
        """Store a batch of metric data.

        Parameters
        ----------
        record_id : str
            Unique identifier for this ingestion record.
        model_endpoint_id : str
            The model endpoint these metrics belong to.
        workspace_id : str
            Owning workspace.
        timestamp : str
            ISO format timestamp.
        data : dict
            Metric data containing any combination of:
            features, embeddings, predictions, confidences, queries.

        Returns
        -------
        dict with status.
        """
        sort_key = f"{timestamp}#{record_id}"

        item = {
            "model_endpoint_id": model_endpoint_id,
            "sort_key": sort_key,
            "record_id": record_id,
            "workspace_id": workspace_id,
            "timestamp": timestamp,
            "data": _convert_floats(data),
            "ttl": int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp()),
        }

        try:
            self.table.put_item(Item=item)
            logger.debug("Stored metrics: model=%s, record=%s", model_endpoint_id, record_id)
            return {"status": "ok", "record_id": record_id}
        except ClientError as exc:
            logger.error("DynamoDB put failed: %s", exc)
            raise

    async def get_recent_metrics(
        self,
        model_endpoint_id: str,
        workspace_id: str,
        limit: int = 1000,
        lookback_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Retrieve recent metric records for a model endpoint.

        Parameters
        ----------
        model_endpoint_id : str
        workspace_id : str
        limit : int
            Maximum records to return.
        lookback_hours : int
            How far back to query.

        Returns
        -------
        list of metric records, newest first.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()

        try:
            response = self.table.query(
                KeyConditionExpression=(
                    Key("model_endpoint_id").eq(model_endpoint_id)
                    & Key("sort_key").gte(cutoff)
                ),
                FilterExpression=Key("workspace_id").eq(workspace_id),
                ScanIndexForward=False,
                Limit=limit,
            )

            items = response.get("Items", [])

            # Handle pagination
            while "LastEvaluatedKey" in response and len(items) < limit:
                response = self.table.query(
                    KeyConditionExpression=(
                        Key("model_endpoint_id").eq(model_endpoint_id)
                        & Key("sort_key").gte(cutoff)
                    ),
                    FilterExpression=Key("workspace_id").eq(workspace_id),
                    ScanIndexForward=False,
                    Limit=limit - len(items),
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))

            return [_convert_decimals(item) for item in items[:limit]]

        except ClientError as exc:
            logger.error("DynamoDB query failed: %s", exc)
            raise

    async def get_metrics_in_range(
        self,
        model_endpoint_id: str,
        workspace_id: str,
        start_time: str,
        end_time: str,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Retrieve metric records within a specific time range.

        Parameters
        ----------
        model_endpoint_id : str
        workspace_id : str
        start_time : str
            ISO format start timestamp.
        end_time : str
            ISO format end timestamp.
        limit : int

        Returns
        -------
        list of metric records.
        """
        try:
            response = self.table.query(
                KeyConditionExpression=(
                    Key("model_endpoint_id").eq(model_endpoint_id)
                    & Key("sort_key").between(start_time, end_time + "~")
                ),
                FilterExpression=Key("workspace_id").eq(workspace_id),
                ScanIndexForward=True,
                Limit=limit,
            )

            items = response.get("Items", [])
            while "LastEvaluatedKey" in response and len(items) < limit:
                response = self.table.query(
                    KeyConditionExpression=(
                        Key("model_endpoint_id").eq(model_endpoint_id)
                        & Key("sort_key").between(start_time, end_time + "~")
                    ),
                    FilterExpression=Key("workspace_id").eq(workspace_id),
                    ScanIndexForward=True,
                    Limit=limit - len(items),
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))

            return [_convert_decimals(item) for item in items[:limit]]

        except ClientError as exc:
            logger.error("DynamoDB range query failed: %s", exc)
            raise

    async def delete_metrics(
        self,
        model_endpoint_id: str,
        workspace_id: str,
        before_timestamp: Optional[str] = None,
    ) -> int:
        """Delete metric records for a model endpoint.

        Parameters
        ----------
        model_endpoint_id : str
        workspace_id : str
        before_timestamp : str, optional
            Delete records older than this timestamp. If None, delete all.

        Returns
        -------
        int count of deleted records.
        """
        deleted = 0

        try:
            key_condition = Key("model_endpoint_id").eq(model_endpoint_id)
            if before_timestamp:
                key_condition = key_condition & Key("sort_key").lt(before_timestamp)

            response = self.table.query(
                KeyConditionExpression=key_condition,
                FilterExpression=Key("workspace_id").eq(workspace_id),
                ProjectionExpression="model_endpoint_id, sort_key",
            )

            items = response.get("Items", [])
            while "LastEvaluatedKey" in response:
                response = self.table.query(
                    KeyConditionExpression=key_condition,
                    FilterExpression=Key("workspace_id").eq(workspace_id),
                    ProjectionExpression="model_endpoint_id, sort_key",
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))

            with self.table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(
                        Key={
                            "model_endpoint_id": item["model_endpoint_id"],
                            "sort_key": item["sort_key"],
                        }
                    )
                    deleted += 1

        except ClientError as exc:
            logger.error("DynamoDB delete failed: %s", exc)
            raise

        return deleted

    async def get_metric_count(self, model_endpoint_id: str, workspace_id: str) -> int:
        """Get the count of stored metrics for a model endpoint."""
        try:
            response = self.table.query(
                KeyConditionExpression=Key("model_endpoint_id").eq(model_endpoint_id),
                FilterExpression=Key("workspace_id").eq(workspace_id),
                Select="COUNT",
            )
            count = response.get("Count", 0)
            while "LastEvaluatedKey" in response:
                response = self.table.query(
                    KeyConditionExpression=Key("model_endpoint_id").eq(model_endpoint_id),
                    FilterExpression=Key("workspace_id").eq(workspace_id),
                    Select="COUNT",
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                count += response.get("Count", 0)
            return count
        except ClientError as exc:
            logger.error("DynamoDB count failed: %s", exc)
            raise
