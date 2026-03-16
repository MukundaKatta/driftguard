"""Query Pattern Drift Detector — Clustering shift in input query patterns."""

import hashlib
import numpy as np
from collections import Counter
from scipy import stats
from scipy.spatial.distance import cosine
from typing import Any


class QueryPatternDriftDetector:
    """Detects shift in input query patterns using text-based heuristics.

    Since we cannot assume a particular embedding model is available,
    this detector uses lightweight text features:
    - Token length distribution
    - Character-level n-gram frequency vectors
    - Query category distribution (via hashing buckets)
    - Vocabulary overlap analysis
    """

    DEFAULT_THRESHOLD = 0.15
    DEFAULT_N_BUCKETS = 64
    DEFAULT_NGRAM_SIZE = 3

    def detect(
        self,
        baseline_data: dict[str, Any],
        current_data: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Run query pattern drift detection.

        Parameters
        ----------
        baseline_data : dict
            Must contain "queries" key with list of query strings.
        current_data : list[dict]
            Each entry may contain "queries".
        config : dict
            Optional keys: threshold, n_buckets, ngram_size.
        """
        baseline_queries: list[str] = baseline_data["queries"]
        current_queries = self._merge_queries(current_data)

        if not current_queries:
            return {"is_drifted": False, "score": 0.0, "details": {"error": "No current queries to compare"}}

        threshold = config.get("threshold", self.DEFAULT_THRESHOLD)
        n_buckets = config.get("n_buckets", self.DEFAULT_N_BUCKETS)
        ngram_size = config.get("ngram_size", self.DEFAULT_NGRAM_SIZE)

        # 1. Token length distribution drift
        length_result = self._length_distribution_drift(baseline_queries, current_queries)

        # 2. N-gram frequency drift
        ngram_result = self._ngram_drift(baseline_queries, current_queries, ngram_size)

        # 3. Hash-bucket distribution drift
        bucket_result = self._bucket_distribution_drift(baseline_queries, current_queries, n_buckets)

        # 4. Vocabulary overlap
        vocab_result = self._vocabulary_overlap(baseline_queries, current_queries)

        # Composite score: weighted average of individual signals
        weights = config.get("weights", {"length": 0.2, "ngram": 0.3, "bucket": 0.3, "vocab": 0.2})
        composite_score = (
            weights.get("length", 0.2) * length_result["score"]
            + weights.get("ngram", 0.3) * ngram_result["score"]
            + weights.get("bucket", 0.3) * bucket_result["score"]
            + weights.get("vocab", 0.2) * vocab_result["score"]
        )

        is_drifted = composite_score >= threshold

        return {
            "is_drifted": is_drifted,
            "score": round(composite_score, 6),
            "details": {
                "composite_threshold": threshold,
                "length_distribution": length_result,
                "ngram_frequency": ngram_result,
                "bucket_distribution": bucket_result,
                "vocabulary_overlap": vocab_result,
                "baseline_query_count": len(baseline_queries),
                "current_query_count": len(current_queries),
            },
        }

    def _length_distribution_drift(self, baseline: list[str], current: list[str]) -> dict:
        baseline_lengths = np.array([len(q.split()) for q in baseline], dtype=np.float64)
        current_lengths = np.array([len(q.split()) for q in current], dtype=np.float64)

        if len(baseline_lengths) < 2 or len(current_lengths) < 2:
            return {"score": 0.0, "details": "Insufficient data"}

        ks_stat, ks_p = stats.ks_2samp(baseline_lengths, current_lengths)

        return {
            "score": round(float(ks_stat), 6),
            "ks_statistic": round(float(ks_stat), 6),
            "ks_p_value": round(float(ks_p), 6),
            "baseline_mean_length": round(float(np.mean(baseline_lengths)), 2),
            "current_mean_length": round(float(np.mean(current_lengths)), 2),
        }

    def _ngram_drift(self, baseline: list[str], current: list[str], n: int) -> dict:
        baseline_ngrams = self._extract_ngram_vector(baseline, n)
        current_ngrams = self._extract_ngram_vector(current, n)

        all_keys = set(baseline_ngrams.keys()) | set(current_ngrams.keys())
        if not all_keys:
            return {"score": 0.0, "details": "No n-grams found"}

        b_vec = np.array([baseline_ngrams.get(k, 0) for k in all_keys], dtype=np.float64)
        c_vec = np.array([current_ngrams.get(k, 0) for k in all_keys], dtype=np.float64)

        b_norm = b_vec / max(b_vec.sum(), 1)
        c_norm = c_vec / max(c_vec.sum(), 1)

        cos_dist = float(cosine(b_norm, c_norm)) if np.any(b_norm) and np.any(c_norm) else 0.0

        return {
            "score": round(min(cos_dist, 1.0), 6),
            "cosine_distance": round(cos_dist, 6),
            "unique_ngrams_baseline": len(baseline_ngrams),
            "unique_ngrams_current": len(current_ngrams),
        }

    def _bucket_distribution_drift(self, baseline: list[str], current: list[str], n_buckets: int) -> dict:
        baseline_buckets = np.zeros(n_buckets, dtype=np.float64)
        current_buckets = np.zeros(n_buckets, dtype=np.float64)

        for q in baseline:
            idx = int(hashlib.md5(q.lower().strip().encode()).hexdigest(), 16) % n_buckets
            baseline_buckets[idx] += 1
        for q in current:
            idx = int(hashlib.md5(q.lower().strip().encode()).hexdigest(), 16) % n_buckets
            current_buckets[idx] += 1

        b_norm = baseline_buckets / max(baseline_buckets.sum(), 1)
        c_norm = current_buckets / max(current_buckets.sum(), 1)

        js_divergence = self._jensen_shannon_divergence(b_norm, c_norm)

        return {
            "score": round(js_divergence, 6),
            "jensen_shannon_divergence": round(js_divergence, 6),
            "n_buckets": n_buckets,
        }

    def _vocabulary_overlap(self, baseline: list[str], current: list[str]) -> dict:
        baseline_vocab = set()
        for q in baseline:
            baseline_vocab.update(q.lower().split())

        current_vocab = set()
        for q in current:
            current_vocab.update(q.lower().split())

        if not baseline_vocab and not current_vocab:
            return {"score": 0.0, "overlap": 1.0, "new_token_ratio": 0.0}

        overlap = len(baseline_vocab & current_vocab)
        union = len(baseline_vocab | current_vocab)
        jaccard = overlap / max(union, 1)

        new_tokens = current_vocab - baseline_vocab
        new_ratio = len(new_tokens) / max(len(current_vocab), 1)

        # Score inversely proportional to overlap
        score = 1.0 - jaccard

        return {
            "score": round(score, 6),
            "jaccard_similarity": round(jaccard, 6),
            "new_token_ratio": round(new_ratio, 6),
            "baseline_vocab_size": len(baseline_vocab),
            "current_vocab_size": len(current_vocab),
            "new_tokens_count": len(new_tokens),
        }

    @staticmethod
    def _extract_ngram_vector(queries: list[str], n: int) -> dict[str, int]:
        counter: Counter = Counter()
        for q in queries:
            text = q.lower().strip()
            for i in range(max(len(text) - n + 1, 0)):
                counter[text[i:i + n]] += 1
        return dict(counter)

    @staticmethod
    def _jensen_shannon_divergence(p: np.ndarray, q: np.ndarray) -> float:
        eps = 1e-10
        p = p + eps
        q = q + eps
        p = p / p.sum()
        q = q / q.sum()
        m = 0.5 * (p + q)
        jsd = 0.5 * float(np.sum(p * np.log(p / m))) + 0.5 * float(np.sum(q * np.log(q / m)))
        return max(jsd, 0.0)

    @staticmethod
    def _merge_queries(data_records: list[dict]) -> list[str]:
        all_queries: list[str] = []
        for record in data_records:
            data = record.get("data", record)
            queries = data.get("queries")
            if queries is not None:
                all_queries.extend(queries)
        return all_queries
