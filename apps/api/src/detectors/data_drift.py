"""Data Drift Detector — KS Test, PSI, Chi-Squared on feature distributions."""

import numpy as np
from scipy import stats
from typing import Any


class DataDriftDetector:
    """Detects distributional shift in input features using statistical tests.

    Supported methods:
    - Kolmogorov-Smirnov (KS) test for continuous features
    - Population Stability Index (PSI) for binned distributions
    - Chi-Squared test for categorical features
    """

    DEFAULT_KS_THRESHOLD = 0.05
    DEFAULT_PSI_THRESHOLD = 0.2
    DEFAULT_CHI2_THRESHOLD = 0.05
    DEFAULT_NUM_BINS = 10

    def detect(
        self,
        baseline_data: dict[str, Any],
        current_data: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Run data drift detection across all features.

        Parameters
        ----------
        baseline_data : dict
            Must contain "features" key with shape (n_baseline, n_features).
        current_data : list[dict]
            Each entry may contain "features" with shape (batch, n_features).
        config : dict
            Optional keys: method (ks|psi|chi2), threshold, num_bins, feature_names.

        Returns
        -------
        dict with keys: is_drifted, score, details
        """
        baseline_features = np.array(baseline_data["features"], dtype=np.float64)
        current_features = self._merge_features(current_data)

        if current_features.size == 0:
            return {"is_drifted": False, "score": 0.0, "details": {"error": "No current features to compare"}}

        method = config.get("method", "ks")
        feature_names = config.get("feature_names", [f"feature_{i}" for i in range(baseline_features.shape[1])])

        n_features = min(baseline_features.shape[1], current_features.shape[1])
        feature_results: list[dict] = []

        for i in range(n_features):
            baseline_col = baseline_features[:, i]
            current_col = current_features[:, i]
            name = feature_names[i] if i < len(feature_names) else f"feature_{i}"

            if method == "psi":
                result = self._psi_test(baseline_col, current_col, config)
            elif method == "chi2":
                result = self._chi2_test(baseline_col, current_col, config)
            else:
                result = self._ks_test(baseline_col, current_col, config)

            result["feature_name"] = name
            result["feature_index"] = i
            feature_results.append(result)

        drifted_features = [r for r in feature_results if r["is_drifted"]]
        drift_ratio = len(drifted_features) / max(len(feature_results), 1)
        overall_score = float(np.mean([r["score"] for r in feature_results])) if feature_results else 0.0

        drift_threshold = config.get("drift_feature_ratio", 0.5)
        is_drifted = drift_ratio >= drift_threshold

        return {
            "is_drifted": is_drifted,
            "score": round(overall_score, 6),
            "details": {
                "method": method,
                "total_features": n_features,
                "drifted_features": len(drifted_features),
                "drift_ratio": round(drift_ratio, 4),
                "feature_results": feature_results,
            },
        }

    def _ks_test(self, baseline: np.ndarray, current: np.ndarray, config: dict) -> dict:
        threshold = config.get("ks_threshold", self.DEFAULT_KS_THRESHOLD)
        statistic, p_value = stats.ks_2samp(baseline, current)
        return {
            "method": "ks",
            "statistic": round(float(statistic), 6),
            "p_value": round(float(p_value), 6),
            "threshold": threshold,
            "is_drifted": p_value < threshold,
            "score": round(float(statistic), 6),
        }

    def _psi_test(self, baseline: np.ndarray, current: np.ndarray, config: dict) -> dict:
        threshold = config.get("psi_threshold", self.DEFAULT_PSI_THRESHOLD)
        num_bins = config.get("num_bins", self.DEFAULT_NUM_BINS)

        combined_min = min(baseline.min(), current.min())
        combined_max = max(baseline.max(), current.max())
        bins = np.linspace(combined_min, combined_max, num_bins + 1)

        baseline_counts = np.histogram(baseline, bins=bins)[0].astype(np.float64)
        current_counts = np.histogram(current, bins=bins)[0].astype(np.float64)

        # Add small epsilon to avoid division by zero
        eps = 1e-6
        baseline_pct = (baseline_counts + eps) / (baseline_counts.sum() + eps * num_bins)
        current_pct = (current_counts + eps) / (current_counts.sum() + eps * num_bins)

        psi_value = float(np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct)))

        return {
            "method": "psi",
            "statistic": round(psi_value, 6),
            "p_value": None,
            "threshold": threshold,
            "is_drifted": psi_value >= threshold,
            "score": round(psi_value, 6),
        }

    def _chi2_test(self, baseline: np.ndarray, current: np.ndarray, config: dict) -> dict:
        threshold = config.get("chi2_threshold", self.DEFAULT_CHI2_THRESHOLD)
        num_bins = config.get("num_bins", self.DEFAULT_NUM_BINS)

        combined_min = min(baseline.min(), current.min())
        combined_max = max(baseline.max(), current.max())
        bins = np.linspace(combined_min, combined_max, num_bins + 1)

        baseline_counts = np.histogram(baseline, bins=bins)[0].astype(np.float64)
        current_counts = np.histogram(current, bins=bins)[0].astype(np.float64)

        # Ensure no zero expected values
        baseline_counts = np.maximum(baseline_counts, 1.0)

        # Scale current counts to match baseline total for valid chi2
        scale = baseline_counts.sum() / max(current_counts.sum(), 1.0)
        current_scaled = current_counts * scale

        statistic, p_value = stats.chisquare(current_scaled, f_exp=baseline_counts)

        return {
            "method": "chi2",
            "statistic": round(float(statistic), 6),
            "p_value": round(float(p_value), 6),
            "threshold": threshold,
            "is_drifted": p_value < threshold,
            "score": round(float(statistic), 6),
        }

    @staticmethod
    def _merge_features(data_records: list[dict]) -> np.ndarray:
        """Merge features from multiple ingested batches."""
        all_features: list = []
        for record in data_records:
            data = record.get("data", record)
            features = data.get("features")
            if features is not None:
                all_features.extend(features)
        if not all_features:
            return np.array([])
        return np.array(all_features, dtype=np.float64)
