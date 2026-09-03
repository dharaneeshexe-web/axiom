from typing import List, Optional
from ..models.schemas import Product


class CatalogService:
    def __init__(self):
        self.products = self._load_catalog()

    def _load_catalog(self) -> List[Product]:
        return [
            # ---- DEMO SCENARIO 1: iPhone 16 (variants) ----
            Product(
                item_id="iphone16_black_128",
                name="iPhone 16 Black 128GB",
                description="iPhone 16 Black, 128GB",
                price=7990000,  # ₹79,900
                merchant_id="apple_retail_001",
                merchant_name="Apple Retail",
                category="Electronics",
                emoji="\U0001F4F1",
                color="Black",
                storage="128GB",
            ),
            Product(
                item_id="iphone16_blue_128",
                name="iPhone 16 Blue 128GB",
                description="iPhone 16 Blue, 128GB",
                price=7990000,  # ₹79,900
                merchant_id="apple_retail_001",
                merchant_name="Apple Retail",
                category="Electronics",
                emoji="\U0001F4F1",
                color="Blue",
                storage="128GB",
            ),
            Product(
                item_id="iphone16_blue_256",
                name="iPhone 16 Blue 256GB",
                description="iPhone 16 Blue, 256GB",
                price=8590000,  # ₹85,900
                merchant_id="apple_retail_001",
                merchant_name="Apple Retail",
                category="Electronics",
                emoji="\U0001F4F1",
                color="Blue",
                storage="256GB",
            ),
            Product(
                item_id="iphone16_white_256",
                name="iPhone 16 White 256GB",
                description="iPhone 16 White, 256GB",
                price=8590000,  # ₹85,900
                merchant_id="apple_retail_001",
                merchant_name="Apple Retail",
                category="Electronics",
                emoji="\U0001F4F1",
                color="White",
                storage="256GB",
            ),
            Product(
                item_id="iphone16_natural_128",
                name="iPhone 16 Natural 128GB",
                description="iPhone 16 Natural (Titanium), 128GB",
                price=7990000,  # ₹79,900
                merchant_id="apple_retail_001",
                merchant_name="Apple Retail",
                category="Electronics",
                emoji="\U0001F4F1",
                color="Natural",
                storage="128GB",
            ),
            Product(
                item_id="iphone16_pink_128",
                name="iPhone 16 Pink 128GB",
                description="iPhone 16 Pink, 128GB",
                price=7990000,  # ₹79,900
                merchant_id="apple_retail_001",
                merchant_name="Apple Retail",
                category="Electronics",
                emoji="\U0001F4F1",
                color="Pink",
                storage="128GB",
            ),

            # ---- DEMO SCENARIO 2: Crepe Bandages (sizes) ----
            Product(
                item_id="crepe_small",
                name="Crepe Bandage Small",
                description="Crepe bandage, small size (5cm x 4m)",
                price=9000,  # ₹90
                merchant_id="medplus_001",
                merchant_name="MedPlus",
                category="Medical",
                emoji="\U0001FA7A",
                size="Small",
            ),
            Product(
                item_id="crepe_medium",
                name="Crepe Bandage Medium",
                description="Crepe bandage, medium size (7.5cm x 4m)",
                price=11000,  # ₹110
                merchant_id="medplus_001",
                merchant_name="MedPlus",
                category="Medical",
                emoji="\U0001FA7A",
                size="Medium",
            ),
            Product(
                item_id="crepe_large",
                name="Crepe Bandage Large",
                description="Crepe bandage, large size (10cm x 4m)",
                price=13000,  # ₹130
                merchant_id="medplus_001",
                merchant_name="MedPlus",
                category="Medical",
                emoji="\U0001FA7A",
                size="Large",
            ),

            # ---- DEMO SCENARIO 3: Ice Cream Cake (flavors) ----
            Product(
                item_id="cake_chocolate_05",
                name="Chocolate Ice Cream Cake 0.5kg",
                description="Chocolate ice cream cake, 0.5kg (serves 4)",
                price=45000,  # ₹450
                merchant_id="frostbites_001",
                merchant_name="FrostBites",
                category="Food & Beverage",
                emoji="\U0001F370",
                flavor="Chocolate",
                weight="0.5kg",
            ),
            Product(
                item_id="cake_vanilla_05",
                name="Vanilla Ice Cream Cake 0.5kg",
                description="Vanilla ice cream cake, 0.5kg (serves 4)",
                price=45000,  # ₹450
                merchant_id="frostbites_001",
                merchant_name="FrostBites",
                category="Food & Beverage",
                emoji="\U0001F370",
                flavor="Vanilla",
                weight="0.5kg",
            ),
            Product(
                item_id="cake_butterscotch_05",
                name="Butterscotch Ice Cream Cake 0.5kg",
                description="Butterscotch ice cream cake, 0.5kg (serves 4)",
                price=48000,  # ₹480
                merchant_id="frostbites_001",
                merchant_name="FrostBites",
                category="Food & Beverage",
                emoji="\U0001F370",
                flavor="Butterscotch",
                weight="0.5kg",
            ),
            Product(
                item_id="cake_chocolate_1kg",
                name="Chocolate Ice Cream Cake 1kg",
                description="Chocolate ice cream cake, 1kg (serves 8)",
                price=85000,  # ₹850
                merchant_id="frostbites_001",
                merchant_name="FrostBites",
                category="Food & Beverage",
                emoji="\U0001F370",
                flavor="Chocolate",
                weight="1kg",
            ),

            # ---- Basic groceries (checkpoint testing) ----
            Product(
                item_id="apple_1kg",
                name="Fresh Apples",
                description="1kg of fresh, organic apples",
                price=5000,  # ₹50
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Groceries",
                emoji="\U0001F34E",
            ),
            Product(
                item_id="apple_2kg",
                name="Fresh Apples (2kg)",
                description="2kg of fresh, organic apples",
                price=9000,  # ₹90
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Groceries",
                emoji="\U0001F34E",
            ),
            Product(
                item_id="banana_1kg",
                name="Ripe Bananas",
                description="1kg of ripe, sweet bananas",
                price=3000,  # ₹30
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Groceries",
                emoji="\U0001F34C",
            ),
            Product(
                item_id="milk_1l",
                name="Fresh Milk",
                description="1 liter of pasteurized milk",
                price=4500,  # ₹45
                merchant_id="dairydirect_001",
                merchant_name="DairyDirect",
                category="Groceries",
                emoji="\U0001F95B",
            ),
            Product(
                item_id="bread_loaf",
                name="Whole Wheat Bread",
                description="Freshly baked whole wheat bread loaf",
                price=2500,  # ₹25
                merchant_id="bakeryworld_001",
                merchant_name="BakeryWorld",
                category="Groceries",
                emoji="\U0001F35E",
            ),
            Product(
                item_id="eggs_12",
                name="Farm Fresh Eggs",
                description="12 farm fresh eggs",
                price=6000,  # ₹60
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Groceries",
                emoji="\U0001F95A",
            ),
            Product(
                item_id="rice_1kg",
                name="Basmati Rice",
                description="1kg premium basmati rice",
                price=8000,  # ₹80
                merchant_id="groceryhub_001",
                merchant_name="GroceryHub",
                category="Groceries",
                emoji="\U0001F35A",
            ),
            Product(
                item_id="tomato_1kg",
                name="Fresh Tomatoes",
                description="1kg of fresh, red tomatoes",
                price=3500,  # ₹35
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Groceries",
                emoji="\U0001F345",
            ),

            # ---- Meat & Fish (new category) ----
            Product(
                item_id="chicken_curry_500",
                name="Chicken Curry Cut 500g",
                description="Chicken curry cut, 500g, ready to cook",
                price=12000,  # ₹120
                merchant_id="meatcraft_001",
                merchant_name="MeatCraft",
                category="Meat & Fish",
                emoji="\U0001F357",
                weight="500g",
            ),
            Product(
                item_id="chicken_breast_1kg",
                name="Chicken Breast 1kg",
                description="Skinless chicken breast, 1kg",
                price=25000,  # ₹250
                merchant_id="meatcraft_001",
                merchant_name="MeatCraft",
                category="Meat & Fish",
                emoji="\U0001F357",
                weight="1kg",
            ),
            Product(
                item_id="fish_seabass_500",
                name="Sea Bass Fish 500g",
                description="Fresh sea bass fish, 500g, cleaned",
                price=22000,  # ₹220
                merchant_id="meatcraft_001",
                merchant_name="MeatCraft",
                category="Meat & Fish",
                emoji="\U0001F41F",
                weight="500g",
            ),
            Product(
                item_id="mutton_curry_500",
                name="Mutton Curry Cut 500g",
                description="Mutton curry cut, 500g, farm raised",
                price=30000,  # ₹300
                merchant_id="meatcraft_001",
                merchant_name="MeatCraft",
                category="Meat & Fish",
                emoji="\U0001F356",
                weight="500g",
            ),

            # ---- More groceries (staples, fresh produce) ----
            Product(
                item_id="onion_1kg",
                name="Onions 1kg",
                description="1kg of fresh onions",
                price=3200,  # ₹32
                merchant_id="groceryhub_001",
                merchant_name="GroceryHub",
                category="Groceries",
                emoji="\U0001F965",
            ),
            Product(
                item_id="potato_1kg",
                name="Potatoes 1kg",
                description="1kg of firm, fresh potatoes",
                price=2800,  # ₹28
                merchant_id="groceryhub_001",
                merchant_name="GroceryHub",
                category="Groceries",
                emoji="\U0001F954",
            ),
            Product(
                item_id="carrot_500g",
                name="Carrots 500g",
                description="500g of crisp, fresh carrots",
                price=2500,  # ₹25
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Groceries",
                emoji="\U0001F955",
            ),
            Product(
                item_id="spinach_250g",
                name="Spinach Bunch 250g",
                description="Fresh spinach leaves, 250g bunch",
                price=2000,  # ₹20
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Groceries",
                emoji="\U0001F96C",
            ),
            Product(
                item_id="cucumber_500g",
                name="Fresh Cucumber 500g",
                description="500g of crisp cucumbers",
                price=2000,  # ₹20
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Groceries",
                emoji="\U0001F952",
            ),
            Product(
                item_id="capsicum_500g",
                name="Green Capsicum 500g",
                description="500g of fresh green capsicum (bell pepper)",
                price=3500,  # ₹35
                merchant_id="groceryhub_001",
                merchant_name="GroceryHub",
                category="Groceries",
                emoji="\U0001FAD1",
            ),
            Product(
                item_id="turmeric_100g",
                name="Turmeric Powder 100g",
                description="100g of pure turmeric powder",
                price=4000,  # ₹40
                merchant_id="groceryhub_001",
                merchant_name="GroceryHub",
                category="Groceries",
                emoji="\U0001F33F",
            ),
            Product(
                item_id="curd_500g",
                name="Fresh Curd 500g",
                description="Thick fresh curd, 500g",
                price=3000,  # ₹30
                merchant_id="dairydirect_001",
                merchant_name="DairyDirect",
                category="Groceries",
                emoji="\U0001F963",
            ),
            Product(
                item_id="paneer_200g",
                name="Fresh Paneer 200g",
                description="Soft fresh paneer, 200g",
                price=6000,  # ₹60
                merchant_id="dairydirect_001",
                merchant_name="DairyDirect",
                category="Groceries",
                emoji="\U0001F9C0",
            ),
            Product(
                item_id="butter_100g",
                name="Salted Butter 100g",
                description="Creamy salted butter, 100g",
                price=5500,  # ₹55
                merchant_id="dairydirect_001",
                merchant_name="DairyDirect",
                category="Groceries",
                emoji="\U0001F9C8",
            ),
            Product(
                item_id="croissant_1",
                name="Butter Croissant",
                description="Freshly baked butter croissant",
                price=4500,  # ₹45
                merchant_id="bakeryworld_001",
                merchant_name="BakeryWorld",
                category="Groceries",
                emoji="\U0001F950",
            ),
            Product(
                item_id="chips_200g",
                name="Potato Chips 200g",
                description="Crispy salted potato chips, 200g",
                price=6000,  # ₹60
                merchant_id="groceryhub_001",
                merchant_name="GroceryHub",
                category="Groceries",
                emoji="\U0001F35F",
            ),
            Product(
                item_id="biscuits_250g",
                name="Cream Biscuits 250g",
                description="Cream-filled biscuits, 250g",
                price=4500,  # ₹45
                merchant_id="groceryhub_001",
                merchant_name="GroceryHub",
                category="Groceries",
                emoji="\U0001F36A",
            ),
            Product(
                item_id="noodles_300g",
                name="Instant Noodles 300g",
                description="Instant noodles, 300g, 2 packs",
                price=3000,  # ₹30
                merchant_id="groceryhub_001",
                merchant_name="GroceryHub",
                category="Groceries",
                emoji="\U0001F35C",
            ),
            Product(
                item_id="coffee_250g",
                name="Filter Coffee Powder 250g",
                description="South Indian filter coffee powder, 250g",
                price=18000,  # ₹180
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Food & Beverage",
                emoji="\u2615",
            ),
            Product(
                item_id="tea_250g",
                name="Assam Tea 250g",
                description="Strong Assam black tea, 250g",
                price=20000,  # ₹200
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Food & Beverage",
                emoji="\U0001F375",
            ),
            Product(
                item_id="orange_juice_1l",
                name="Orange Juice 1L",
                description="Packed orange juice, 1 liter",
                price=8500,  # ₹85
                merchant_id="freshcart_001",
                merchant_name="FreshCart",
                category="Food & Beverage",
                emoji="\U0001F9C3",
            ),
            Product(
                item_id="cake_birthday_1kg",
                name="Chocolate Birthday Cake 1kg",
                description="Chocolate birthday cake, 1kg (serves 8)",
                price=60000,  # ₹600
                merchant_id="frostbites_001",
                merchant_name="FrostBites",
                category="Food & Beverage",
                emoji="\U0001F382",
                flavor="Chocolate",
                weight="1kg",
            ),
            Product(
                item_id="brownie_1",
                name="Chocolate Brownie",
                description="Rich chocolate brownie, single piece",
                price=7000,  # ₹70
                merchant_id="frostbites_001",
                merchant_name="FrostBites",
                category="Food & Beverage",
                emoji="\U0001F36B",
                flavor="Chocolate",
            ),

            # ---- More electronics (tech essentials) ----
            Product(
                item_id="earbuds_1",
                name="Wireless Earbuds",
                description="Bluetooth wireless earbuds with charging case",
                price=199900,  # ₹1,999
                merchant_id="techbay_001",
                merchant_name="TechBay",
                category="Electronics",
                emoji="\U0001F3A7",
            ),
            Product(
                item_id="powerbank_10k",
                name="Power Bank 10000mAh",
                description="10000mAh fast-charge power bank",
                price=99900,  # ₹999
                merchant_id="techbay_001",
                merchant_name="TechBay",
                category="Electronics",
                emoji="\U0001F50B",
            ),
            Product(
                item_id="smartwatch_1",
                name="Smart Watch",
                description="Fitness smart watch with heart-rate tracking",
                price=249900,  # ₹2,499
                merchant_id="techbay_001",
                merchant_name="TechBay",
                category="Electronics",
                emoji="\u231A",
            ),
            Product(
                item_id="led_bulb_1",
                name="Smart LED Bulb 9W",
                description="9W smart LED bulb, app-controlled",
                price=24900,  # ₹249
                merchant_id="techbay_001",
                merchant_name="TechBay",
                category="Electronics",
                emoji="\U0001F4A1",
            ),
        ]

    def search_products(
        self,
        query: Optional[str] = None,
        merchant_id: Optional[str] = None,
    ) -> List[Product]:
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

    def get_product(self, item_id: str) -> Optional[Product]:
        for product in self.products:
            if product.item_id == item_id:
                return product
        return None

    def list_all(self) -> List[Product]:
        return list(self.products)

    def by_category(self) -> dict:
        grouped: dict = {}
        for p in self.products:
            cat = p.category or "Other"
            grouped.setdefault(cat, []).append(p)
        return grouped
