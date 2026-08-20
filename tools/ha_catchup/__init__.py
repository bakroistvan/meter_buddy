"""Sparse upload-session payload generator for HA catch-up sims."""

from .generate import chunk_upload_batches, generate_sparse_readings

__all__ = ["chunk_upload_batches", "generate_sparse_readings"]
