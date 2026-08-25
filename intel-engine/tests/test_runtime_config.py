import unittest

from runtime_config import database_settings, rabbitmq_url, required_config


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
