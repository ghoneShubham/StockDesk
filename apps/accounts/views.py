"""Day 15 — login with simple IP rate limiting (SECURITY.md finding)."""

from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.cache import cache


class RateLimitedLoginView(LoginView):
    """
    Allow at most MAX_ATTEMPTS failed POSTs per IP per WINDOW_SECONDS.
    Successful login clears the counter. CSRF still applies as usual.
    """

    template_name = "accounts/login.html"
    MAX_ATTEMPTS = 10
    WINDOW_SECONDS = 60

    def _client_ip(self) -> str:
        xff = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR") or "unknown"

    def _cache_key(self) -> str:
        return f"login_attempts:{self._client_ip()}"

    def post(self, request, *args, **kwargs):
        key = self._cache_key()
        attempts = cache.get(key, 0)
        if attempts >= self.MAX_ATTEMPTS:
            messages.error(
                request,
                f"Too many login attempts. Try again in about {self.WINDOW_SECONDS} seconds.",
            )
            form = self.get_form_class()(data=request.POST, files=request.FILES)
            form.is_valid()  # bind errors without authenticating
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._cache_key()
        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, timeout=self.WINDOW_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._cache_key())
        return super().form_valid(form)
