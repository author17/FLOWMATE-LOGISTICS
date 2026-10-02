"""Business types: what a new business gets at sign-up and which optional screens it sees.
Add a new type (clinic, salon, ...) by adding one entry here - nothing else needs to change."""
KINDS = {
    "cafe":    {"section": "Food & hospitality", "label": "Café / restaurant", "location_kind": "cafe", "modules": ["Delivery"],
                "categories": ["Coffee & drinks", "Food", "Bakery", "Ingredients", "Packaging & supplies"]},
    "gym":     {"section": "Fitness & wellness", "label": "Gym / fitness studio", "location_kind": "gym", "modules": ["Members"],
                "categories": ["Memberships", "Drinks & snacks", "Merchandise", "Equipment", "Cleaning & supplies"]},
    "shop":    {"section": "Retail & other", "label": "Retail shop", "location_kind": "shop", "modules": ["Delivery"],
                "categories": ["Products", "Supplies", "Packaging"]},
    "general": {"section": "Retail & other", "label": "Other / mixed business", "location_kind": "shop", "modules": ["Members", "Delivery"],
                "categories": []},
}
OPTIONAL_SCREENS = {"Members", "Delivery"}      # every other screen is shown to every business

def kind_info(kind: str) -> dict: return KINDS.get(kind) or KINDS["general"]
def modules_for(kind: str) -> list[str]: return kind_info(kind)["modules"]

SECTIONS = ["Food & hospitality", "Fitness & wellness", "Retail & other"]   # the 3 groups shown on the sign-up screen
