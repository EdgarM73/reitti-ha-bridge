"""Constants for Reitti Tracker."""

DOMAIN = "reitti_tracker"

CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_DEVICE = "device"
CONF_INTERVAL = "interval_seconds"
CONF_ENABLE_PUSH = "enable_push"
CONF_IDLE_INTERVAL = "idle_interval_seconds"

DEFAULT_INTERVAL = 30
DEFAULT_IDLE_INTERVAL = 300
INGEST_PATH = "/api/v1/ingest/owntracks"
SERVICE_PUSH_NOW = "push_now"
