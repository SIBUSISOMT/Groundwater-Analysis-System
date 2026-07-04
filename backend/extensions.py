"""
extensions.py — Shared Flask extension instances.

Exists so blueprint modules (auth.py, admin_bp.py, wq_bp.py) can decorate their
own routes with @limiter.limit(...) at import time, before app.py has called
limiter.init_app(app). Creating the Limiter here avoids a circular import
between app.py and the blueprints.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])
