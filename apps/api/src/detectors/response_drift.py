"""Response Drift Detector — Distribution shift in model outputs."""

import numpy as np
from scipy import stats
from typing import Any


class ResponseDriftDetector:
    """Detects distributional shift in model prediction outputs.

    Uses KS test and Wasserstein distance to measure how the output
    distribution has shifted from the baseline.
    """

    DEFAULT_KS_THRESHOLD = 0.05
    DEFAULT_WASSERSTEIN_THRESHOLD = 0.1

    def detect(
        self,
        baseline_data: dict[str, Any],
        current_data: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Run response drift detection.

        Parameters
        ----------
        baseline_data : dict
            Must contain "predictions" key with shape (n_baseline,).
        current_data : list[dict]
            Each entry may contain "predictions".
        config : dict
            Optional keys: method (ks|wasserstein|both), threshold.
        """
        baseline_preds = np.array(baseline_data["predictions"], dtype=np.float64)
        current_preds = self._merge_predictions(current_data)

        if current_preds.size == 0:
            return {"is_drifted": False, "score": 0.0, "details": {"error": "No current predictions to compare"}}

        method = config.get("method", "both")

        ks_result = self._ks_test(baseline_preds, current_preds, config)
        wasserstein_result = self._wasserstein_test(baseline_preds, current_preds, config)

        if method == "ks":
            is_drifted = ks_result["is_drifted"]
            score = ks_result["statistic"]
        elif method == "wasserstein":
            is_drifted = wasserstein_result["is_drifted"]
            score = wasserstein_result["distance"]
        else:
            is_drifted = ks_result["is_drifted"] or wasserstein_result["is_drifted"]
            score = max(ks_result["statistic"], wasserstein_result["normalized_distance"])

        baseline_stats = {
            "mean": round(float(np.mean(baseline_preds)), 6),
            "std": round(float(np.std(baseline_preds)), 6),
            "median": round(float(np.median(baseline_preds)), 6),
            "min": round(float(np.min(baseline_preds)), 6),
            "max": round(float(np.max(baseline_preds)), 6),
            "count": len(baseline_preds),
        }
        current_stats = {
            "mean": round(float(np.mean(current_preds)), 6),
            "std": round(float(np.std(current_preds)), 6),
            "median": round(float(np.median(current_preds)), 6),
            "min": round(float(np.min(current_preds)), 6),
            "max": round(float(np.max(current_preds)), 6),
            "count": len(current_preds),
        }

        return {
            "is_drifted": is_drifted,
            "score": round(float(score), 6),
            "details": {
                "method": method,
                "ks_test": ks_result,
                "wasserstein_test": wasserstein_result,
                "baseline_stats": baseline_stats,
                "current_stats": current_stats,
                "mean_shift": round(float(np.mean(current_preds) - np.mean(baseline_preds)), 6),
                "std_ratio": round(float(np.std(current_preds) / max(np.std(baseline_preds), 1e-10)), 6),
            },
        }

    def _ks_test(self, baseline: np.ndarray, current: np.ndarray, config: dict) -> dict:
        threshold = config.get("ks_threshold", self.DEFAULT_KS_THRESHOLD)
        statistic, p_value = stats.ks_2samp(baseline, current)
        return {
            "statistic": round(float(statistic), 6),
            "p_value": round(float(p_value), 6),
            "threshold": threshold,
            "is_drifted": p_value < threshold,
        }

    def _wasserstein_test(self, baseline: np.ndarray, current: np.ndarray, config: dict) -> dict:
        threshold = config.get("wasserstein_threshold", self.DEFAULT_WASSERSTEIN_THRESHOLD)
        distance = float(stats.wasserstein_distance(baseline, current))

        # Normalize by baseline range for comparability
        baseline_range = float(np.ptp(baseline))
        normalized = distance / max(baseline_range, 1e-10)

        return {
            "distance": round(distance, 6),
            "normalized_distance": round(normalized, 6),
            "threshold": threshold,
            "is_drifted": normalized >= threshold,
        }

    @staticmethod
    def _merge_predictions(data_records: list[dict]) -> np.ndarray:
        all_preds: list = []
        for record in data_records:
            data = record.get("data", record)
            preds = data.get("predictions")
            if preds is not None:
                all_preds.extend(preds)
        if not all_preds:
            return np.array([])
        return np.array(all_preds, dtype=np.float64)
