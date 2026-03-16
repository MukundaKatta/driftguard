"""Embedding Drift Detector — Cosine distance and MMD between embedding batches."""

import numpy as np
from scipy.spatial.distance import cdist
from typing import Any


class EmbeddingDriftDetector:
    """Detects shift in embedding space using distance-based metrics.

    Supported methods:
    - cosine: Mean pairwise cosine distance between baseline and current centroids
    - mmd: Maximum Mean Discrepancy with RBF kernel
    """

    DEFAULT_COSINE_THRESHOLD = 0.15
    DEFAULT_MMD_THRESHOLD = 0.05
    DEFAULT_MMD_GAMMA = 1.0

    def detect(
        self,
        baseline_data: dict[str, Any],
        current_data: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Run embedding drift detection.

        Parameters
        ----------
        baseline_data : dict
            Must contain "embeddings" key with shape (n_baseline, embedding_dim).
        current_data : list[dict]
            Each entry may contain "embeddings" with shape (batch, embedding_dim).
        config : dict
            Optional keys: method (cosine|mmd), threshold, mmd_gamma.
        """
        baseline_emb = np.array(baseline_data["embeddings"], dtype=np.float64)
        current_emb = self._merge_embeddings(current_data)

        if current_emb.size == 0:
            return {"is_drifted": False, "score": 0.0, "details": {"error": "No current embeddings to compare"}}

        method = config.get("method", "cosine")

        if method == "mmd":
            return self._mmd_test(baseline_emb, current_emb, config)
        return self._cosine_test(baseline_emb, current_emb, config)

    def _cosine_test(self, baseline: np.ndarray, current: np.ndarray, config: dict) -> dict:
        threshold = config.get("cosine_threshold", self.DEFAULT_COSINE_THRESHOLD)

        baseline_centroid = baseline.mean(axis=0, keepdims=True)
        current_centroid = current.mean(axis=0, keepdims=True)

        centroid_distance = float(cdist(baseline_centroid, current_centroid, metric="cosine")[0, 0])

        # Also compute distribution of pairwise distances for detail
        sample_size = min(500, len(baseline), len(current))
        b_sample = baseline[np.random.choice(len(baseline), sample_size, replace=True)]
        c_sample = current[np.random.choice(len(current), sample_size, replace=True)]

        intra_baseline = float(np.mean(cdist(b_sample[:50], b_sample[50:100], metric="cosine")))
        intra_current = float(np.mean(cdist(c_sample[:50], c_sample[50:100], metric="cosine")))
        inter_distance = float(np.mean(cdist(b_sample[:100], c_sample[:100], metric="cosine")))

        is_drifted = centroid_distance >= threshold

        return {
            "is_drifted": is_drifted,
            "score": round(centroid_distance, 6),
            "details": {
                "method": "cosine",
                "centroid_distance": round(centroid_distance, 6),
                "intra_baseline_distance": round(intra_baseline, 6),
                "intra_current_distance": round(intra_current, 6),
                "inter_distance": round(inter_distance, 6),
                "threshold": threshold,
                "baseline_count": len(baseline),
                "current_count": len(current),
            },
        }

    def _mmd_test(self, baseline: np.ndarray, current: np.ndarray, config: dict) -> dict:
        threshold = config.get("mmd_threshold", self.DEFAULT_MMD_THRESHOLD)
        gamma = config.get("mmd_gamma", self.DEFAULT_MMD_GAMMA)

        # Subsample for computational efficiency
        max_samples = config.get("max_samples", 1000)
        if len(baseline) > max_samples:
            baseline = baseline[np.random.choice(len(baseline), max_samples, replace=False)]
        if len(current) > max_samples:
            current = current[np.random.choice(len(current), max_samples, replace=False)]

        mmd_value = self._compute_mmd(baseline, current, gamma)

        # Permutation test for p-value estimation
        n_permutations = config.get("n_permutations", 100)
        combined = np.vstack([baseline, current])
        n_b = len(baseline)
        perm_mmds = []
        for _ in range(n_permutations):
            perm = np.random.permutation(len(combined))
            perm_b = combined[perm[:n_b]]
            perm_c = combined[perm[n_b:]]
            perm_mmds.append(self._compute_mmd(perm_b, perm_c, gamma))

        p_value = float(np.mean(np.array(perm_mmds) >= mmd_value))

        is_drifted = mmd_value >= threshold

        return {
            "is_drifted": is_drifted,
            "score": round(float(mmd_value), 6),
            "details": {
                "method": "mmd",
                "mmd_value": round(float(mmd_value), 6),
                "p_value": round(p_value, 6),
                "threshold": threshold,
                "gamma": gamma,
                "baseline_count": len(baseline),
                "current_count": len(current),
                "permutation_mean": round(float(np.mean(perm_mmds)), 6),
                "permutation_std": round(float(np.std(perm_mmds)), 6),
            },
        }

    @staticmethod
    def _compute_mmd(x: np.ndarray, y: np.ndarray, gamma: float) -> float:
        """Compute MMD^2 with RBF kernel."""
        xx = cdist(x, x, metric="sqeuclidean")
        yy = cdist(y, y, metric="sqeuclidean")
        xy = cdist(x, y, metric="sqeuclidean")

        k_xx = np.exp(-gamma * xx)
        k_yy = np.exp(-gamma * yy)
        k_xy = np.exp(-gamma * xy)

        m = len(x)
        n = len(y)

        mmd_sq = (k_xx.sum() / (m * m)) + (k_yy.sum() / (n * n)) - 2 * (k_xy.sum() / (m * n))
        return max(float(mmd_sq), 0.0)

    @staticmethod
    def _merge_embeddings(data_records: list[dict]) -> np.ndarray:
        all_embeddings: list = []
        for record in data_records:
            data = record.get("data", record)
            embs = data.get("embeddings")
            if embs is not None:
                all_embeddings.extend(embs)
        if not all_embeddings:
            return np.array([])
        return np.array(all_embeddings, dtype=np.float64)
