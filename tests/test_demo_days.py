"""Multi-day demos create fresh availability without replacing saved data."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from servicesetu.core import Store, Rejected
from servicesetu.__main__ import main
from tests.test_proofs import Clock


class DemoDays(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"demo.db"

    def test_three_days_have_two_slots_per_day(self):
        store=Store(self.path,Clock())
        store.seed(days=3)
        providers=store.providers()
        self.assertEqual(len(providers),6)
        self.assertTrue(all(len(p["slots"])==6 for p in providers))
        self.assertEqual(len({s[:10] for s in providers[0]["slots"]}),3)

    def test_reseeding_does_not_replace_existing_provider_data(self):
        store=Store(self.path,Clock()); store.seed()
        before=store.providers()
        quote=store.quote("customer","p1",before[0]["slots"][0])
        booking=store.hold("customer",quote["id"])
        store.seed(days=3)
        self.assertEqual(store.providers(),before)
        self.assertEqual(store.booking(booking["id"],"customer")["state"],"held")

    def test_invalid_day_counts_are_rejected(self):
        store=Store(self.path,Clock())
        for days in (0,15,True,1.5):
            with self.subTest(days=days),self.assertRaises(Rejected): store.seed(days=days)
        self.assertEqual(store.providers(),[])

    def test_cli_refuses_to_overwrite_existing_database(self):
        self.path.write_bytes(b"existing data")
        with patch("sys.argv",["servicesetu","seed-demo","--db",str(self.path)]),self.assertRaises(SystemExit): main()
        self.assertEqual(self.path.read_bytes(),b"existing data")

    def test_cli_creates_new_database(self):
        with patch("sys.argv",["servicesetu","seed-demo","--db",str(self.path),"--days","3"]): main()
        self.assertEqual(len(Store(self.path).provider("p1")["slots"]),6)
