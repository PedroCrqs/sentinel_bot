"""Small runtime configuration helpers shared by the Python services."""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(PROJECT_ENV)


def database_settings(environ=None):
    """Return the canonical DATABASE_URL or the temporary legacy settings."""
    env = os.environ if environ is None else environ
    database_url = (env.get("DATABASE_URL") or "").strip()
    if database_url:
        return {"dsn": database_url}

    return {
        "dbname": env.get("POSTGRES_DB", "sentinel_db"),
        "user": env.get("POSTGRES_USER", "postgres"),
        "password": env.get("POSTGRES_PASSWORD", ""),
        "host": env.get("DB_HOST", "localhost"),
        "port": env.get("DB_PORT", "5432"),
    }


def validated_database_settings(environ=None):
    """Return settings and reject an unconfigured password fallback."""
    settings = database_settings(environ)
    env = os.environ if environ is None else environ
    if "dsn" in settings:
        return settings
    if not (env.get("POSTGRES_PASSWORD") or "").strip():
        raise ValueError(
            "Missing required configuration: DATABASE_URL "
            "(or POSTGRES_PASSWORD for legacy fallback)"
        )
    return settings


def inventory_sync_interval_seconds(environ=None):
    env = os.environ if environ is None else environ
    raw = (env.get("INVENTORY_SYNC_INTERVAL_SECONDS") or "300").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("INVENTORY_SYNC_INTERVAL_SECONDS must be a positive integer") from exc
    if value <= 0:
        raise ValueError("INVENTORY_SYNC_INTERVAL_SECONDS must be a positive integer")
    return value


def inventory_sync_enabled(environ=None):
    env = os.environ if environ is None else environ
    value = (env.get("INVENTORY_SYNC_ENABLED") or "true").strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("INVENTORY_SYNC_ENABLED must be true or false")
    return value in {"true", "1", "yes"}


def rabbitmq_url(environ=None):
    """Return RabbitMQ as an AMQP URL, rejecting the old bare-host format."""
    env = os.environ if environ is None else environ
    value = (env.get("RABBITMQ_URL") or "amqp://localhost:5672").strip()
    if not value.startswith(("amqp://", "amqps://")):
        raise ValueError("RABBITMQ_URL must use the amqp:// or amqps:// format")
    return value


def required_config(name, environ=None):
    """Return a required value without exposing it in an error message."""
    env = os.environ if environ is None else environ
    value = (env.get(name) or "").strip()
    if not value:
        raise ValueError(f"Missing required configuration: {name}")
    return value
