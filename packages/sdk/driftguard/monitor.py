"""Monitor Decorator — Automatically instrument model prediction functions."""

import functools
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .collector import DriftGuardClient

logger = logging.getLogger("driftguard.monitor")


@dataclass
class MonitorConfig:
    """Configuration for the @monitor decorator.

    Attributes
    ----------
    capture_features : bool
        Whether to capture input features.
    capture_predictions : bool
        Whether to capture model outputs.
    capture_confidence : bool
        Whether to capture confidence scores.
    capture_embeddings : bool
        Whether to capture embedding vectors.
    capture_queries : bool
        Whether to capture query strings.
    batch_size : int
        Number of records to buffer before flushing.
    flush_interval_seconds : float
        Maximum time between flushes.
    feature_extractor : callable, optional
        Custom function to extract features from function args.
    prediction_extractor : callable, optional
        Custom function to extract prediction value from return value.
    confidence_extractor : callable, optional
        Custom function to extract confidence from return value.
    embedding_extractor : callable, optional
        Custom function to extract embeddings from function args or return.
    query_extractor : callable, optional
        Custom function to extract query string from function args.
    """

    capture_features: bool = True
    capture_predictions: bool = True
    capture_confidence: bool = True
    capture_embeddings: bool = False
    capture_queries: bool = False
    batch_size: int = 50
    flush_interval_seconds: float = 60.0
    feature_extractor: Optional[Callable] = None
    prediction_extractor: Optional[Callable] = None
    confidence_extractor: Optional[Callable] = None
    embedding_extractor: Optional[Callable] = None
    query_extractor: Optional[Callable] = None
    metadata: dict[str, Any] = field(default_factory=dict)


def monitor(
    client: DriftGuardClient,
    model_id: str,
    config: Optional[MonitorConfig] = None,
) -> Callable:
    """Decorator to automatically monitor a prediction function.

    Parameters
    ----------
    client : DriftGuardClient
        An initialized DriftGuard client.
    model_id : str
        The registered model endpoint ID in DriftGuard.
    config : MonitorConfig, optional
        Monitoring configuration. Uses defaults if not provided.

    Returns
    -------
    Decorated function that logs predictions to DriftGuard.

    Examples
    --------
    >>> client = DriftGuardClient(api_key="dg_abc123")
    >>>
    >>> @monitor(client, model_id="my-classifier")
    ... def predict(features: list[float]) -> dict:
    ...     result = model.predict([features])
    ...     return {"prediction": result[0], "confidence": 0.95}
    >>>
    >>> # With custom extractors
    >>> cfg = MonitorConfig(
    ...     feature_extractor=lambda args, kwargs: kwargs.get("X"),
    ...     prediction_extractor=lambda result: result["label"],
    ...     confidence_extractor=lambda result: result["score"],
    ... )
    >>> @monitor(client, model_id="my-model", config=cfg)
    ... def classify(X, **kwargs):
    ...     return {"label": 1, "score": 0.92}
    """
    cfg = config or MonitorConfig()

    def decorator(func: Callable) -> Callable:
        collector = client.collector(model_id, batch_size=cfg.batch_size)
        _last_flush = [time.time()]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            error = None

            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                error = exc
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000

                try:
                    record: dict[str, Any] = {"latency_ms": latency_ms}

                    if error is None:
                        if cfg.capture_features:
                            features = _extract_features(args, kwargs, cfg)
                            if features is not None:
                                record["features"] = features

                        if cfg.capture_predictions and error is None:
                            prediction = _extract_prediction(result, cfg)
                            if prediction is not None:
                                record["prediction"] = prediction

                        if cfg.capture_confidence and error is None:
                            confidence = _extract_confidence(result, cfg)
                            if confidence is not None:
                                record["confidence"] = confidence

                        if cfg.capture_embeddings:
                            embeddings = _extract_embeddings(args, kwargs, result, cfg)
                            if embeddings is not None:
                                record["embeddings"] = embeddings

                        if cfg.capture_queries:
                            query = _extract_query(args, kwargs, cfg)
                            if query is not None:
                                record["query"] = query

                    record["error"] = str(error) if error else None
                    collector.log(**record)

                    # Flush if batch is full or interval exceeded
                    now = time.time()
                    if (
                        collector.buffer_size >= cfg.batch_size
                        or now - _last_flush[0] >= cfg.flush_interval_seconds
                    ):
                        collector.flush()
                        _last_flush[0] = now

                except Exception as log_exc:
                    logger.warning("Failed to log prediction: %s", log_exc)

            return result

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            error = None

            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                error = exc
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000

                try:
                    record: dict[str, Any] = {"latency_ms": latency_ms}

                    if error is None:
                        if cfg.capture_features:
                            features = _extract_features(args, kwargs, cfg)
                            if features is not None:
                                record["features"] = features

                        if cfg.capture_predictions:
                            prediction = _extract_prediction(result, cfg)
                            if prediction is not None:
                                record["prediction"] = prediction

                        if cfg.capture_confidence:
                            confidence = _extract_confidence(result, cfg)
                            if confidence is not None:
                                record["confidence"] = confidence

                        if cfg.capture_embeddings:
                            embeddings = _extract_embeddings(args, kwargs, result, cfg)
                            if embeddings is not None:
                                record["embeddings"] = embeddings

                        if cfg.capture_queries:
                            query = _extract_query(args, kwargs, cfg)
                            if query is not None:
                                record["query"] = query

                    record["error"] = str(error) if error else None
                    collector.log(**record)

                    now = time.time()
                    if (
                        collector.buffer_size >= cfg.batch_size
                        or now - _last_flush[0] >= cfg.flush_interval_seconds
                    ):
                        await collector.flush_async()
                        _last_flush[0] = now

                except Exception as log_exc:
                    logger.warning("Failed to log prediction: %s", log_exc)

            return result

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _extract_features(args: tuple, kwargs: dict, cfg: MonitorConfig) -> Any:
    """Extract feature data from function arguments."""
    if cfg.feature_extractor:
        return cfg.feature_extractor(args, kwargs)
    # Default: first positional argument if it looks like features
    if args:
        first = args[0]
        if isinstance(first, (list, tuple)):
            return first
        if hasattr(first, "tolist"):
            return first.tolist()
    # Check common kwarg names
    for key in ("features", "X", "x", "inputs", "input_data"):
        if key in kwargs:
            val = kwargs[key]
            return val.tolist() if hasattr(val, "tolist") else val
    return None


def _extract_prediction(result: Any, cfg: MonitorConfig) -> Any:
    """Extract prediction value from function return value."""
    if cfg.prediction_extractor:
        return cfg.prediction_extractor(result)
    if isinstance(result, (int, float)):
        return float(result)
    if isinstance(result, dict):
        for key in ("prediction", "pred", "output", "result", "label", "score"):
            if key in result:
                val = result[key]
                return float(val) if isinstance(val, (int, float)) else val
    if hasattr(result, "tolist"):
        arr = result.tolist()
        if isinstance(arr, (int, float)):
            return float(arr)
        if isinstance(arr, list) and len(arr) == 1:
            return float(arr[0])
    return None


def _extract_confidence(result: Any, cfg: MonitorConfig) -> Any:
    """Extract confidence score from function return value."""
    if cfg.confidence_extractor:
        return cfg.confidence_extractor(result)
    if isinstance(result, dict):
        for key in ("confidence", "probability", "prob", "score", "certainty"):
            if key in result:
                val = result[key]
                if isinstance(val, (int, float)):
                    return float(val)
    return None


def _extract_embeddings(args: tuple, kwargs: dict, result: Any, cfg: MonitorConfig) -> Any:
    """Extract embedding vectors."""
    if cfg.embedding_extractor:
        return cfg.embedding_extractor(args, kwargs, result)
    if isinstance(result, dict) and "embedding" in result:
        emb = result["embedding"]
        return emb.tolist() if hasattr(emb, "tolist") else emb
    for key in ("embeddings", "embedding", "vectors"):
        if key in kwargs:
            val = kwargs[key]
            return val.tolist() if hasattr(val, "tolist") else val
    return None


def _extract_query(args: tuple, kwargs: dict, cfg: MonitorConfig) -> Any:
    """Extract query string from function arguments."""
    if cfg.query_extractor:
        return cfg.query_extractor(args, kwargs)
    for key in ("query", "prompt", "text", "question", "input_text"):
        if key in kwargs:
            return str(kwargs[key])
    if args and isinstance(args[0], str):
        return args[0]
    return None
