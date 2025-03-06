from pydantic import BaseModel, Field
from typing import Optional

try:
    from app.utils.config import settings
except ImportError:
    from utils.config import settings


class Schedule(BaseModel):
    enabled: bool = Field(..., description="Whether the schedule is enabled")
    on_time: Optional[str] = Field(None, description="Time to turn the relay on")
    off_time: Optional[str] = Field(None, description="Time to turn the relay off")
    days_mask: Optional[int] = Field(0, description="Days mask for the schedule")


class ButtonConfig(BaseModel):
    show: bool = Field(..., description="Whether the button is shown on the dashboard")
    status_text: str = Field(..., description="Text to display for the button status")
    status_color: str = Field(..., description="Color to display for the button status")
    button_label: str = Field(..., description="Label for the button")


class DashboardConfig(BaseModel):
    on_button: ButtonConfig = Field(..., description="Configuration for the 'On' button")
    off_button: ButtonConfig = Field(..., description="Configuration for the 'Off' button")
    pulse_button: ButtonConfig = Field(..., description="Configuration for the 'Pulse' button")


class Relay(BaseModel):
    id: str = Field(..., description="Unique identifier for the relay")
    name: str = Field(..., description="Name of the relay")
    enabled: bool = Field(..., description="Whether the relay is enabled")
    state: str = Field(..., description="Current state of the relay")
    boot_state: str = Field(..., description="State of the relay on boot")
    pulse_time: int = Field(..., description="Pulse time for the relay in seconds")
    schedule: Schedule = Field(..., description="Schedule configuration for the relay")
    dashboard: DashboardConfig = Field(..., description="Settings for how the relay is displayed on the dashboard")


class HardwareConfig(BaseModel):
    id: str = Field(..., description="Unique identifier for the hardware configuration")
    pin: int = Field(..., description="GPIO pin number for the relay")
    address: str = Field(..., description="I2C address for the relay")
    setup: str = Field(..., description="GPIO setup (e.g., IN or OUT)")
    normally_open: bool = Field(..., description="Whether the relay is normally open")
