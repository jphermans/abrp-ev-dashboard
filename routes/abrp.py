"""ABRP API routes — REMOVED.

The ABRP free-tier API token can only SEND telemetry data (via /tlm/send),
not FETCH activities. All data fetching code has been removed.

For live vehicle data forwarding to ABRP, use the VW connector's
'ABRP Live Data token' field in Settings → Vehicle Connections.
"""

from auth import login_required


def register(app):
    # All endpoints removed — ABRP token is send-only, not fetch.
    # The /api/abrp/login endpoint has been deprecated.
    pass
