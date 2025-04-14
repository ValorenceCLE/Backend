"""
Relay data models.

This module defines Pydantic models for relay data.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class RelayState(BaseModel):
    """Model for relay state information"""
    id: str
    state: int
    name: Optional[str] = None

class RelayAction(BaseModel):
    """Model for relay action requests"""
    action: str = Field(..., description="Action to perform: 'on', 'off', or 'pulse'")
    duration: Optional[float] = Field(None, description="Duration in seconds for pulse action")

class RelayInfo(BaseModel):
    """Model for detailed relay information"""
    id: str
    name: str
    state: int
    enabled: bool
    pulse_time: Optional[int] = None
    scheduled: bool