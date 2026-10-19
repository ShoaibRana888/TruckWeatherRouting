class UpstreamError(Exception):
    """A third-party API (Mapbox, Open-Meteo) failed; the message is safe to show users."""


class NotFoundError(Exception):
    """The request was valid but nothing matched (e.g. no drivable route)."""
