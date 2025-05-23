"""
Hardware control service for GPIO and relay management.

This module provides a unified interface for controlling relays and accessing
GPIO pins. It implements thread safety and proper error handling for hardware
operations.
"""
import threading
import asyncio
import logging
import gpiod
from gpiod.line import Direction, Value
from typing import Dict, Any, Optional, List
from app.core.env_settings import env

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class RelayControl:
    """
    Controls a relay via GPIO using the gpiod library.
    Implements a per-relay singleton pattern.
    
    Logical relay state:
      - 1 means ON (active)
      - 0 means OFF (inactive)
    
    Each relay's hardware configuration (GPIO pin and wiring type) is embedded.
    """
    # Singleton instances per relay id
    _instances: Dict[str, "RelayControl"] = {}
    _init_lock = threading.Lock()

    def __new__(cls, relay_id: str, *args, **kwargs):
        with cls._init_lock:
            if relay_id in cls._instances:
                logger.debug(f"Returning existing instance for relay '{relay_id}'.")
                return cls._instances[relay_id]
            instance = super().__new__(cls)
            cls._instances[relay_id] = instance
        return instance

    def __init__(self, relay_id: str) -> None:
        # Prevent reinitialization if already set up
        if hasattr(self, "_initialized") and self._initialized:
            return

        with RelayControl._init_lock:
            if hasattr(self, "_initialized") and self._initialized:
                return

            self.id: str = relay_id
            self.config: Optional[Dict[str, Any]] = self._get_hardware_info()
            if self.config is None:
                error_msg = f"No configuration found for relay '{relay_id}'"
                logger.error(error_msg)
                raise ValueError(error_msg)
            self.pin: int = self.config["pin"]
            self.normally: str = self.config.get("normally", "open").lower()

            # Setup the GPIO device (only done once per instance)
            self._setup_relay()

            logger.debug(
                f"Relay '{self.id}' initialized on pin {self.pin} with logical state: "
                f"{'ON' if self.state == 1 else 'OFF'} (normally {self.normally})"
            )
            self._initialized = True
            self._lock = asyncio.Lock()

    def _get_hardware_info(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve hardware configuration for the relay from environment settings.
        """
        # Get relay configuration from environment settings
        config = env.HARDWARE_CONFIG.get(self.id)
        if config:
            logger.debug(f"Found configuration for relay '{self.id}': {config}")
        else:
            logger.error(f"Relay '{self.id}' not found in hardware configuration.")
        return config

    def _logical_to_hardware_value(self, logical_state: int) -> int:
        """
        Convert a logical state (1 for ON, 0 for OFF) to the appropriate hardware value,
        taking into account whether the relay is normally open or normally closed.
        """
        if self.normally == "open":
            return Value.ACTIVE if logical_state == 1 else Value.INACTIVE
        elif self.normally == "closed":
            return Value.INACTIVE if logical_state == 1 else Value.ACTIVE
        else:
            raise ValueError(f"Unknown normally state '{self.normally}' for relay '{self.id}'")

    def _hardware_to_logical_state(self, hardware_value: int) -> int:
        """
        Convert a hardware value back to the logical state.
        """
        if self.normally == "open":
            return 1 if hardware_value == Value.ACTIVE else 0
        elif self.normally == "closed":
            return 1 if hardware_value == Value.INACTIVE else 0
        else:
            raise ValueError(f"Unknown normally state '{self.normally}' for relay '{self.id}'")

    def _setup_relay(self) -> None:
        """
        Setup the gpiod device control for the relay.
        Reads the initial state and then requests the line as output.
        """
        try:
            # Open the GPIO chip
            # Request the line temporarily as input to read its current state
            temp_request = gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="TempReader",
                config={self.pin: gpiod.LineSettings(direction=Direction.INPUT)},
            )
            temp_value = temp_request.get_value(self.pin)
            current_logical = self._hardware_to_logical_state(temp_value)
            logger.debug(
                f"Relay '{self.id}' hardware value on pin {self.pin}: "
                f"{'ACTIVE' if temp_value == Value.ACTIVE else 'INACTIVE'} -> logical state: "
                f"{'ON' if current_logical == 1 else 'OFF'}"
            )
            temp_request.release()
            # Now request the line as output, using the current state
            hardware_initial = self._logical_to_hardware_value(current_logical)
            self.request = gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="GpioController",
                config={
                    self.pin: gpiod.LineSettings(
                        direction=Direction.OUTPUT,
                        output_value=hardware_initial,
                    )
                },
            )
            logger.debug(
                f"Device setup complete for relay '{self.id}', pin {self.pin} with initial hardware value: "
                f"{'ACTIVE' if hardware_initial == Value.ACTIVE else 'INACTIVE'}"
            )
        except Exception as e:
            logger.exception(f"Failed to setup device for relay '{self.id}': {e}")
            raise

    def _get_current_state(self) -> int:
        """
        Retrieve the current logical state of the relay from the hardware.
        """
        try:
            hardware_value = self.request.get_value(self.pin)
            logical_state = self._hardware_to_logical_state(hardware_value)
            logger.debug(
                f"Relay '{self.id}' read hardware value on pin {self.pin}: "
                f"{'ACTIVE' if hardware_value == Value.ACTIVE else 'INACTIVE'} -> logical state: "
                f"{'ON' if logical_state == 1 else 'OFF'}"
            )
            return logical_state
        except Exception as e:
            logger.exception(f"Failed to get current state for relay '{self.id}': {e}")
            raise

    @property
    def state(self) -> int:
        """
        Return the current logical state of the relay.
        """
        return self._get_current_state()

    def _change_state(self, new_logical_state: int) -> Dict[str, Any]:
        """
        Change the relay's logical state.
        """
        if new_logical_state not in (0, 1):
            raise ValueError("State must be 0 (OFF) or 1 (ON)")
        try:
            hardware_value = self._logical_to_hardware_value(new_logical_state)
            self.request.set_values({self.pin: hardware_value})
            confirmed_state = self._get_current_state()
            status_str = "success" if confirmed_state == new_logical_state else "error"
            logger.info(
                f"Relay '{self.id}' set to {'ON' if new_logical_state == 1 else 'OFF'}; confirmed logical state: "
                f"{'ON' if confirmed_state == 1 else 'OFF'}"
            )
            return {"id": self.id, "status": status_str, "state": confirmed_state}
        except Exception as e:
            logger.exception(f"Failed to change state for relay '{self.id}': {e}")
            return {
                "id": self.id,
                "status": "error",
                "message": str(e),
                "state": self._get_current_state(),
            }

    async def turn_on(self) -> Dict[str, Any]:
        """
        Asynchronously turn the relay logical state ON.
        """
        logger.debug(f"Turning relay '{self.id}' ON.")
        async with self._lock:
            return await asyncio.to_thread(self._change_state, 1)

    async def turn_off(self) -> Dict[str, Any]:
        """
        Asynchronously turn the relay logical state OFF.
        """
        logger.debug(f"Turning relay '{self.id}' OFF.")
        async with self._lock:
            return await asyncio.to_thread(self._change_state, 0)

    async def toggle(self) -> Dict[str, Any]:
        """
        Asynchronously toggle the relay's logical state.
        """
        current_state = self.state
        logger.info(
            f"Toggling relay '{self.id}' from logical state: {'ON' if current_state == 1 else 'OFF'}."
        )
        new_state = 1 if current_state == 0 else 0
        logger.info(f"New logical state after toggle will be: {'ON' if new_state == 1 else 'OFF'}.")
        return await asyncio.to_thread(self._change_state, new_state)

# Class method to get all relay IDs
def get_all_relay_ids() -> List[str]:
    """
    Get a list of all available relay IDs.
    """
    return list(RelayControl._hardware_config.keys())