from app.services.default_categories import DEFAULT_CATEGORIES


class TestDefaultCategories:
    def test_default_categories_names_are_unique(self):
        category_names = [name for name, _ in DEFAULT_CATEGORIES]

        assert category_names
        assert len(category_names) == len(set(category_names))
