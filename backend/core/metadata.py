"""What an ``OPTIONS`` request may learn about an endpoint.

From Store-Arbitrage (core/api/metadata.py). DRF's ``SimpleMetadata`` answers
with the view's docstring as ``description``. Docstrings are written for
maintainers, and ``OPTIONS`` needs no credential on a public view, so
publishing them hands internal notes to anyone who asks.
"""

from rest_framework.metadata import SimpleMetadata


class PublicMetadata(SimpleMetadata):
    """``SimpleMetadata`` without the view's docstring."""

    def determine_metadata(self, request, view):
        metadata = super().determine_metadata(request, view)
        metadata.pop("description", None)
        return metadata
