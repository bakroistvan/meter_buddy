"""Constants for the Meter Buddy integration."""

DOMAIN = "meter_buddy"

CONF_BASE_URL = "base_url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"
CONF_IMPORT_SCHEMA = "import_schema"
CONF_WATERMARK = "watermark"

DEFAULT_SCAN_INTERVAL_SECONDS = 600  # 10 min fallback poll
SESSION_COMPLETE_TIMEOUT_SECONDS = 60
DEFAULT_IMPORT_SCHEMA = 1

ATTR_ENERGY_KWH = "energy_kwh"
ATTR_POWER_W = "power_w"
ATTR_BATTERY_PCT = "battery_pct_est"
ATTR_LAST_TIMESTAMP = "last_timestamp"

SENSOR_POWER = "power"
SENSOR_ENERGY = "energy"
SENSOR_BATTERY = "battery"
