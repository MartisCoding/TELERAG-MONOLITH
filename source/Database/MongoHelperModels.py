from typing import List, Optional, Tuple, Dict
from pydantic import BaseModel, Field

class UserModel(BaseModel):
    id: int = Field(alias="_id")
    name: str
    channels: Dict[int, str] = Field(default_factory=dict)
    # Changed from List[int] to Dict[int, str] to store channel names
    # This allows us to store channel names directly in the user model

    class Config:
        populate_by_name = True

class ChannelModel(BaseModel):
    id: int = Field(alias="_id")
    name: str
    subscribers: int = 0

    class Config:
        populate_by_name = True