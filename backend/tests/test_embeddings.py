"""Tests for embeddings — offline tests use FakeEmbedder; slow tests use the real model."""
import numpy as np
import pytest

from tests.fakes import FakeEmbedder


# ---------------------------------------------------------------------------
# FakeEmbedder (offline)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fake_embedder_shape() -> None:
    emb = FakeEmbedder()
    arr = await emb.embed(["hello world", "foo bar"])
    assert arr.shape == (2, FakeEmbedder.DIM)
    assert arr.dtype == np.float32


@pytest.mark.asyncio
async def test_fake_embedder_normalised() -> None:
    emb = FakeEmbedder()
    arr = await emb.embed(["hello world"])
    norm = float(np.linalg.norm(arr[0]))
    assert abs(norm - 1.0) < 1e-5


@pytest.mark.asyncio
async def test_fake_embedder_query_shape() -> None:
    emb = FakeEmbedder()
    vec = await emb.embed_query("test")
    assert vec.shape == (FakeEmbedder.DIM,)


@pytest.mark.asyncio
async def test_fake_embedder_similar_texts_score_higher() -> None:
    emb = FakeEmbedder()
    vecs = await emb.embed(["machine learning neural network", "machine learning neural network", "cooking pasta recipe"])
    # identical texts → cosine = 1.0
    assert float(np.dot(vecs[0], vecs[1])) > 0.99
    # unrelated text → lower score
    assert float(np.dot(vecs[0], vecs[2])) < float(np.dot(vecs[0], vecs[1]))


# ---------------------------------------------------------------------------
# Real SentenceTransformerEmbedder (slow — requires model download)
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.asyncio
async def test_real_embedder_shape_and_normalisation() -> None:
    from app.services.embeddings import SentenceTransformerEmbedder
    emb = SentenceTransformerEmbedder()
    arr = await emb.embed(["hello world"])
    assert arr.ndim == 2
    assert arr.shape[0] == 1
    norm = float(np.linalg.norm(arr[0]))
    assert abs(norm - 1.0) < 1e-5
