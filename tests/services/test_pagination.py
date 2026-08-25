"""Tests for the generic pagination utility — domain-agnostic, so these
tests use plain lists rather than any model (moved out of
tests/services/test_collection.py, see issue #58).
"""

from ley_shards_bot.services.pagination import paginate


class TestPaginate:
    def test_first_page_of_a_short_list(self):
        page = paginate([1, 2, 3], page_number=0, page_size=10)

        assert page.items == [1, 2, 3]
        assert page.total_pages == 1
        assert page.has_previous is False
        assert page.has_next is False

    def test_splits_across_pages(self):
        items = list(range(25))

        first = paginate(items, page_number=0, page_size=10)
        second = paginate(items, page_number=1, page_size=10)
        third = paginate(items, page_number=2, page_size=10)

        assert first.items == list(range(10))
        assert second.items == list(range(10, 20))
        assert third.items == list(range(20, 25))
        assert first.total_pages == 3
        assert first.has_next is True
        assert first.has_previous is False
        assert third.has_next is False
        assert third.has_previous is True

    def test_out_of_range_page_number_clamps_into_range(self):
        items = list(range(5))

        too_high = paginate(items, page_number=99, page_size=10)
        too_low = paginate(items, page_number=-5, page_size=10)

        assert too_high.page_number == 0
        assert too_low.page_number == 0

    def test_empty_list_is_a_single_empty_page(self):
        page = paginate([], page_number=0, page_size=10)

        assert page.items == []
        assert page.total_pages == 1
        assert page.has_previous is False
        assert page.has_next is False
