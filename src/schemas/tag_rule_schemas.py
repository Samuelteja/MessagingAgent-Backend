# src/schemas/tag_rule_schemas.py

from pydantic import BaseModel, ConfigDict

class TagRuleBase(BaseModel):
    keyword: str
    tag_id: int

class TagRuleCreate(TagRuleBase):
    pass

class TagRule(TagRuleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)