"""Hash-based embedding fallback when real embedding API is unavailable."""

import hashlib
import math

import numpy as np


class HashEmbeddingProvider:
    """Deterministic pseudo-embedding using n-gram hashing.

    Produces fixed-dimension vectors suitable for approximate lexical matching.
    Not semantic search — used as degradation fallback only.
    """

    def __init__(self, dimension: int = 256):
        self._dimension = dimension
        self.name = "hash-fallback"

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(text) for text in texts]

    def _hash_embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        dim = self._dimension

        # Character n-gram hashing (2, 3, 4-grams)
        for n in (2, 3, 4):
            for i in range(max(1, len(text) - n + 1)):
                gram = text[i:i + n]
                h = hashlib.md5(gram.encode("utf-8")).digest()
                h1 = int.from_bytes(h[0:4], "little")
                h2 = int.from_bytes(h[4:8], "little")
                vec[h1 % dim] += 1.0
                vec[h2 % dim] -= 0.5

        # Word-level hashing
        for word in text.split():
            h = hashlib.md5(word.lower().encode("utf-8")).digest()
            h1 = int.from_bytes(h[0:4], "little")
            vec[h1 % dim] += 2.0

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]

        return vec
