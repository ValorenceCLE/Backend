# app/core/models/config_models.py
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Union, Any
from datetime import datetime
import ipaddress

class NetworkConfig(BaseModel):
    """Network configuration settings."""
    ip_address: str
    subnet_mask: str
    gateway: str
    dhcp: bool
    primary_dns: str
    secondary_dns: Optional[str] = None

class DateTimeConfig(BaseModel):
    """Date and time settings."""
    primary_ntp: str
    secondary_ntp: Optional[str] = None
    synchronize: bool = True
    timezone: str
    utc_offset: int

class RelaySchedule(BaseModel):
    """Relay scheduling configuration."""
    enabled: bool = False
    on_time: Optional[str] = None
    off_time: Optional[str] = None
    days_mask: int = 0

class ButtonConfig(BaseModel):
    """UI button configuration."""
    show: bool = True
    status_text: str
    status_color: str
    button_label: str

class DashboardConfig(BaseModel):
    """Dashboard UI configuration."""
    on_button: ButtonConfig
    off_button: ButtonConfig
    pulse_button: ButtonConfig

class RelayConfig(BaseModel):
    """Relay configuration."""
    id: str
    name: str
    enabled: bool = True
    pulse_time: int = 5
    schedule: Union[RelaySchedule, bool] = False
    dashboard: DashboardConfig

class TaskAction(BaseModel):
    """Task action configuration."""
    type: str
    target: Optional[str] = None
    state: Optional[str] = None
    message: Optional[str] = None

class Task(BaseModel):
    """Task configuration."""
    id: str
    name: str
    source: str
    field: str
    operator: str
    value: Union[int, float]
    actions: List[TaskAction]

class GeneralConfig(BaseModel):
    """General system configuration."""
    system_name: str
    system_id: str
    version: str
    agency: str
    product: str
    reboot_time: str

class ApplicationConfig(BaseModel):
    """Complete application configuration model."""
    general: GeneralConfig
    network: NetworkConfig
    date_time: DateTimeConfig
    relays: List[RelayConfig]
    tasks: List[Task]