"""AXNODE v1 parse-only adversarial and canonicalization tests."""
import copy
import json
import unittest

from eai.axnode_schema import parse_axnode


class AXNodeSchemaTests(unittest.TestCase):
    def node(self):
        return {
            "schema": "eai.axnode.v1", "id": "data.csv.key_diff", "version": 1,
            "kind": "strategy", "status": "CANDIDATE",
            "signature": {"inputs": {"a": "csv_ref", "b": "csv_ref", "key": "column"},
                          "output": "difference_receipt"},
            "pre": ["authorized_read_only_sources", "key_column_exists"],
            "post": ["source_hashes_unchanged", "independently_verified_receipt"],
            "steps": [{"skill": "csv.reconcile.v1"},
                      {"skill": "evidence.verify_receipt.v1"}],
            "capabilities": ["local.read"], "parent_hashes": [],
            "tests": {"unit": [], "heldout": [], "negative": []}, "evidence": [],
            "provenance": {"author": "EAI_DESIGN", "source": "local_verified_only"},
            "budget": {"max_steps": 5, "max_seconds": 60}
        }

    def test_canonical_hash_unchanged_by_json_order_and_spacing(self):
        raw = self.node()
        a = parse_axnode(json.dumps(raw, ensure_ascii=False))
        b = parse_axnode(json.dumps(dict(reversed(list(raw.items()))),
                                        indent=2, ensure_ascii=False))
        self.assertEqual(a.sha256, b.sha256)
        self.assertEqual(a.as_dict(), raw)
        mut = a.as_dict()
        mut["steps"].clear()
        self.assertEqual(len(a.as_dict()["steps"]), 2)
        self.assertEqual(len(a.sha256), 64)

    def test_synthetic_noop_is_a_parse_only_pure_axnode_skill(self):
        raw = self.node()
        raw["steps"] = [{"skill": "synthetic.noop.v1"}]
        raw["capabilities"] = ["pure"]
        raw["budget"] = {"max_steps": 1, "max_seconds": 15}
        parsed = parse_axnode(json.dumps(raw))
        self.assertEqual(parsed.as_dict()["steps"], raw["steps"])
        self.assertEqual(parsed.as_dict()["status"], "CANDIDATE")

    def test_dup_keys_and_untrusted_executable_skill_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_axnode('{"schema":"eai.axnode.v1","schema":"eai.axnode.v1"}')
        for skill in ["shell.run", "python.exec", "github.write", "web.fetch"]:
            bad = self.node()
            bad["steps"] = [{"skill": skill}]
            with self.subTest(skill=skill), self.assertRaises(ValueError):
                parse_axnode(json.dumps(bad))

    def test_fail_closed_on_privileged_node_or_unauthorized_activation(self):
        for patch in [
            {"status": "ACTIVE"}, {"status": "VERIFIED"},
            {"capabilities": ["github.write"]},
            {"capabilities": ["pure", "pure"]},
            {"evidence": ["f"*64]},
            {"kind": "arbitrary_python"},
            {"version": True},
        ]:
            raw = dict(self.node(), **patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parse_axnode(json.dumps(raw))

    def test_reject_hidden_extra_fields_and_oversize_payload(self):
        bad = dict(self.node(), exec="import os")
        with self.assertRaises(ValueError):
            parse_axnode(json.dumps(bad))
        with self.assertRaises(ValueError):
            parse_axnode(" " * 32769)
        with self.assertRaises(ValueError):
            parse_axnode(b"\xff\xff")

    def test_budget_parent_schema_and_identifier_checks(self):
        for patch in [
            {"budget": {"max_steps": True, "max_seconds": 1}},
            {"budget": {"max_steps": 1, "max_seconds": 60}},
            {"parent_hashes": ["badsha"]},
            {"parent_hashes": ["a"*64, "a"*64]},
            {"id": "../malicious"},
            {"signature": {"inputs": {"file": "shell_command"}, "output": "text"}},
            {"tests": {"unit": ["../escape"], "heldout": [], "negative": []}},
        ]:
            bad = dict(self.node(), **patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parse_axnode(json.dumps(bad))

    def test_mutation_changes_content_hash(self):
        base = self.node()
        first = parse_axnode(json.dumps(base))
        second = copy.deepcopy(base)
        second["pre"].append("synthetic_only")
        self.assertNotEqual(parse_axnode(json.dumps(second)).sha256, first.sha256)

    def test_no_imported_node_is_executable_or_persisted(self):
        import socket
        from unittest.mock import patch
        with patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.assertEqual(parse_axnode(json.dumps(self.node())).as_dict()["status"],
                             "CANDIDATE")


if __name__ == "__main__":
    unittest.main()
