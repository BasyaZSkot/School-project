import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.parcers import monitoring


class MonitoringStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.path_patcher = patch.object(monitoring, "DB_PATH", self.db_path)
        self.path_patcher.start()
        monitoring.init_db()

    def tearDown(self):
        self.path_patcher.stop()
        self.temp_dir.cleanup()

    def create(self):
        return monitoring.create_monitor(
            query="wireless headphones",
            product_url="https://shop.example/product/1",
            marketplace="Ozon",
            title="Wireless headphones",
            interval_seconds=900,
        )

    def test_create_list_pause_resume_and_delete(self):
        monitor = self.create()
        self.assertTrue(monitor["active"])
        self.assertEqual(len(monitoring.list_monitors()), 1)

        paused = monitoring.update_monitor(monitor["id"], active=False)
        self.assertFalse(paused["active"])
        resumed = monitoring.update_monitor(monitor["id"], active=True)
        self.assertTrue(resumed["active"])

        self.assertTrue(monitoring.delete_monitor(monitor["id"]))
        self.assertEqual(monitoring.list_monitors(), [])

    def test_history_and_price_alert(self):
        monitor = self.create()
        monitoring.record_check(monitor["id"], price=100.0, currency="RUB", status="ok")
        monitoring.record_check(monitor["id"], price=85.0, currency="RUB", status="ok")

        history = monitoring.price_history(monitor["id"])
        self.assertEqual([point["price"] for point in history], [100.0, 85.0])
        alerts = monitoring.list_alerts(monitor["id"])
        self.assertEqual(len(alerts), 1)
        self.assertAlmostEqual(alerts[0]["change_percent"], -15.0)

    def test_currency_change_does_not_create_false_alert(self):
        monitor = self.create()
        monitoring.record_check(monitor["id"], price=100.0, currency="USD", status="ok")
        monitoring.record_check(monitor["id"], price=90.0, currency="RUB", status="ok")
        self.assertEqual(monitoring.list_alerts(monitor["id"]), [])

    def test_missing_offer_does_not_invent_snapshot(self):
        monitor = self.create()
        monitoring.record_check(
            monitor["id"], price=None, currency=None, status="offer_not_returned"
        )
        self.assertEqual(monitoring.price_history(monitor["id"]), [])
        updated = monitoring.get_monitor(monitor["id"])
        self.assertEqual(updated["last_status"], "offer_not_returned")


if __name__ == "__main__":
    unittest.main()
