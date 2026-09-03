import json
from pathlib import Path

from ..models.schemas import Product


class CatalogService:
    def __init__(self):
        self.products = self._load_catalog()

    def _load_catalog(self) -> list[Product]:
        if products := self._load_from_json():
            return products
        return []

    def _load_from_json(self) -> list[Product]:
        candidates = [
            Path(__file__).resolve().parent.parent / "data" / "catalog.json",
            Path(__file__).resolve().parent.parent.parent / "catalog.json",
        ]
        for path in candidates:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                return [Product(**row) for row in raw]
            except (OSError, ValueError):
                continue
        return []

    def search_products(
        self,
        query: str | None = None,
        merchant_id: str | None = None,
    ) -> list[Product]:
        results = self.products

        if merchant_id:
            results = [p for p in results if p.merchant_id == merchant_id]

        if query:
            query_lower = query.lower()
            search_terms = set(query_lower.split())

            def normalize(word: str) -> str:
                if word.endswith("ies") and len(word) > 4:
                    return word[:-3] + "y"
                if word.endswith("es") and len(word) > 3:
                    return word[:-2]
                if word.endswith("s") and len(word) > 2:
                    return word[:-1]
                return word

            def matches(product: Product) -> bool:
                name_lower = product.name.lower()
                desc_lower = product.description.lower()
                color_lower = (product.color or "").lower()
                size_lower = (product.size or "").lower()
                flavor_lower = (product.flavor or "").lower()
                storage_lower = (product.storage or "").lower()

                haystack = f"{name_lower} {desc_lower} {color_lower} {size_lower} {flavor_lower} {storage_lower}"

                if query_lower in name_lower or query_lower in haystack:
                    return True

                # singular/plural tolerant token matching
                hay_tokens = {normalize(t) for t in haystack.split()}
                for term in search_terms:
                    if normalize(term) not in hay_tokens and normalize(term) not in name_lower:
                        return False
                return True

            results = [p for p in results if matches(p)]

        return results

    def get_product(self, item_id: str) -> Product | None:
        for product in self.products:
            if product.item_id == item_id:
                return product
        return None

    def list_all(self) -> list[Product]:
        return list(self.products)

    def by_category(self) -> dict:
        grouped: dict = {}
        for p in self.products:
            cat = p.category or "Other"
            grouped.setdefault(cat, []).append(p)
        return grouped
