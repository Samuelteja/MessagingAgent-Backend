# src/schemas/tag_rule_schemas.py

from pydantic import BaseModel, ConfigDict, computed_field
from typing import Optional

class _TagInRule(BaseModel):
    name: str

class TagRuleBase(BaseModel):
    keyword: str

class TagRuleCreate(TagRuleBase):
    tag_id: int

class TagRule(TagRuleBase):
    id: int
    tag: _TagInRule

    @computed_field
    @property
    def tag_to_apply(self) -> str:
        """
        This computed field creates the 'tag_to_apply' key in the JSON response
        by using the name from the nested 'tag' object.
        """
        return self.tag.name

    model_config = ConfigDict(from_attributes=True)