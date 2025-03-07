import asyncio
import json
import logging
from typing import Any, Dict

import aiofiles

try:
    import gpiozero
except ImportError:
    gpiozero = None  # Simulation mode when no GPIO available

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
    RelayController controls a relay via GPIO.
    
    Logical states are "on" and "off". The wiring is defined by the relay’s 'normalState'.
    This class exposes simple async methods (turn_on, turn_off, pulse, device_state)
    and ensures that each relay’s internal state is updated and persisted to the hardware
    configuration file.
    """
    def __init__(self, config: Dict[str, Any], hardware_config_file: str = "app/config/hardware_config.json") -> None:
        """
        Expected keys in config:
          - relayId: Unique identifier (e.g. "relay_1")
          - gpioPin: GPIO pin number used to control the relay
          - normalState: Defines the hardware wiring; expected values "open" or "closed"
          - currentState: The current state ("on" or "off"); must be in sync with hardware
          - bootState: Desired state at boot ("on" or "off")
          - pulse_time: Optional pulse duration in seconds (default: 1)
        """
        self.relay_id = config["relayId"]
        self.gpio_pin = config["gpioPin"]
        self.normal_state = config["normalState"].lower()  # "open" or "closed"
        self.boot_state = config.get("bootState", "off").lower()
        self.logical_state = config.get("currentState", self.boot_state).lower()
        self.pulse_time = config.get("pulse_time", 1)
        self.hardware_config_file = hardware_config_file

        # Determine the physical device's initial output from stored logical state.
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
        Maps stored logical state to physical output.
          For normalState "open": logical "on" → True; "off" → False.
          For normalState "closed": logical "on" → False; "off" → True.
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
        Ensures the relay is set to its boot state.
        If the actual state does not match the boot state, update it and persist the change.
        """
        current = self._get_logical_state()
        if current != self.boot_state:
            logger.info(f"{self.relay_id}: current state '{current}' does not match boot state '{self.boot_state}'. Updating.")
            self._apply_logical_state(self.boot_state)
            self._update_config_sync(self.boot_state)
        else:
            logger.info(f"{self.relay_id}: already in boot state '{self.boot_state}'.")

    def _apply_logical_state(self, desired: str) -> None:
        """
        Applies the desired logical state ("on" or "off") to the physical device.
          - For normalState "open": "on" → device.on(), "off" → device.off()
          - For normalState "closed": inverted logic.
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
        physical = self.device.value  # True or False
        if self.normal_state == "open":
            return "on" if physical else "off"
        elif self.normal_state == "closed":
            return "on" if not physical else "off"
        else:
            logger.error(f"Invalid normalState for {self.relay_id}")
            return "unknown"

    def _update_config_sync(self, state: str) -> None:
        """
        Synchronously updates the hardware configuration file with the new state.
        It modifies the "currentState" for the matching relay.
        """
        try:
            with open(self.hardware_config_file, "r") as f:
                config_data = json.load(f)
            updated = False
            for relay in config_data.get("relays", []):
                if relay.get("relayId") == self.relay_id:
                    relay["currentState"] = state
                    updated = True
                    break
            if updated:
                with open(self.hardware_config_file, "w") as f:
                    json.dump(config_data, f, indent=4)
            else:
                logger.warning(f"{self.relay_id} not found in hardware config file.")
        except Exception as e:
            logger.error(f"Error updating hardware config for {self.relay_id}: {e}")

    async def _update_config_async(self, state: str) -> None:
        """
        Asynchronously updates the hardware configuration file.
        """
        try:
            async with aiofiles.open(self.hardware_config_file, "r") as f:
                data = await f.read()
            config_data = json.loads(data)
            updated = False
            for relay in config_data.get("relays", []):
                if relay.get("relayId") == self.relay_id:
                    relay["currentState"] = state
                    updated = True
                    break
            if updated:
                async with aiofiles.open(self.hardware_config_file, "w") as f:
                    await f.write(json.dumps(config_data, indent=4))
            else:
                logger.warning(f"{self.relay_id} not found in hardware config file (async).")
        except Exception as e:
            logger.error(f"Error updating hardware config async for {self.relay_id}: {e}")

    def sync_turn_on(self) -> None:
        """
        Synchronously turns the relay on and updates the hardware config.
        """
        self._apply_logical_state("on")
        self._update_config_sync("on")

    def sync_turn_off(self) -> None:
        """
        Synchronously turns the relay off and updates the hardware config.
        """
        self._apply_logical_state("off")
        self._update_config_sync("off")

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
        Asynchronously returns the current logical state.
        """
        return await asyncio.to_thread(self._get_logical_state)

    async def pulse(self) -> None:
        """
        Asynchronously pulses the relay for the configured duration.
        Toggles the relay, waits asynchronously, then reverts to its previous state.
        """
        current = await self.device_state()
        if current == "on":
            await self.turn_off()
            await asyncio.sleep(self.pulse_time)
            await self.turn_on()
        else:
            await self.turn_on()
            await asyncio.sleep(self.pulse_time)
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
