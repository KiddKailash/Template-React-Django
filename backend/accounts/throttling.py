"""Named throttle scopes (rates live in settings.REST_FRAMEWORK).

From Store-Arbitrage (core/api/throttling.py). Note that
``throttle_classes = [...]`` REPLACES the defaults for a view rather than adding
to them; every scope here is stricter than the ``anon``/``user`` default it
displaces.
"""

from rest_framework.throttling import AnonRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    """Sign-in (and registration, if a project adds it), keyed by client IP.

    Anon rather than User deliberately: the caller has no identity yet, and the
    thing being limited is how many identities they can try. Token refresh is
    NOT on this budget: it is automatic, and limiting it would sign people out.
    """

    scope = "auth"
