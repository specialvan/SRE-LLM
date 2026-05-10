"""Tests for PCA hidden-score extractor (§4)."""
from __future__ import annotations

import numpy as np

from gan_matchmaking import HiddenScoreExtractor


def test_explained_variance_covers_most_of_signal():
    rng = np.random.default_rng(0)
    # Generate data with a strong 1D structure plus small noise.
    z = rng.normal(size=(500, 1))
    W = rng.normal(size=(1, 6))
    X = z @ W + 0.05 * rng.normal(size=(500, 6))
    pca = HiddenScoreExtractor(n_components=2).fit(X)
    assert pca.explained_variance_ratio_[0] > 0.9


def test_transform_recovers_latent_up_to_sign():
    rng = np.random.default_rng(1)
    z = rng.normal(size=(300, 1))
    W = rng.normal(size=(1, 4))
    X = z @ W
    pca = HiddenScoreExtractor(n_components=1).fit(X)
    z_hat = pca.transform(X)
    corr = abs(np.corrcoef(z.ravel(), z_hat.ravel())[0, 1])
    assert corr > 0.99
