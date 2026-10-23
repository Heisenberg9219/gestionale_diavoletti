"""Limiti di frequenza per gli endpoint di autenticazione."""

from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Limita i tentativi di login per indirizzo IP."""

    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class RefreshRateThrottle(SimpleRateThrottle):
    """Limita i rinnovi di sessione per indirizzo IP."""

    scope = "auth_refresh"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


FAILED_LOGIN_LIMIT = 10
FAILED_LOGIN_WINDOW_SECONDS = 15 * 60


def _failed_login_key(email):
    return f"auth:failed-login:{(email or '').strip().lower()}"


def is_login_locked(email):
    """True se per questa email ci sono stati troppi tentativi falliti di recente."""
    return cache.get(_failed_login_key(email), 0) >= FAILED_LOGIN_LIMIT


def register_failed_login(email):
    key = _failed_login_key(email)
    if cache.add(key, 1, FAILED_LOGIN_WINDOW_SECONDS):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, FAILED_LOGIN_WINDOW_SECONDS)


def reset_failed_logins(email):
    cache.delete(_failed_login_key(email))
