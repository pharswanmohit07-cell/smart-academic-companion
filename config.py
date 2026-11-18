"""
Environment-based configuration.

Every secret and every environment-specific value is read from the process
environment so nothing sensitive lives in the repository. Local development
loads an optional ``.env`` file (git-ignored); Render supplies the same names
through its dashboard.

Environment variables (see also ``.env.example``):

    SECRET_KEY / FLASK_SECRET_KEY   Flask session signing key (required in production)
    DATABASE_URL                    Supabase PostgreSQL connection string (SSL required)
    SUPABASE_URL                    https://<project-ref>.supabase.co
    SUPABASE_PUBLISHABLE_KEY        Anon/publishable key (safe for browsers)
    SUPABASE_SECRET_KEY             Service-role key - server side only, never sent to a page
    APP_BASE_URL                    Public URL, used for email confirmation links
    FLASK_ENV                       "development" (default) or "production"
    FLASK_DEBUG                     "1" enables the debugger (never in production)
    COOKIE_SECURE                   Force Secure cookies; defaults to on in production
    COOKIE_DOMAIN                   Optional cookie domain (usually unset)
    DATABASE_FILE                   SQLite file used when DATABASE_URL is unset
    ALLOWED_EMAIL_DOMAINS           Optional comma-separated signup domain allow list
    LOG_LEVEL                       Logging level (default INFO)
    SESSION_LIFETIME_MINUTES        Server-side cookie lifetime (default 480)
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
_ENV_LOADED = False


def load_dotenv(path=None):
    """Load ``.env`` into ``os.environ`` without overriding real variables."""
    global _ENV_LOADED
    if _ENV_LOADED and path is None:
        return
    env_path = Path(path) if path else BASE_DIR / ".env"
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)
    _ENV_LOADED = True


def _first(*names, default=""):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return default


def _as_bool(value, default=False):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Read-only view of the environment.

    Values are read on every access so a test can set an environment variable
    (or patch an attribute) without reloading the module.
    """

    def __init__(self):
        load_dotenv()

    @property
    def APP_ENV(self):
        return (_first("FLASK_ENV", "APP_ENV", default="development")).lower()

    @property
    def IS_PRODUCTION(self):
        return self.APP_ENV in {"production", "prod"}

    @property
    def DEBUG(self):
        return _as_bool(os.environ.get("FLASK_DEBUG"), default=not self.IS_PRODUCTION)

    @property
    def DATABASE_URL(self):
        return _first("DATABASE_URL")

    @property
    def DATABASE_FILE(self):
        return _first("DATABASE_FILE")

    @property
    def SUPABASE_URL(self):
        return _first("SUPABASE_URL").rstrip("/")

    @property
    def SUPABASE_PUBLISHABLE_KEY(self):
        return _first("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY")

    @property
    def SUPABASE_SECRET_KEY(self):
        return _first("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")

    @property
    def SECRET_KEY(self):
        return _first("SECRET_KEY", "FLASK_SECRET_KEY")

    @property
    def APP_BASE_URL(self):
        return _first("APP_BASE_URL", "RENDER_EXTERNAL_URL").rstrip("/")

    @property
    def COOKIE_SECURE(self):
        return _as_bool(os.environ.get("COOKIE_SECURE"), default=self.IS_PRODUCTION)

    @property
    def COOKIE_DOMAIN(self):
        return _first("COOKIE_DOMAIN") or None

    @property
    def SESSION_LIFETIME_MINUTES(self):
        try:
            return int(_first("SESSION_LIFETIME_MINUTES", default="480"))
        except ValueError:
            return 480

    @property
    def SESSION_COOKIE_NAME(self):
        return os.environ.get("SESSION_COOKIE_NAME", "sac_session")

    @property
    def ALLOWED_EMAIL_DOMAINS(self):
        raw = _first("ALLOWED_EMAIL_DOMAINS")
        return [item.strip().lower().lstrip("@") for item in raw.split(",") if item.strip()]

    @property
    def LOG_LEVEL(self):
        return _first("LOG_LEVEL", default="INFO").upper()

    @property
    def SUPABASE_AUTH_ENABLED(self):
        return bool(self.SUPABASE_URL and self.SUPABASE_PUBLISHABLE_KEY)

    def missing_for_production(self):
        """Return the names of variables production cannot run without."""
        missing = []
        if not self.SECRET_KEY:
            missing.append("SECRET_KEY / FLASK_SECRET_KEY")
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not self.SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not self.SUPABASE_PUBLISHABLE_KEY:
            missing.append("SUPABASE_PUBLISHABLE_KEY")
        return missing


settings = Settings()
