from .base import *  # noqa: F401,F403
from .base import BASE_DIR, MIDDLEWARE, INSTALLED_APPS

DEBUG = True

INSTALLED_APPS += ["debug_toolbar"]

MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

INTERNAL_IPS = ["127.0.0.1"]

# Remove RedirectsPanel entirely. DISABLE_PANELS only turns it off by default;
# the toolbar checkbox "Intercept redirects" can turn it back on and then every
# login/form save shows a "302 Found — click to continue" page.
DEBUG_TOOLBAR_PANELS = [
    "debug_toolbar.panels.history.HistoryPanel",
    "debug_toolbar.panels.versions.VersionsPanel",
    "debug_toolbar.panels.timer.TimerPanel",
    "debug_toolbar.panels.settings.SettingsPanel",
    "debug_toolbar.panels.headers.HeadersPanel",
    "debug_toolbar.panels.request.RequestPanel",
    "debug_toolbar.panels.sql.SQLPanel",
    "debug_toolbar.panels.staticfiles.StaticFilesPanel",
    "debug_toolbar.panels.templates.TemplatesPanel",
    "debug_toolbar.panels.alerts.AlertsPanel",
    "debug_toolbar.panels.cache.CachePanel",
    "debug_toolbar.panels.signals.SignalsPanel",
    # intentionally omitted: debug_toolbar.panels.redirects.RedirectsPanel
    "debug_toolbar.panels.profiling.ProfilingPanel",
]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Relaxed in dev only — production overrides these explicitly in prod.py.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Console-only logging in dev: TimedRotatingFileHandler's midnight rollover
# does an os.rename() that Windows refuses while a prior process still holds
# the file handle. Production (Linux, single gunicorn-managed process) keeps
# the file handler defined in base.py.
LOGGING["root"]["handlers"] = ["console"]
for _logger in LOGGING["loggers"].values():
    _logger["handlers"] = ["console"]
