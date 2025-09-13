# src/menu_schemas.py
from pydantic import BaseModel
from typing import Optional, List

# --- Upsell Rule Schemas ---
class UpsellRuleBase(BaseModel):
    suggestion_text: str
    upsell_menu_item_id: int

class UpsellRuleCreate(UpsellRuleBase):
    pass

class UpsellRule(UpsellRuleBase):
    id: int
    trigger_menu_item_id: int

    class Config:
        orm_mode = True

# --- Menu Item Schemas ---
class MenuItemBase(BaseModel):
    name: str
    category: str
    price: float
    description: Optional[str] = None

class MenuItemCreate(MenuItemBase):
    pass

class MenuItem(MenuItemBase):
    id: int
    upsell_rule: Optional[UpsellRule] = None

    class Config:
        orm_mode = True