"""Day 13 — production settings must never run with DEBUG=True."""

from django.conf import settings
from django.test import SimpleTestCase, override_settings


class ProdSettingsGuardsTests(SimpleTestCase):
    def test_prod_module_forces_debug_false(self):
        # Importing prod requires env vars; assert the module source contract via settings path.
        from pathlib import Path

        text = (Path(settings.BASE_DIR) / "config" / "settings" / "prod.py").read_text(encoding="utf-8")
        assert "DEBUG = False" in text
        assert "ManifestStaticFilesStorage" in text
