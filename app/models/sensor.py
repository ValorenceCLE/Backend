"""
Sensor data models.

This module defines Pydantic models for sensor data.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class SensorReading(BaseModel):
    """Base model for sensor readings"""
    timestamp: datetime
    source: str

class PowerSensorReading(SensorReading):
    """Model for power sensor readings"""
    voltage: float
    current: float
    power: float
    relay_id: str

class EnvironmentalSensorReading(SensorReading):
    """Model for environmental sensor readings"""
    temperature: float
    humidity: float

class SystemMetrics(SensorReading):
    """Model for system performance metrics"""
    cpu: float
    memory: float
    disk: float
    uptime: Optional[float] = None