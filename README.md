# filesystem_block_aligner_tools

Pad (or trim) byte strings so their lengths land on filesystem block boundaries.

```python
from filesystem_block_aligner_tools import BlockAligner, align_size

# One-off size math.
assert align_size(4097, 4096) == 8192
assert align_size(0, 4096) == 0

# Reusable aligner for a 4 KiB block filesystem.
aligner = BlockAligner(4096)
padded = aligner.pad(b"hello")
assert len(padded) == 4096
assert aligner.trim(padded, 5) == b"hello"

# A different fill byte, for formats that care about slack space.
marker = BlockAligner(512, fill=b"\xff")
assert marker.pad(b"x") == b"x" + b"\xff" * 511
```

## Why this exists

Filesystems read and write in fixed-size blocks. A file whose length is not a
multiple of that block size forces the final partial block to be read, modified,
and written back on many workloads. Padding the file to the next block boundary
turns that read-modify-write cycle into a plain write.

The trade-off is that files get bigger. This library makes the cost explicit:
the caller chooses the block size, and `padding_needed` reports exactly how many
bytes will be added before anything is written. The library never touches the
filesystem itself, so the same code works with real files, in-memory buffers, or
network streams, and the tests run without a disk.

## The awkward edge

An empty input stays empty. `align_size(0, block_size)` returns `0` and
`BlockAligner.pad(b"")` returns `b""`, not a full block of fill bytes. An empty
file is already aligned; padding it would create a file where none existed, and
that is almost never what the caller wants. If you do want a full block of
padding, pass at least one byte of real data.

## API

- `align_size(size, block_size) -> int` — smallest multiple of `block_size` that
  is `>= size`. `size` must be non-negative, `block_size` must be a positive
  integer.
- `BlockAligner(block_size, fill=b"\x00")` — reusable aligner. `fill` must be
  exactly one byte.
  - `.block_size` / `.fill` — read-only properties.
  - `.aligned_size(size) -> int` — same as `align_size` with the configured
    block size.
  - `.padding_needed(size) -> int` — bytes that would be appended.
  - `.pad(data) -> bytes` — extend `data` (any bytes-like object) to the next
    block boundary. Returns `bytes`.
  - `.trim(data, size) -> bytes` — return the first `size` bytes of `data`.
    Raises `AlignmentError` if `size` exceeds `len(data)`.
- `AlignmentError` — subclass of `ValueError`. Raised for non-positive block
  sizes, negative sizes, non-integer sizes, multi-byte fills, and trims that
  would need to shrink the data.
