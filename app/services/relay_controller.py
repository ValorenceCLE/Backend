import asyncio
import logging
from typing import Any, Dict, Optional
try:
    import gpiozero
except ImportError:
    gpiozero = None  # Simulation mode when no GPIO is available

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class FakeOutputDevice:
    """
    A fake GPIO output device for simulation mode.
    """
    def __init__(self, gpio_pin: int, initial_value: bool = False) -> None:
        self.gpio_pin = gpio_pin
        self.value = initial_value
        logger.info(f"[SIM] FakeOutputDevice on pin {gpio_pin} initialized with value {initial_value}")

    def on(self) -> None:
        self.value = True
        logger.info(f"[SIM] FakeOutputDevice on pin {self.gpio_pin} turned ON")

    def off(self) -> None:
        self.value = False
        logger.info(f"[SIM] FakeOutputDevice on pin {self.gpio_pin} turned OFF")

    def close(self) -> None:
        logger.info(f"[SIM] FakeOutputDevice on pin {self.gpio_pin} closed")


class RelayController:
    """
    RelayController controls a relay using GPIO (or in simulation mode).
    
    Static configuration (relayId, gpioPin, sensorAddress, normalState, currentState) comes
    from hardware_config.py. Dynamic fields (such as pulse_time) are obtained from app.state.config.
    
    This class exposes simple asynchronous methods:
      - turn_on()
      - turn_off()
      - pulse(duration: Optional[float])
      - device_state()
      
    It does not perform any file I/O.
    """
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Expected keys in config:
          - relayId: e.g. "relay_1"
          - gpioPin: e.g. 22
          - normalState: "open" or "closed"
          - currentState: "on" or "off"
          - bootState: Desired state at boot ("on" or "off")
          - pulse_time: Default pulse duration (from static config)
        """
        self.relay_id = config["relayId"]
        self.gpio_pin = config["gpioPin"]
        self.normal_state = config["normalState"].lower()  # "open" or "closed"
        self.boot_state = config.get("bootState", "off").lower()
        self.logical_state = config.get("currentState", self.boot_state).lower()
        self.pulse_time = config.get("pulse_time", 1)

        # Determine the initial physical output from the stored logical state.
        initial = self._initial_physical_state()
        if gpiozero is not None:
            try:
                self.device = gpiozero.OutputDevice(self.gpio_pin, initial_value=initial)
            except Exception as e:
                logger.error(f"Error initializing gpiozero for {self.relay_id}: {e}")
                self.device = FakeOutputDevice(self.gpio_pin, initial_value=initial)
        else:
            logger.warning("gpiozero not available – using simulation mode.")
            self.device = FakeOutputDevice(self.gpio_pin, initial_value=initial)

        self._setup_device()

    def _initial_physical_state(self) -> bool:
        """
        Maps the stored logical state to a physical output.
          For normalState "open": logical "on" → True, "off" → False.
          For normalState "closed": logical "on" → False, "off" → True.
        """
        if self.normal_state == "open":
            return True if self.logical_state == "on" else False
        elif self.normal_state == "closed":
            return False if self.logical_state == "on" else True
        else:
            logger.error(f"Invalid normalState for {self.relay_id}")
            return False

    def _setup_device(self) -> None:
        """
        Ensure the relay is set to its boot state.
        """
        current = self._get_logical_state()
        if current != self.boot_state:
            logger.info(f"{self.relay_id}: current state '{current}' does not match boot state '{self.boot_state}'. Updating.")
            self._apply_logical_state(self.boot_state)
        else:
            logger.info(f"{self.relay_id}: already in boot state '{self.boot_state}'.")

    def _apply_logical_state(self, desired: str) -> None:
        """
        Applies the desired logical state ("on" or "off") to the physical device.
          For normalState "open": "on" → device.on(), "off" → device.off()
          For normalState "closed": inverted logic.
        """
        desired = desired.lower()
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
            logger.error(f"Invalid normalState for {self.relay_id}")
        self.logical_state = desired

    def _get_logical_state(self) -> str:
        """
        Returns the current logical state by mapping the physical device output.
        """
        physical = self.device.value
        if self.normal_state == "open":
            return "on" if physical else "off"
        elif self.normal_state == "closed":
            return "on" if not physical else "off"
        else:
            logger.error(f"Invalid normalState for {self.relay_id}")
            return "unknown"

    def sync_turn_on(self) -> None:
        """
        Synchronously turns the relay on.
        """
        self._apply_logical_state("on")

    def sync_turn_off(self) -> None:
        """
        Synchronously turns the relay off.
        """
        self._apply_logical_state("off")

    async def turn_on(self) -> None:
        """
        Asynchronously turns the relay on.
        """
        await asyncio.to_thread(self.sync_turn_on)

    async def turn_off(self) -> None:
        """
        Asynchronously turns the relay off.
        """
        await asyncio.to_thread(self.sync_turn_off)

    async def device_state(self) -> str:
        """
        Asynchronously retrieves the current logical state.
        """
        return await asyncio.to_thread(self._get_logical_state)

    async def pulse(self, duration: Optional[float] = None) -> None:
        """
        Asynchronously pulses the relay.
        If a duration is provided, it is used; otherwise, self.pulse_time is used.
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
        """
        Synchronously releases the GPIO device.
        """
        self.device.close()

    async def cleanup(self) -> None:
        """
        Asynchronously releases the GPIO device.
        """
        await asyncio.to_thread(self.sync_cleanup)
