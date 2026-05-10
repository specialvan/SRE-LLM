"""Offline training helpers.

The SRE self-iteration pipeline keeps an append-only log of every release
outcome in ``ObservationRepository``. This package turns that log into
updated Cox / EOMM weights so the online pipeline can stop running on the
bootstrap fallback.

Entry points
------------

- :func:`train_cox_from_store` — fit ``CoxModel`` on observations.
- :func:`train_retention_from_store` — fit ``RetentionModel`` on observation
  pairs (previous → next).

Both functions return a training report for auditability and keep the
fitted artefacts on disk as NumPy ``.npz`` files with adjacent JSON
metadata for runtime versioning.
"""

from .cox import train_cox_from_store
from .retention import train_retention_from_store

__all__ = ["train_cox_from_store", "train_retention_from_store"]
