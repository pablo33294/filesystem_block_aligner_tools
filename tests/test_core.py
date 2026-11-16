import unittest

from filesystem_block_aligner_tools import (
    AlignmentError,
    BlockAligner,
    align_size,
)


class AlignSizeTests(unittest.TestCase):
    def test_already_aligned_returns_same_value(self):
        self.assertEqual(align_size(4096, 4096), 4096)
        self.assertEqual(align_size(8192, 4096), 8192)

    def test_rounds_up_to_next_block(self):
        self.assertEqual(align_size(1, 4096), 4096)
        self.assertEqual(align_size(4097, 4096), 8192)
        self.assertEqual(align_size(4095, 4096), 4096)

    def test_zero_size_stays_zero(self):
        # An empty file is already aligned; padding it would create a file.
        self.assertEqual(align_size(0, 4096), 0)
        self.assertEqual(align_size(0, 1), 0)

    def test_block_size_one_is_identity(self):
        for size in (0, 1, 2, 100):
            self.assertEqual(align_size(size, 1), size)

    def test_rejects_non_positive_block_size(self):
        with self.assertRaises(AlignmentError):
            align_size(10, 0)
        with self.assertRaises(AlignmentError):
            align_size(10, -1)

    def test_rejects_negative_size(self):
        with self.assertRaises(AlignmentError):
            align_size(-1, 4096)

    def test_rejects_non_integer_inputs(self):
        with self.assertRaises(AlignmentError):
            align_size(1.0, 4096)
        with self.assertRaises(AlignmentError):
            align_size(1, "4096")
        with self.assertRaises(AlignmentError):
            align_size(True, 4096)
        with self.assertRaises(AlignmentError):
            align_size(1, True)


class BlockAlignerConstructionTests(unittest.TestCase):
    def test_default_fill_is_nul(self):
        aligner = BlockAligner(512)
        self.assertEqual(aligner.block_size, 512)
        self.assertEqual(aligner.fill, b"\x00")

    def test_custom_fill(self):
        aligner = BlockAligner(512, fill=b"\xff")
        self.assertEqual(aligner.fill, b"\xff")

    def test_rejects_bad_block_size(self):
        with self.assertRaises(AlignmentError):
            BlockAligner(0)
        with self.assertRaises(AlignmentError):
            BlockAligner(-8)

    def test_rejects_multi_byte_fill(self):
        with self.assertRaises(AlignmentError):
            BlockAligner(512, fill=b"ab")

    def test_rejects_empty_fill(self):
        with self.assertRaises(AlignmentError):
            BlockAligner(512, fill=b"")

    def test_rejects_non_bytes_fill(self):
        with self.assertRaises(AlignmentError):
            BlockAligner(512, fill="x")


class BlockAlignerBehaviourTests(unittest.TestCase):
    def test_aligned_size_matches_free_function(self):
        aligner = BlockAligner(4096)
        for size in (0, 1, 4095, 4096, 4097, 1_000_000):
            self.assertEqual(aligner.aligned_size(size), align_size(size, 4096))

    def test_padding_needed(self):
        aligner = BlockAligner(16)
        self.assertEqual(aligner.padding_needed(0), 0)
        self.assertEqual(aligner.padding_needed(16), 0)
        self.assertEqual(aligner.padding_needed(15), 1)
        self.assertEqual(aligner.padding_needed(1), 15)

    def test_pad_extends_to_boundary_with_default_fill(self):
        aligner = BlockAligner(8)
        self.assertEqual(aligner.pad(b"abc"), b"abc" + b"\x00" * 5)

    def test_pad_leaves_aligned_data_untouched(self):
        aligner = BlockAligner(8)
        payload = b"abcdefgh"
        self.assertEqual(aligner.pad(payload), payload)

    def test_pad_empty_input_stays_empty(self):
        aligner = BlockAligner(8)
        self.assertEqual(aligner.pad(b""), b"")

    def test_pad_uses_custom_fill_byte(self):
        aligner = BlockAligner(4, fill=b"#")
        self.assertEqual(aligner.pad(b"ab"), b"ab##")

    def test_pad_accepts_bytearray_and_memoryview(self):
        aligner = BlockAligner(4)
        self.assertEqual(aligner.pad(bytearray(b"ab")), b"ab\x00\x00")
        self.assertEqual(aligner.pad(memoryview(b"ab")), b"ab\x00\x00")

    def test_pad_returns_bytes_type(self):
        aligner = BlockAligner(4)
        result = aligner.pad(bytearray(b"ab"))
        self.assertIsInstance(result, bytes)

    def test_pad_rejects_non_bytes(self):
        aligner = BlockAligner(4)
        with self.assertRaises(AlignmentError):
            aligner.pad("ab")

    def test_trim_returns_prefix(self):
        aligner = BlockAligner(8)
        padded = aligner.pad(b"abc")
        self.assertEqual(aligner.trim(padded, 3), b"abc")

    def test_trim_to_zero(self):
        aligner = BlockAligner(8)
        self.assertEqual(aligner.trim(b"abcdefgh", 0), b"")

    def test_trim_accepts_bytearray(self):
        aligner = BlockAligner(8)
        self.assertEqual(aligner.trim(bytearray(b"abcdefgh"), 4), b"abcd")

    def test_trim_rejects_size_beyond_data(self):
        aligner = BlockAligner(8)
        with self.assertRaises(AlignmentError):
            aligner.trim(b"abc", 4)

    def test_trim_rejects_negative_size(self):
        aligner = BlockAligner(8)
        with self.assertRaises(AlignmentError):
            aligner.trim(b"abc", -1)

    def test_trim_rejects_non_bytes(self):
        aligner = BlockAligner(8)
        with self.assertRaises(AlignmentError):
            aligner.trim("abc", 1)

    def test_pad_then_trim_round_trip(self):
        aligner = BlockAligner(64, fill=b"\x7f")
        original = bytes(range(50))
        padded = aligner.pad(original)
        self.assertEqual(len(padded), 64)
        self.assertEqual(aligner.trim(padded, len(original)), original)

    def test_large_unaligned_size(self):
        aligner = BlockAligner(4096)
        size = 4096 * 1000 + 1
        self.assertEqual(aligner.aligned_size(size), 4096 * 1001)
        self.assertEqual(aligner.padding_needed(size), 4095)


if __name__ == "__main__":
    unittest.main()
