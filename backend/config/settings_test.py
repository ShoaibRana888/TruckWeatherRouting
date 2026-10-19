import os

# Settings refuse to start without a secret key unless DEBUG is on.
os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ["MAPBOX_TOKEN"] = "test-token"

import tempfile  # noqa: E402

from .settings import *  # noqa: E402,F401,F403

# Keep WhiteNoise quiet: point it at an existing empty directory.
STATIC_ROOT = WHITENOISE_ROOT = tempfile.mkdtemp()
