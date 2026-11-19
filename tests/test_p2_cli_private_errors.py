"""P2-09 privacy-safe CLI negative paths, only synthetic exception inputs."""
from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import patch

from eai.__main__ import main, _public_failure_code


class P2CLIPrivateErrorsTests(unittest.TestCase):
    TOKEN = "PRIVATE_OWNER_RECORD_DO_NOT_LOG_8972"

    def failure(self, argv, target, error):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch(target, side_effect=error), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn(self.TOKEN, stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        return stderr.getvalue()

    def test_file_goals_manifest_and_pipeline_redact_validation_exception(self):
        cases = (
            (["solve-goal", self.TOKEN + ".json"],
             "eai.__main__.execute_goal_document"),
            (["pipeline-goals", self.TOKEN + ".json"],
             "eai.__main__.execute_pipeline_document"),
            (["batch-goals", self.TOKEN + ".json"],
             "eai.__main__.execute_batch_document"),
            (["make-manifest", "--mode", "batch", "--goal", "a=" + self.TOKEN + ".json"],
             "eai.__main__.build_goal_manifest"),
        )
        for argv, target in cases:
            with self.subTest(command=argv[0]):
                err = self.failure(argv, target, ValueError(self.TOKEN))
                self.assertIn("ValueError INPUT_CONTRACT_REJECTED", err)

    def test_csv_quick_and_owner_selection_redact_filesystem_exception(self):
        cases = (
            (["quick-goal", "--kind", "csv_relationships", "--source", self.TOKEN + ".csv"],
             "eai.__main__.quick_goal"),
            (["select-goal", "--manifest", self.TOKEN + ".json", "--request", "sample"],
             "eai.__main__.select_goal"),
            (["reconcile-csv", self.TOKEN + ".csv", "other.csv",
              "--key", "key", "--value", "amount"],
             "eai.__main__.reconcile_csv"),
        )
        for argv, target in cases:
            with self.subTest(command=argv[0]):
                err = self.failure(argv, target,
                                   OSError("C:/owner/private/" + self.TOKEN))
                self.assertIn("OSError LOCAL_IO_REJECTED", err)

    def test_unhandled_cli_and_timeout_redact_backend_exception(self):
        err = self.failure(["solve-goal", self.TOKEN + ".json"],
                           "eai.__main__.execute_goal_document",
                           TimeoutError("sensitive provider " + self.TOKEN))
        self.assertIn("TimeoutError LOCAL_RESOURCE_TIMEOUT", err)
        err = self.failure(["ask", "synthetic request"], "eai.__main__.Store",
                           RuntimeError("internal " + self.TOKEN))
        self.assertIn("RuntimeError LOCAL_OPERATION_REJECTED", err)


    def test_argparse_rejection_does_not_echo_positional_or_flag_value(self):
        for args in (
            ["quick-goal", "--kind", self.TOKEN],
            ["solve-goal", "synthetic.json", "--not-a-real-option", self.TOKEN],
            ["--profile", self.TOKEN, "health"],
        ):
            with self.subTest(args=args):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    with self.assertRaises(SystemExit) as raised:
                        main(args)
                self.assertEqual(raised.exception.code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertNotIn(self.TOKEN, err.getvalue())
                self.assertIn("EAI_ARGUMENT_REJECTED", err.getvalue())
                self.assertNotIn("Traceback", err.getvalue())

    def test_only_fixed_error_categories_are_public(self):
        self.assertEqual(_public_failure_code(ValueError(self.TOKEN)),
                         "INPUT_CONTRACT_REJECTED")
        self.assertEqual(_public_failure_code(PermissionError(self.TOKEN)),
                         "LOCAL_ACCESS_DENIED")
        self.assertEqual(_public_failure_code(UnicodeError(self.TOKEN)),
                         "INPUT_TEXT_ENCODING_REJECTED")


if __name__ == "__main__":
    unittest.main()
