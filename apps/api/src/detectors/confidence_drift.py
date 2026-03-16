"""Confidence Drift Detector — Prediction confidence degradation over time."""

import numpy as np
from scipy import stats
from typing import Any


class ConfidenceDriftDetector:
    """Detects degradation in model prediction confidence scores.

    Monitors both the mean confidence level and the distributional shape
    of confidence scores relative to a baseline period.
    """

    DEFAULT_MEAN_DROP_THRESHOLD = 0.05
    DEFAULT_KS_THRESHOLD = 0.05
    DEFAULT_LOW_CONFIDENCE_RATIO_THRESHOLD = 0.3

    def detect(
        self,
        baseline_data: dict[str, Any],
        current_data: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Run confidence drift detection.

        Parameters
        ----------
        baseline_data : dict
            Must contain "confidences" key with shape (n_baseline,).
        current_data : list[dict]
            Each entry may contain "confidences".
        config : dict
            Optional keys: mean_drop_threshold, ks_threshold,
            low_confidence_cutoff, low_confidence_ratio_threshold.
        """
        baseline_conf = np.array(baseline_data["confidences"], dtype=np.float64)
        current_conf = self._merge_confidences(current_data)

        if current_conf.size == 0:
            return {"is_drifted": False, "score": 0.0, "details": {"error": "No current confidence scores to compare"}}

        mean_drop_threshold = config.get("mean_drop_threshold", self.DEFAULT_MEAN_DROP_THRESHOLD)
        ks_threshold = config.get("ks_threshold", self.DEFAULT_KS_THRESHOLD)
        low_conf_cutoff = config.get("low_confidence_cutoff", 0.5)
        low_conf_ratio_threshold = config.get("low_confidence_ratio_threshold", self.DEFAULT_LOW_CONFIDENCE_RATIO_THRESHOLD)

        baseline_mean = float(np.mean(baseline_conf))
        current_mean = float(np.mean(current_conf))
        mean_drop = baseline_mean - current_mean

        # KS test on confidence distributions
        ks_stat, ks_p = stats.ks_2samp(baseline_conf, current_conf)

        # Low-confidence ratio analysis
        baseline_low_ratio = float(np.mean(baseline_conf < low_conf_cutoff))
        current_low_ratio = float(np.mean(current_conf < low_conf_cutoff))

        # Trend detection using Mann-Kendall-like monotonic trend
        # Split current data into windows and check for declining trend
        window_size = max(len(current_conf) // 5, 10)
        window_means = []
        for i in range(0, len(current_conf) - window_size + 1, window_size):
            window_means.append(float(np.mean(current_conf[i:i + window_size])))

        has_declining_trend = False
        if len(window_means) >= 3:
            diffs = np.diff(window_means)
            has_declining_trend = float(np.mean(diffs < 0)) > 0.6

        # Determine drift
        mean_drifted = mean_drop >= mean_drop_threshold
        distribution_drifted = ks_p < ks_threshold
        low_conf_drifted = current_low_ratio >= low_conf_ratio_threshold and current_low_ratio > baseline_low_ratio * 1.5

        is_drifted = mean_drifted or distribution_drifted or low_conf_drifted

        # Score: normalized confidence degradation (0 = identical, 1 = severe)
        score = min(1.0, max(0.0, mean_drop / max(baseline_mean, 1e-10)))

        return {
            "is_drifted": is_drifted,
            "score": round(score, 6),
            "details": {
                "baseline_mean_confidence": round(baseline_mean, 6),
                "current_mean_confidence": round(current_mean, 6),
                "mean_confidence_drop": round(mean_drop, 6),
                "mean_drop_threshold": mean_drop_threshold,
                "mean_drifted": mean_drifted,
                "ks_statistic": round(float(ks_stat), 6),
                "ks_p_value": round(float(ks_p), 6),
                "ks_threshold": ks_threshold,
                "distribution_drifted": distribution_drifted,
                "baseline_low_confidence_ratio": round(baseline_low_ratio, 6),
                "current_low_confidence_ratio": round(current_low_ratio, 6),
                "low_confidence_cutoff": low_conf_cutoff,
                "low_confidence_drifted": low_conf_drifted,
                "has_declining_trend": has_declining_trend,
                "window_means": [round(m, 6) for m in window_means],
                "baseline_std": round(float(np.std(baseline_conf)), 6),
                "current_std": round(float(np.std(current_conf)), 6),
                "baseline_count": len(baseline_conf),
                "current_count": len(current_conf),
            },
        }

    @staticmethod
    def _merge_confidences(data_records: list[dict]) -> np.ndarray:
        all_conf: list = []
        for record in data_records:
            data = record.get("data", record)
            confs = data.get("confidences")
            if confs is not None:
                all_conf.extend(confs)
        if not all_conf:
            return np.array([])
        return np.array(all_conf, dtype=np.float64)
