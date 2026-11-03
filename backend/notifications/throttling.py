from rest_framework.throttling import UserRateThrottle


class PushTestRateThrottle(UserRateThrottle):
    """ "Send a test notification": a person checks a device or two, not hundreds."""

    scope = "push_test"
