"""A minimal CSV row parser.

Deliberately small so a whole task bundle stays inspectable. The bug below is the kind that
survives review: the naive implementation is correct for the common case and only fails when a
quoted field contains the delimiter.
"""

from __future__ import annotations

import csv

__all__ = ["parse_row"]


def parse_row(row: str) -> list[str]:
    """Split one CSV row into fields.

    Quoted fields may contain the delimiter, and quotes are stripped from the result.
    """
    return next(csv.reader([row]))
