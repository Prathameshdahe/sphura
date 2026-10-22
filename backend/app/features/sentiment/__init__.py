"""Financial sentiment (fine-tuned DistilBERT → TF-IDF fallback) for the markets feature.

`app.features.market.sentiment` probes this package for a `predict(texts)` callable; it is only exposed while a
trained artifact is present so that, without one, the markets feature keeps its own lexicon fallback silently.
"""
from __future__ import annotations

from app.features.sentiment import model


def __getattr__(name: str):
    if name == "predict" and model.available():
        return model.predict
    raise AttributeError(name)


__all__ = ["model"]
