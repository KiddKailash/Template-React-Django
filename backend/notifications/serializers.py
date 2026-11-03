from rest_framework import serializers


class PushSubscriptionSerializer(serializers.Serializer):
    """Matches the browser's PushSubscription.toJSON() shape."""

    endpoint = serializers.URLField(max_length=1024)
    keys = serializers.DictField(child=serializers.CharField())

    def validate_keys(self, value):
        missing = {"p256dh", "auth"} - set(value)
        if missing:
            raise serializers.ValidationError(f"Missing keys: {sorted(missing)}")
        return value
