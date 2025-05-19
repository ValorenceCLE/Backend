"""
Task system for hardware control, sensor monitoring, and rule automation.

This package provides a comprehensive set of Celery tasks for:
- Controlling and scheduling relays
- Reading sensor data
- Processing sensor data through rule-based automation
"""
from typing import Dict, Any

# Version info
__version__ = '2.0.0'

# ----- Relay Control Tasks -----

from .relay_tasks import (
    check_schedules,
    get_relay_state,
    set_relay_state, 
    pulse_relay,
    get_all_relay_states
)

# ----- Sensor Data Tasks -----

from .sensor_tasks import (
    read_all_sensors
)

# ----- Rule Automation Tasks -----

from .rule_tasks import (
    evaluate_rules,
    execute_action,
    get_rule_status
)

# ----- Convenience Functions -----

def turn_relay_on(relay_id: str) -> Dict[str, Any]:
    """
    Convenience function to turn a relay ON.
    
    Args:
        relay_id: Identifier for the relay
        
    Returns:
        Task result information
    """
    return set_relay_state.delay(relay_id, True)

def turn_relay_off(relay_id: str) -> Dict[str, Any]:
    """
    Convenience function to turn a relay OFF.
    
    Args:
        relay_id: Identifier for the relay
        
    Returns:
        Task result information
    """
    return set_relay_state.delay(relay_id, False)

def pulse_relay_for(relay_id: str, duration: float = 5.0) -> Dict[str, Any]:
    """
    Convenience function to pulse a relay for a specified duration.
    
    Args:
        relay_id: Identifier for the relay
        duration: Pulse duration in seconds (default: 5.0)
        
    Returns:
        Task result information
    """
    return pulse_relay.delay(relay_id, duration)

def get_all_sensor_data() -> Dict[str, Any]:
    """
    Convenience function to read data from all sensors immediately.
    
    Returns:
        Task result information
    """
    return read_all_sensors.delay()

def check_all_rules(source: str, data: Dict[str, float]) -> Dict[str, Any]:
    """
    Convenience function to evaluate rules for a specific data source.
    
    Args:
        source: The source identifier of the data
        data: Dictionary of data fields with their values
        
    Returns:
        Task result information
    """
    return evaluate_rules.delay(source, data)