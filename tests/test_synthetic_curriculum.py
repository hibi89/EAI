"""C18 reproducible, split-clean synthetic-only research fixtures."""
from dataclasses import replace
import unittest
from typing import cast

from eai.synthetic_curriculum import generate_synthetic_curriculum
from eai.synthetic_holdout import _fixture_hash


class SyntheticCurriculumTests(unittest.TestCase):
    def test_deterministic_four_nonleaking_families(self):
        a = generate_synthetic_curriculum(5)
        self.assertEqual(a, generate_synthetic_curriculum(5))
        self.assertEqual(len(a.train), 2)
        self.assertEqual(len(a.heldout), 2)
        hashes = [_fixture_hash(f) for f in a.train + a.heldout]
        self.assertEqual(len(hashes), len(set(hashes)))
        self.assertEqual(len(a.manifest_sha256), 64)
        self.assertEqual(a.trust,
                         "SYNTHETIC_FIXTURES_NOT_REAL_WORLD_EVIDENCE")

    def test_distinct_seeds_change_canonical_manifest(self):
        a = generate_synthetic_curriculum(1)
        b = generate_synthetic_curriculum(2)
        self.assertNotEqual(a.manifest_sha256, b.manifest_sha256)
        self.assertNotEqual(a.train[0].left, b.train[0].left)

    def test_invalid_seed_types_fail_closed(self):
        for bad in (-1, 10001, True, 1.5, "123", None):
            with self.subTest(seed=bad), self.assertRaises(ValueError):
                generate_synthetic_curriculum(cast(int, bad))

    def test_train_and_heldout_distinct_even_when_numeric_values_normalized(self):
        a = generate_synthetic_curriculum(1)
        self.assertNotEqual(_fixture_hash(a.train[0]),
                            _fixture_hash(a.heldout[1]))
        self.assertEqual(a.train[0].claimed_different, ())
        self.assertEqual(a.heldout[1].claimed_different, ())

    def test_missing_key_family_has_explicit_counterexample_labels(self):
        a = generate_synthetic_curriculum(4)
        fixture = a.heldout[0]
        self.assertEqual(fixture.claimed_different, ("d", "e"))
        self.assertNotEqual(fixture.left, fixture.right)
