import asyncio
import logging
import time
from typing import Any, Dict, Optional
from gpiozero import OutputDevice, Device, LED
from gpiozero.pins.rpigpio import RPiGPIOFactory

Device.pin_factory = RPiGPIOFactory()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class RelayController:
    """
    RelayController controls a relay using GPIO.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.relay_id = config["relayId"]
        self.gpio_pin = config["gpioPin"]
        self.normal_state = config["normalState"].lower()  # "open" or "closed"
        self.boot_state = config.get("bootState", "off").lower()
        self.logical_state = config.get("currentState", self.boot_state).lower()
        self.pulse_time = config.get("pulse_time", 1)
        
        # Determine the initial physical output from the stored logical state.
        initial = self._initial_physical_state()
        try:
            self.device = OutputDevice(self.gpio_pin, initial_value=initial)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[GPIO] {self.relay_id}: Initialized device on pin {self.gpio_pin} with value {initial} at {ts}")
        except Exception as e:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.error(f"[GPIO] {self.relay_id}: Error initializing device on pin {self.gpio_pin}: {e} at {ts}")
            # Do not raise the error; assign None to device so subsequent calls log an error.
            self.device = None

        self._setup_device()

    def _initial_physical_state(self) -> bool:
        """
        Map the stored logical state to a physical output.
        For normalState "open": logical "on" → True, "off" → False.
        For normalState "closed": logical "on" → False, "off" → True.
        """
        if self.normal_state == "open":
            return True if self.logical_state == "on" else False
        elif self.normal_state == "closed":
            return False if self.logical_state == "on" else True
        else:
            logger.error(f"{self.relay_id}: Invalid normalState value: {self.normal_state}")
            return False

    def _setup_device(self) -> None:
        """
        Ensure the relay is set to its boot state.
        """
        current = self._get_logical_state()
        if current != self.boot_state:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"{self.relay_id}: Current state '{current}' does not match boot state '{self.boot_state}' at {ts}. Updating.")
            self._apply_logical_state(self.boot_state)
        else:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"{self.relay_id}: Already in boot state '{self.boot_state}' at {ts}.")

    def _apply_logical_state(self, desired: str) -> None:
        """
        Applies the desired logical state ("on" or "off") to the physical device.
        Errors are logged but do not interrupt the flow.
        """
        desired = desired.lower()
        try:
            if self.device is None:
                logger.error(f"[GPIO] {self.relay_id}: Device not initialized.")
                return
            if self.normal_state == "open":
                if desired == "on":
                    self.device.on()
                else:
                    self.device.off()
            elif self.normal_state == "closed":
                if desired == "on":
                    self.device.off()
                else:
                    self.device.on()
            else:
                logger.error(f"[GPIO] {self.relay_id}: Invalid normalState: {self.normal_state}")
            self.logical_state = desired
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[GPIO] {self.relay_id}: Set to '{desired}' at {ts}")
        except Exception as e:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.error(f"[GPIO] {self.relay_id}: Failed to set state '{desired}': {e} at {ts}")

    def _get_logical_state(self) -> str:
        """
        Retrieves the current logical state by mapping the physical device output.
        """
        if self.device is None:
            logger.error(f"{self.relay_id}: Device not initialized.")
            return "unknown"
        physical = self.device.value
        if self.normal_state == "open":
            return "on" if physical else "off"
        elif self.normal_state == "closed":
            return "on" if not physical else "off"
        else:
            logger.error(f"{self.relay_id}: Invalid normalState: {self.normal_state}")
            return "unknown"

    def sync_turn_on(self) -> None:
        """Synchronously turns the relay on."""
        self._apply_logical_state("on")

    def sync_turn_off(self) -> None:
        """Synchronously turns the relay off."""
        self._apply_logical_state("off")

    async def turn_on(self) -> None:
        """Asynchronously turns the relay on."""
        await asyncio.to_thread(self.sync_turn_on)

    async def turn_off(self) -> None:
        """Asynchronously turns the relay off."""
        await asyncio.to_thread(self.sync_turn_off)

    async def device_state(self) -> str:
        """Asynchronously retrieves the current logical state."""
        return await asyncio.to_thread(self._get_logical_state)

    async def pulse(self, duration: Optional[float] = None) -> None:
        """
        Asynchronously pulses the relay for the given duration (default pulse_time).
        """
        dur = duration if duration is not None else self.pulse_time
        current = await self.device_state()
        if current == "on":
            await self.turn_off()
            await asyncio.sleep(dur)
            await self.turn_on()
        else:
            await self.turn_on()
            await asyncio.sleep(dur)
            await self.turn_off()

    def sync_cleanup(self) -> None:
        """Releases the GPIO device synchronously."""
        if self.device:
            try:
                self.device.close()
            except Exception as e:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                logger.error(f"[GPIO] {self.relay_id}: Error during cleanup: {e} at {ts}")

    async def cleanup(self) -> None:
        """Releases the GPIO device asynchronously."""
        await asyncio.to_thread(self.sync_cleanup)
