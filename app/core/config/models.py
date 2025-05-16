from pydantic import BaseModel, Field
from typing import List, Optional, Union
import subprocess

class NetworkConfig(BaseModel):
    """Network configuration settings."""
    ip_address: str = "192.168.1.2"
    subnet_mask: str = "255.255.255.0"
    gateway: str = "192.168.1.1"
    dhcp: bool = True
    primary_dns: str = "8.8.8.8"
    secondary_dns: Optional[str] = "8.8.4.4"

class DateTimeConfig(BaseModel):
    """Date and time settings."""
    primary_ntp: str = "ntp.axis.com"
    secondary_ntp: Optional[str] = "time.google.com"
    synchronize: bool = True
    timezone: str = "America/Denver"
    utc_offset: int = -7

class ButtonConfig(BaseModel):
    """UI button configuration."""
    show: bool = True
    status_text: str = ""
    status_color: str = ""
    button_label: str = ""

class DashboardConfig(BaseModel):
    """Dashboard UI configuration."""
    on_button: ButtonConfig = Field(default_factory=ButtonConfig)
    off_button: ButtonConfig = Field(default_factory=ButtonConfig)
    pulse_button: ButtonConfig = Field(default_factory=ButtonConfig)

class RelaySchedule(BaseModel):
    """
    Relay schedule configuration model.
    """
    enabled: bool = False
    on_time: Optional[str] = None
    off_time: Optional[str] = None
    days_mask: int = 0  # Bitmask for days using custom bit values

class RelayConfig(BaseModel):
    """Relay configuration."""
    id: str
    name: str
    enabled: bool = True
    pulse_time: int = 5
    schedule: Union[RelaySchedule, bool] = Field(default_factory=lambda: RelaySchedule())  # Allow bool or RelaySchedule
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)

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
    actions: List[TaskAction] = Field(default_factory=list)

class GeneralConfig(BaseModel):
    """General system configuration."""
    system_name: str = "Valorence System"
    system_id: str = Field(default_factory=lambda: subprocess.check_output(['cat', '/proc/cpuinfo']).decode().split('Serial')[1].split(':')[1].strip().split('\n')[0])
    version: str = "1.0.0"
    agency: str = "Valorence"
    product: str = "DPM"
    reboot_time: str = "04:00"

class EmailConfig(BaseModel):
    """Email configuration."""
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_secure: str = "tls"
    return_email: str = ""
    emails: List[str] = Field(default_factory=list)

class AppConfig(BaseModel):
    """Complete application configuration model."""
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    date_time: DateTimeConfig = Field(default_factory=DateTimeConfig)
    relays: List[RelayConfig] = Field(default_factory=list)
    tasks: List[Task] = Field(default_factory=list)
    email: EmailConfig = Field(default_factory=EmailConfig)