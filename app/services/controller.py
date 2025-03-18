from typing import Dict, Any, Optional
import asyncio
import logging
from app.utils.hardware import HardwareConfig
import gpiod
from gpiod.line import Direction, Value

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class RelayControl:
    """
    A class to control a relay via GPIO pins using the gpiod library.
    The relay state is represented as an integer:
        - 1 means ON (active)
        - 0 means OFF (inactive)
    Hardware configuration is loaded from a configuration file that maps relay IDs to GPIO pins.
    The current hardware state is always read directly from the device.
    """

    def __init__(self, relay_id: str) -> None:
        self.id: str = relay_id
        self.config: Optional[Dict[str, Any]] = self._get_hardware_info()
        if self.config is None:
            error_msg = f"No configuration found for relay '{relay_id}'"
            logger.error(error_msg)
            raise ValueError(error_msg)
        self.pin: int = self.config["pin"]
        self._setup_relay()
        logger.info(
            f"Relay '{self.id}' initialized on pin {self.pin} with state: "
            f"{'ON' if self.state == 1 else 'OFF'}"
        )

    def _get_hardware_info(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve hardware configuration for the relay.

        Returns:
            A configuration dictionary for the relay if found, otherwise None.
        """
        for config in HardwareConfig:
            if config.get("id") == self.id:
                logger.debug(f"Found configuration for relay '{self.id}': {config}")
                return config
        logger.error(f"Relay '{self.id}' not found in hardware configuration.")
        return None

    def _setup_relay(self) -> None:
        """
        Setup the gpiod device control for the relay.
        First, the current state of the pin is determined by temporarily requesting it as input.
        Then, the line is requested as output using that current state,
        ensuring that we preserve the pin's actual state during setup.
        """
        try:
            chip = gpiod.Chip("/dev/gpiochip0")
            # Temporarily request the line as input to read its current state.
            temp_request = gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="TempReader",
                config={self.pin: gpiod.LineSettings(direction=Direction.INPUT)},
            )
            temp_value = temp_request.get_value(self.pin)
            current_value = 1 if temp_value == Value.ACTIVE else 0
            logger.debug(
                f"Relay '{self.id}' current value on pin {self.pin} read as: "
                f"{'ON' if current_value == 1 else 'OFF'}"
            )
            temp_request.release()
            # Now request the line as output, preserving the measured state.
            self.request = gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="GpioController",
                config={
                    self.pin: gpiod.LineSettings(
                        direction=Direction.OUTPUT,
                        output_value=Value.ACTIVE if current_value == 1 else Value.INACTIVE,
                    )
                },
            )
            logger.debug(
                f"Device setup complete for relay '{self.id}', pin {self.pin} with initial state: "
                f"{'ON' if current_value == 1 else 'OFF'}"
            )
        except Exception as e:
            logger.exception(f"Failed to setup device for relay '{self.id}': {e}")
            raise

    def _get_current_state(self) -> int:
        """
        Get the current state of the relay from the hardware.

        Returns:
            int: The current state (1 for ON, 0 for OFF).
        """
        try:
            value = self.request.get_value(self.pin)
            state_value = 1 if value == Value.ACTIVE else 0
            logger.info(
                f"Relay '{self.id}' current state read as: {'ON' if state_value == 1 else 'OFF'}"
            )
            return state_value
        except Exception as e:
            logger.exception(f"Failed to get current state for relay '{self.id}': {e}")
            raise

    @property
    def state(self) -> int:
        """
        Always return the current state of the relay directly from hardware.
        """
        return self._get_current_state()

    def _change_state(self, new_state: int) -> Dict[str, Any]:
        """
        Change the state of the relay to the new state.

        Args:
            new_state (int): The new state to set (1 for ON, 0 for OFF).

        Returns:
            Dict[str, Any]: A dictionary with the relay id, status, and confirmed state.
        """
        if new_state not in (0, 1):
            raise ValueError("State must be 0 (OFF) or 1 (ON)")
        try:
            value = Value.ACTIVE if new_state == 1 else Value.INACTIVE
            self.request.set_values({self.pin: value})
            confirmed_state = self._get_current_state()
            status_str = "success" if confirmed_state == new_state else "error"
            logger.info(
                f"Relay '{self.id}' set to {'ON' if new_state == 1 else 'OFF'}; confirmed state: "
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
        Asynchronously turn the relay ON.

        Returns:
            Dict[str, Any]: A dictionary with the relay id, status, and confirmed state.
        """
        logger.info(f"Turning relay '{self.id}' ON.")
        return await asyncio.to_thread(self._change_state, 1)

    async def turn_off(self) -> Dict[str, Any]:
        """
        Asynchronously turn the relay OFF.

        Returns:
            Dict[str, Any]: A dictionary with the relay id, status, and confirmed state.
        """
        logger.info(f"Turning relay '{self.id}' OFF.")
        return await asyncio.to_thread(self._change_state, 0)

    async def toggle(self) -> Dict[str, Any]:
        """
        Asynchronously toggle the relay state.

        Returns:
            Dict[str, Any]: A dictionary with the relay id, status, and confirmed state after toggling.
        """
        current_state = self.state
        logger.info(
            f"Toggling relay '{self.id}' from state: {'ON' if current_state == 1 else 'OFF'}."
        )
        new_state = 1 if current_state == 0 else 0
        logger.info(f"New state after toggle will be: {'ON' if new_state == 1 else 'OFF'}.")
        return await asyncio.to_thread(self._change_state, new_state)
