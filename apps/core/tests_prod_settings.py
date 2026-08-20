"""Day 13/14 — production settings guards."""

from django.conf import settings
from django.test import SimpleTestCase


class ProdSettingsGuardsTests(SimpleTestCase):
    def test_prod_module_forces_debug_false(self):
        from pathlib import Path

        text = (Path(settings.BASE_DIR) / "config" / "settings" / "prod.py").read_text(encoding="utf-8")
        assert "DEBUG = False" in text
        assert "ManifestStaticFilesStorage" in text
        assert "S3Storage" in text
        assert "BACKUP_RETENTION_DAYS" in text

    def test_staging_module_exists_and_forces_debug_false(self):
        from pathlib import Path

        text = (Path(settings.BASE_DIR) / "config" / "settings" / "staging.py").read_text(
            encoding="utf-8"
        )
        assert "DEBUG = False" in text
        assert "media_staging" in text
