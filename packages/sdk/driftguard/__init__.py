"""DriftGuard SDK — Instrument ML models for drift monitoring.

Usage::

    from driftguard import DriftGuardClient, monitor

    client = DriftGuardClient(api_key="dg_...", endpoint="https://api.driftguard.io")

    # Option 1: Decorator
    @monitor(client, model_id="my-model")
    def predict(features):
        return model.predict(features)

    # Option 2: Manual instrumentation
    with client.collector("my-model") as collector:
        result = model.predict(features)
        collector.log(features=features, prediction=result, confidence=0.95)
"""

from .monitor import monitor, MonitorConfig
from .collector import DriftGuardClient, Collector
from .reporter import Reporter

__version__ = "1.0.0"
__all__ = ["DriftGuardClient", "Collector", "Reporter", "monitor", "MonitorConfig"]
