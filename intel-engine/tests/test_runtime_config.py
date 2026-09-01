import unittest

from runtime_config import (
    database_settings,
    inventory_sync_enabled,
    inventory_sync_interval_seconds,
    rabbitmq_url,
    required_config,
    validated_database_settings,
)


class RuntimeConfigurationTests(unittest.TestCase):
    def test_database_url_has_priority_over_legacy_settings(self):
        settings = database_settings(
            {
                "DATABASE_URL": "postgresql://user:pass@db:5432/sentinel_db",
                "POSTGRES_DB": "legacy_db",
                "POSTGRES_USER": "legacy_user",
            }
        )

        self.assertEqual(
            settings,
            {"dsn": "postgresql://user:pass@db:5432/sentinel_db"},
        )

    def test_legacy_database_settings_are_temporary_fallback(self):
        settings = database_settings({})

        self.assertEqual(settings["dbname"], "sentinel_db")
        self.assertEqual(settings["user"], "postgres")
        self.assertEqual(settings["host"], "localhost")
        self.assertEqual(settings["port"], "5432")

    def test_database_without_credentials_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            validated_database_settings({})

    def test_inventory_sync_runtime_defaults_and_validation(self):
        self.assertTrue(inventory_sync_enabled({}))
        self.assertEqual(inventory_sync_interval_seconds({}), 300)
        self.assertFalse(inventory_sync_enabled({"INVENTORY_SYNC_ENABLED": "false"}))
        self.assertEqual(
            inventory_sync_interval_seconds({"INVENTORY_SYNC_INTERVAL_SECONDS": "30"}),
            30,
        )
        with self.assertRaisesRegex(ValueError, "positive integer"):
            inventory_sync_interval_seconds({"INVENTORY_SYNC_INTERVAL_SECONDS": "0"})

    def test_rabbitmq_requires_amqp_url(self):
        self.assertEqual(rabbitmq_url({}), "amqp://localhost:5672")
        self.assertEqual(
            rabbitmq_url({"RABBITMQ_URL": "amqp://rabbit:5672"}),
            "amqp://rabbit:5672",
        )
        with self.assertRaisesRegex(ValueError, "RABBITMQ_URL"):
            rabbitmq_url({"RABBITMQ_URL": "rabbit"})

    def test_required_configuration_has_safe_error(self):
        with self.assertRaisesRegex(
            ValueError, "Missing required configuration: NEO4J_URI"
        ):
            required_config("NEO4J_URI", {})


if __name__ == "__main__":
    unittest.main()
