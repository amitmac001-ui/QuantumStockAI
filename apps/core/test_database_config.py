from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.database import build_database_config


class DatabaseConfigTests(SimpleTestCase):
    def test_sqlite_is_the_local_fallback(self):
        base_dir = Path("C:/safe/project")
        config = build_database_config(base_dir, {})
        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(config["NAME"], base_dir / "db.sqlite3")

    def test_postgresql_url_is_parsed_without_extra_dependency(self):
        config = build_database_config(
            Path("."),
            {"DATABASE_URL": "postgresql://user:p%40ss@db.example/test?sslmode=require&channel_binding=require"},
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["PASSWORD"], "p@ss")
        self.assertEqual(config["HOST"], "db.example")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")
        self.assertEqual(config["CONN_MAX_AGE"], 0)

    def test_non_postgresql_database_url_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            build_database_config(Path("."), {"DATABASE_URL": "mysql://user:pass@db/name"})
