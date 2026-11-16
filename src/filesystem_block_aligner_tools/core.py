"""Core routines for aligning file sizes to filesystem block boundaries.

Why this exists
---------------
Filesystems read and write in fixed-size blocks. A file whose length is not a
multiple of the block size forces the final partial block to be read, modified,
and written back on many workloads. Padding the file to the next block boundary
turns that read-modify-write cycle into a plain write.

The trade-off is explicit: we make files larger. The caller decides the block
size, so the cost is predictable and can be bounded. We never read the file's
contents to decide the padding, and we never touch the filesystem ourselves --
the caller passes bytes and gets bytes back. That keeps the library testable
without a real disk and usable with in-memory buffers, network streams, or any
storage backend.

Edge cases handled
------------------
* ``block_size`` must be a positive integer. Zero and negative values raise
  :class:`AlignmentError` rather than silently producing nonsense.
* ``align_size(0, block_size)`` returns ``0``. An empty file is already aligned;
  padding it would create a file where none existed.
* A size that is already a multiple of ``block_size`` is returned unchanged.
* ``BlockAligner.pad`` accepts any bytes-like object and returns ``bytes``.
* ``BlockAligner.trim`` refuses to shrink below the requested size and raises
  :class:`AlignmentError` if asked to do so.
"""

from __future__ import annotations

__all__ = ["AlignmentError", "BlockAligner", "align_size"]


class AlignmentError(ValueError):
    """Raised when a block size or alignment request is invalid.

    Subclasses :class:`ValueError` so callers that already catch ``ValueError``
    around numeric parsing keep working.
    """


# Block sizes are bounded above by 2**31 - 1 so that ``size + block_size - 1``
# cannot overflow a signed 64-bit integer for any realistic file size. 2 GiB is
# far larger than any real filesystem block; the bound exists to reject typos.
_MAX_BLOCK_SIZE = 2**31 - 1


def _validate_block_size(block_size: int) -> int:
    """Return ``block_size`` after checking it is a usable positive integer."""
    if isinstance(block_size, bool) or not isinstance(block_size, int):
        raise AlignmentError(
            f"block_size must be an int, got {type(block_size).__name__}"
        )
    if block_size <= 0:
        raise AlignmentError(f"block_size must be positive, got {block_size}")
    if block_size > _MAX_BLOCK_SIZE:
        raise AlignmentError(
            f"block_size must be at most {_MAX_BLOCK_SIZE}, got {block_size}"
        )
    return block_size


def _validate_size(size: int) -> int:
    """Return ``size`` after checking it is a non-negative integer."""
    if isinstance(size, bool) or not isinstance(size, int):
        raise AlignmentError(f"size must be an int, got {type(size).__name__}")
    if size < 0:
        raise AlignmentError(f"size must be non-negative, got {size}")
    return size


def align_size(size: int, block_size: int) -> int:
    """Round ``size`` up to the next multiple of ``block_size``.

    Parameters
    ----------
    size:
        Current length in bytes. Must be non-negative.
    block_size:
        Filesystem block size in bytes. Must be a positive integer.

    Returns
    -------
    int
        The smallest multiple of ``block_size`` that is greater than or equal
        to ``size``. ``align_size(0, block_size)`` is ``0``.

    Raises
    ------
    AlignmentError
        If ``size`` is negative or ``block_size`` is not positive.
    """
    size = _validate_size(size)
    block_size = _validate_block_size(block_size)
    if size == 0:
        return 0
    # Integer arithmetic avoids floating-point rounding on large sizes.
    remainder = size % block_size
    if remainder == 0:
        return size
    return size + (block_size - remainder)


class BlockAligner:
    """Pad or trim byte strings so their lengths sit on block boundaries.

    The aligner is stateless apart from its configured ``block_size``, so a
    single instance can be reused across files. Padding uses a caller-supplied
    fill byte (default ``b"\x00"``) because some formats care what the slack
    space contains.

    Parameters
    ----------
    block_size:
        Filesystem block size in bytes. Must be a positive integer.
    fill:
        A single byte used to pad. Must be exactly one byte long.

    Raises
    ------
    AlignmentError
        If ``block_size`` is not positive or ``fill`` is not a single byte.
    """

    __slots__ = ("_block_size", "_fill")

    def __init__(self, block_size: int, fill: bytes = b"\x00") -> None:
        self._block_size = _validate_block_size(block_size)
        if not isinstance(fill, (bytes, bytearray)):
            raise AlignmentError(
                f"fill must be bytes, got {type(fill).__name__}"
            )
        if len(fill) != 1:
            raise AlignmentError(
                f"fill must be exactly one byte, got {len(fill)}"
            )
        self._fill = bytes(fill)

    @property
    def block_size(self) -> int:
        """The configured block size in bytes."""
        return self._block_size

    @property
    def fill(self) -> bytes:
        """The single padding byte."""
        return self._fill

    def aligned_size(self, size: int) -> int:
        """Return the block-aligned size for ``size``.

        Equivalent to :func:`align_size` with this instance's block size.
        """
        return align_size(size, self._block_size)

    def padding_needed(self, size: int) -> int:
        """Return how many fill bytes would be appended to ``size`` bytes.

        A size that is already aligned yields ``0``.
        """
        return self.aligned_size(size) - _validate_size(size)

    def pad(self, data: bytes) -> bytes:
        """Return ``data`` extended with fill bytes to the next block boundary.

        ``data`` may be any bytes-like object; the return value is always a
        ``bytes`` object, which is what file-writing APIs expect.

        Raises
        ------
        AlignmentError
            If ``data`` is not bytes-like.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise AlignmentError(
                f"data must be bytes-like, got {type(data).__name__}"
            )
        raw = bytes(data)
        target = self.aligned_size(len(raw))
        if target == len(raw):
            # Return the original bytes unchanged; avoids a copy on the common
            # already-aligned path.
            return raw
        return raw + self._fill * (target - len(raw))

    def trim(self, data: bytes, size: int) -> bytes:
        """Return the first ``size`` bytes of ``data``.

        This is the inverse of padding: after reading a block-aligned file you
        often want the logical payload back. ``size`` must not exceed
        ``len(data)``; shrinking below the requested size is not something the
        aligner can do, so it raises rather than returning short data.

        Raises
        ------
        AlignmentError
            If ``data`` is not bytes-like or ``size`` exceeds its length.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise AlignmentError(
                f"data must be bytes-like, got {type(data).__name__}"
            )
        size = _validate_size(size)
        raw = bytes(data)
        if size > len(raw):
            raise AlignmentError(
                f"cannot trim {len(raw)} bytes to {size} bytes"
            )
        return raw[:size]

    def __repr__(self) -> str:  # pragma: no cover - trivial formatting
        return f"BlockAligner(block_size={self._block_size}, fill={self._fill!r})"
