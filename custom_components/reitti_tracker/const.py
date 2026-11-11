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

# A tracker whose last report showed movement is not "standing still" when it
# stays silent: its unchanged position is stale, so it is not repeated with the
# current time. After MOVING_STALE_LIMIT seconds of silence the repeat resumes.
MOVING_SPEED = 1.0  # m/s (about 3.6 km/h)
MOVING_STALE_LIMIT = 900  # seconds

# Delivery / buffering
MAX_BUFFER = 10000  # points kept while Reitti is unavailable
FLUSH_BATCH = 200  # points delivered in one go
RETRY_MIN = 30  # seconds until the first retry, doubled per failure
RETRY_MAX = 600
REMIND_AFTER = 1800  # repeat the warning this often during an outage

STATUS_OK = "ok"
STATUS_UNREACHABLE = "unreachable"
STATUS_REJECTED = "rejected"
STATUS_AUTH_FAILED = "auth_failed"
