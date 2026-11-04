"""Traditional-ML transaction classifier (TF-IDF + multinomial logistic regression).

Features
  * word TF-IDF (uni+bi-grams) over the narration, digits masked, plus meta
    tokens for direction (__dr__/__cr__), statement type, payment channel and an
    order-of-magnitude amount bucket
  * character TF-IDF (2–5-grams, word-bounded) — robust to the glued-together,
    truncated and misspelt merchant names common in Indian narrations
Logistic regression gives calibrated-enough probabilities for a review
threshold and per-class coefficients we can turn into explanations.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

from .narration import parse
from .synth import Example, generate

log = logging.getLogger(__name__)

BUNDLED_DIR = Path(__file__).parent / "model"
RUNTIME_DIR = Path(os.environ.get("BEFREE_DATA_DIR", Path(__file__).resolve().parents[2] / "data" / "runtime")) / "model"
MODEL_FILE = "classifier.joblib"
CARD_FILE = "model_card.json"


def _mask(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\S*@\S*", " vpa ", t)
    t = re.sub(r"\d+", "0", t)
    return re.sub(r"[^a-z0 ]+", " ", t)


def meta_text(text: str, is_debit: bool, amount: float, statement_type: str) -> str:
    n = parse(text)
    bucket = int(math.log10(max(abs(amount), 1)))
    return (f"__{'dr' if is_debit else 'cr'}__ __{'cc' if statement_type == 'credit_card' else 'sb'}__ "
            f"__ch_{n.channel.lower()}__ __amt{bucket}__ "
            f"{'__mvpa__ ' if n.is_merchant_vpa else ''}{_mask(text)}")


def _strip_meta(s: str) -> str:
    return re.sub(r"__\w+__", " ", s)


def _word_tokens(s: str) -> list[str]:
    return re.findall(r"__\w+__|[a-z]{2,}", s)


def build_pipeline() -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(tokenizer=_word_tokens, token_pattern=None, lowercase=False, ngram_range=(1, 2),
                                 min_df=2, sublinear_tf=True)),
        ("char", TfidfVectorizer(preprocessor=_strip_meta, analyzer="char_wb", ngram_range=(2, 5), min_df=3,
                                 max_features=80000, sublinear_tf=True)),
    ])
    clf = LogisticRegression(C=8.0, max_iter=3000, class_weight="balanced")
    return Pipeline([("features", features), ("clf", clf)])


@dataclass
class Prediction:
    category: str
    confidence: float
    top: list[tuple[str, float]]  # alternative categories
    cues: list[str]               # words that pushed towards the prediction
    proba: dict[str, float]       # full distribution (for direction-aware renormalisation)


class Model:
    def __init__(self, pipeline: Pipeline, card: dict):
        self.pipeline = pipeline
        self.card = card
        self.classes_ = [str(c) for c in pipeline.named_steps["clf"].classes_]
        word_vec: TfidfVectorizer = pipeline.named_steps["features"].transformer_list[0][1]
        self._n_word = len(word_vec.vocabulary_)
        self._word_names = word_vec.get_feature_names_out()

    def predict(self, texts: list[str], is_debit: list[bool], amounts: list[float], stypes: list[str]) -> list[Prediction]:
        if not texts:
            return []
        X_text = [meta_text(t, d, a, s) for t, d, a, s in zip(texts, is_debit, amounts, stypes)]
        feats = self.pipeline.named_steps["features"].transform(X_text)
        clf: LogisticRegression = self.pipeline.named_steps["clf"]
        proba = clf.predict_proba(feats)
        out = []
        for i in range(len(texts)):
            order = np.argsort(-proba[i])
            best = order[0]
            top = [(self.classes_[j], float(proba[i, j])) for j in order[:3]]
            row = feats[i, : self._n_word].tocoo()
            contrib = [(self._word_names[c], v * clf.coef_[best, c]) for c, v in zip(row.col, row.data)]
            cues = [w for w, s in sorted(contrib, key=lambda x: -x[1]) if s > 0 and not w.startswith("__")][:3]
            dist = {c: float(proba[i, j]) for j, c in enumerate(self.classes_)}
            # No known words at all (only meta tokens / char noise): the model is guessing from
            # direction and channel, so don't let it claim high confidence.
            known_words = sum(1 for c in row.col if not self._word_names[c].startswith("__"))
            if known_words == 0:
                dist = {c: v * 0.6 for c, v in dist.items()}
            out.append(Prediction(self.classes_[best], float(proba[i, best]), top, cues, dist))
        return out


_model: Optional[Model] = None
_lock = threading.RLock()


def _xy(examples: list[Example]) -> tuple[list[str], list[str]]:
    return [meta_text(e.text, e.is_debit, e.amount, e.statement_type) for e in examples], [e.label for e in examples]


def train(extra: Optional[list[Example]] = None, extra_weight: int = 8, n: int = 24000, save_dir: Path = RUNTIME_DIR,
          gold: Optional[list[Example]] = None) -> Model:
    """Train on synthetic data (+ user corrections, up-weighted by repetition)."""
    t0 = time.perf_counter()
    train_ex = generate(n=n, seed=7, split="train")
    if extra:
        train_ex = train_ex + [e for e in extra for _ in range(extra_weight)]
    X, y = _xy(train_ex)
    pipe = build_pipeline()
    pipe.fit(X, y)
    secs = time.perf_counter() - t0

    test_ex = generate(n=4000, seed=99, split="test")
    Xt, yt = _xy(test_ex)
    pred = pipe.predict(Xt)
    card = {
        "algorithm": "TF-IDF (word 1–2-grams + char 2–5-grams) → multinomial logistic regression",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "training_examples": len(train_ex),
        "user_corrections": len(extra or []),
        "classes": sorted(set(y)),
        "holdout": {
            "description": "Synthetic narrations built from person names and business stems never seen in training",
            "examples": len(test_ex),
            "accuracy": round(float(accuracy_score(yt, pred)), 4),
            "macro_f1": round(float(f1_score(yt, pred, average="macro")), 4),
        },
        "train_seconds": round(secs, 1),
    }
    if gold:
        Xg, yg = _xy(gold)
        pg = pipe.predict(Xg)
        card["gold"] = {"description": "Hand-labelled narrations from real sample statements (model only, no rules)",
                        "examples": len(gold), "accuracy": round(float(accuracy_score(yg, pg)), 4)}
    save_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, save_dir / MODEL_FILE, compress=3)
    (save_dir / CARD_FILE).write_text(json.dumps(card, indent=2))
    model = Model(pipe, card)
    global _model
    with _lock:
        _model = model
    log.info("trained classifier in %.1fs: %s", secs, card["holdout"])
    return model


def get_model() -> Model:
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        for d in (RUNTIME_DIR, BUNDLED_DIR):
            f = d / MODEL_FILE
            if f.exists():
                try:
                    pipe = joblib.load(f)
                    card = json.loads((d / CARD_FILE).read_text()) if (d / CARD_FILE).exists() else {}
                    _model = Model(pipe, card)
                    return _model
                except Exception as e:  # noqa: BLE001  (version skew etc.)
                    log.warning("could not load model from %s: %s", f, e)
    return train(save_dir=BUNDLED_DIR)
