"""Routine output stays local while published evidence remains available."""
import json
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from servicesetu.evidence import evidence_path, evidence_input


class EvidencePaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import SDK logging before entering temporary working directories.
        if importlib.util.find_spec("uagents"):
            from servicesetu import register
            cls.register = register

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        previous = Path.cwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, previous)
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("SERVICESETU_ARTIFACT_DIR", None)
        Path("artifacts").mkdir()

    def test_default_output_does_not_overwrite_published_report(self):
        published = Path("artifacts/proof-results.json")
        published.write_text("published")
        path = evidence_path("proof-results.json")
        path.write_text("new local run")
        self.assertEqual(path, Path("artifacts/local/proof-results.json"))
        self.assertEqual(published.read_text(), "published")

    def test_readers_prefer_local_and_fall_back_to_published(self):
        published = Path("artifacts/agent-addresses.json")
        published.write_text("published")
        self.assertEqual(evidence_input(published.name), published)
        local = evidence_path(published.name)
        local.write_text("local")
        self.assertEqual(evidence_input(published.name), local)

    @unittest.skipUnless(importlib.util.find_spec("uagents"), "Requires fetch extras")
    def test_routine_manifest_write_preserves_readme(self):
        write_manifest = self.register.write_manifest
        Path("README.md").write_text("Published documentation")
        write_manifest([])
        self.assertEqual(Path("README.md").read_text(), "Published documentation")
        self.assertEqual(json.loads(evidence_path("registration-manifest.json").read_text()), [])

    @unittest.skipUnless(importlib.util.find_spec("uagents"), "Requires fetch extras")
    def test_explicit_publication_updates_published_manifest_and_readme(self):
        write_manifest = self.register.write_manifest
        os.environ["SERVICESETU_ARTIFACT_DIR"] = "artifacts"
        Path("README.md").write_text("## Register and try it in ASI:One")
        write_manifest([{"name": "Example", "address": "example-address"}])
        self.assertIn("Example", Path("README.md").read_text())
        self.assertTrue(Path("artifacts/registration-manifest.json").exists())

    @unittest.skipUnless(importlib.util.find_spec("uagents"), "Requires fetch extras")
    def test_prepare_retains_published_verification_for_matching_identity(self):
        register = self.register
        prior = [{"address": "existing-address", "registration_status": "registered_active",
                  "profile_url": "https://example.com/profile", "verified_at": "previous-check"}]
        Path("artifacts/registration-manifest.json").write_text(json.dumps(prior))
        agent = SimpleNamespace(address="existing-address", name="Example", protocols={})
        with patch.object(register, "create_mesh", return_value=(None, {"concierge": agent}, None)):
            result = register.prepare()
        self.assertEqual(result[0]["address"], prior[0]["address"])
        self.assertEqual(result[0]["verified_at"], "previous-check")
        self.assertEqual(result[0]["registration_status"], "registered_active")
        self.assertEqual(json.loads(Path("artifacts/registration-manifest.json").read_text()), prior)
