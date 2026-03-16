import sys
import uuid
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class DriveItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: uuid.UUID
    name: str
    is_starred: bool = False

class DummySQLAlchemyModel:
    def __init__(self, item_id, name):
        self.item_id = item_id
        self.name = name

# Test
mock_obj = DummySQLAlchemyModel(item_id=uuid.uuid4(), name="test.txt")
mock_obj.is_starred = True  # Dynamically assigned

response = DriveItemResponse.model_validate(mock_obj)
print(f"Result: is_starred = {response.is_starred}")
