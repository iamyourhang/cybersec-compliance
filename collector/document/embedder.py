"""
collector/document/embedder.py
OpenAI 兼容 embedding 客户端。
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, List

from openai import OpenAI

from config.settings import get_settings


class EmbeddingService:
    def __init__(self):
        settings = get_settings()
        cfg = settings.embedding
        self._dimensions = cfg.dimensions
        self._client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url) if cfg.api_key else None
        self._model = cfg.model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        items = list(texts)
        if not items:
            return []
        if self._client is None:
            return [self._local_embed(text) for text in items]
        resp = self._client.embeddings.create(
            model=self._model,
            input=items,
            dimensions=self._dimensions,
        )
        vectors = [item.embedding for item in resp.data]
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise ValueError(
                    f"embedding 维度不匹配，期望 {self._dimensions}，实际 {len(vector)}"
                )
        return vectors

    def _local_embed(self, text: str) -> List[float]:
        vector = [0.0] * self._dimensions
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = -1.0 if digest[4] % 2 else 1.0
            weight = 1.0 + (digest[5] / 255.0)
            vector[slot] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]
