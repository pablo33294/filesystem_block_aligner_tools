"""Filesystem block alignment helpers.

Public surface:

* :class:`BlockAligner` -- pad or trim byte streams to block boundaries.
* :func:`align_size` -- compute the smallest aligned size >= a given size.
* :class:`AlignmentError` -- raised for invalid configuration or input.
"""

from .core import AlignmentError, BlockAligner, align_size

__all__ = ["AlignmentError", "BlockAligner", "align_size"]
