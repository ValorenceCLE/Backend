from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.utils.config import settings

class Schedule(BaseModel):
    """
    Schedule model representing the on and off times for the relay.
    """
    enabled: bool = Field(..., description="Whether the schedule is enabled")
    onTime: Optional[str] = Field(None, description="Time to turn the relay on")
    offTime: Optional[str] = Field(None, description="Time to turn the relay off")

class ButtonConfig(BaseModel):
    """
    Button configuration model for the dashboard buttons.
    """
    show: bool = Field(..., description="Whether the button is shown on the dashboard")
    statusText: str = Field(..., description="Text to display for the button status")
    statusColor: str = Field(..., description="Color to display for the button status")
    buttonLabel: str = Field(..., description="Label for the button")

class DashboardConfig(BaseModel):
    """
    Dashboard configuration model for the relay.
    """
    onButton: ButtonConfig = Field(..., description="Configuration for the 'On' button")
    offButton: ButtonConfig = Field(..., description="Configuration for the 'Off' button")
    pulseButton: ButtonConfig = Field(..., description="Configuration for the 'Pulse' button")

class Relay(BaseModel):
    """
    Relay model representing a physical relay and its associated configurations.
    """
    id: str = Field(..., description="Unique identifier for the relay")
    name: str = Field(..., description="Name of the relay")
    enabled: bool = Field(..., description="Whether the relay is enabled")
    state: str = Field(..., description="Current state of the relay")
    bootState: str = Field(..., description="State of the relay on boot")
    pulseTime: int = Field(..., description="Pulse time for the relay in seconds")
    schedule: Schedule = Field(..., description="Schedule configuration for the relay")
    dashboard: DashboardConfig = Field(..., description="Settings for how the relay is displayed on the dashboard")

class HardwareConfig(BaseModel):
    """
    Hardware configuration model for the relay.
    """
    id: str = Field(..., description="Unique identifier for the hardware configuration")
    pin: int = Field(..., description="GPIO pin number for the relay")
    address: str = Field(..., description="I2C address for the relay")
    setup: str = Field(..., description="GPIO setup (e.g., IN or OUT)")
    normallyOpen: bool = Field(..., description="Whether the relay is normally open")