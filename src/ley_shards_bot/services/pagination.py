"""Generic pagination — pages any sequence, nothing here is specific to
character collections. Was previously bundled inside services/collection.py
(its first consumer); Phase 1.1's /banners, /banner_info, and the admin
panel's users table all need the same thing — see issue #58.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Sequence

PAGE_SIZE = 10

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    page_number: int
    total_pages: int
    has_previous: bool
    has_next: bool


def paginate(items: Sequence[T], page_number: int, page_size: int = PAGE_SIZE) -> Page[T]:
    total_pages = max(1, math.ceil(len(items) / page_size))
    page_number = max(0, min(page_number, total_pages - 1))
    start = page_number * page_size
    end = start + page_size
    return Page(
        items=list(items[start:end]),
        page_number=page_number,
        total_pages=total_pages,
        has_previous=page_number > 0,
        has_next=page_number < total_pages - 1,
    )
