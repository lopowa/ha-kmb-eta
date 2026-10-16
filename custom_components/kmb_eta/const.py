"""Constants for the KMB ETA integration."""

DOMAIN = "kmb_eta"

API_STOPS = "https://data.etabus.gov.hk/v1/transport/kmb/stop"
API_STOP_ETA = "https://data.etabus.gov.hk/v1/transport/kmb/stop-eta/{stop_id}"

CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_ROUTES = "routes"

SCAN_INTERVAL_SECONDS = 60

ATTR_DEST = "destination"
ATTR_REMARK = "remark"
ATTR_ETA_1 = "eta_1"
ATTR_ETA_2 = "eta_2"
ATTR_ETA_3 = "eta_3"
ATTR_MINS_2 = "mins_2"
ATTR_MINS_3 = "mins_3"
ATTR_DIR = "direction"
