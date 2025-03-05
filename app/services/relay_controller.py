import asyncio
import logging
from gpiozero import OutputDevice, Device, LED, PiBoardInfo
try:
    from app.models.relay_models import Relay, HardwareConfig
except ImportError:
    from models.relay_models import Relay, HardwareConfig
    
logger = logging.getLogger("RelayController")
logger.setLevel(logging.INFO)

class Controller(Relay):
    """
    Fully asynchronous Controller for managing relay states using gpiozero.
    This controller:
      - Uses asynchronous methods to turn the relay on/off, pulse it, check its state, and cleanup.
      - Adjusts the meaning of on/off based on the relay wiring:
          * For normally open (NO): logical "on" calls device.on(), "off" calls device.off().
          * For normally closed (NC): logical "on" calls device.off(), "off" calls device.on().
    """
    def __init__(self, relay: Relay, hardwareConfig: HardwareConfig) -> None:
        # Initialize the Relay model using pydantic data
        super().__init__(**relay.dict())
        self.hardwareConfig = HardwareConfig(**hardwareConfig.dict())
        self.device = None  # Will be set in _setup_device
        self.state = "off"
        # Setup the physical device synchronously (this is run once at startup)
        self._setup_device()

    def _setup_device(self) -> None:
        """
        Set up the gpiozero OutputDevice.
        The OutputDevice is created with active_high set to the hardwareConfig.normallyOpen value.
        (For normally open, device.on() sends HIGH, for normally closed, device.on() sends LOW.)
        """
        try:
            self.device = OutputDevice(
                pin=self.hardwareConfig.pin,
                active_high=self.hardwareConfig.normallyOpen,
                initial_value=False
            )
            logger.info(f"Device setup on pin {self.hardwareConfig.pin}")
            # On boot, if the relay should be on, schedule the async_turn_on
            if self.bootState.lower() == "on":
                # Schedule asynchronous turn on (do not await here)
                asyncio.create_task(self.async_turn_on())
            else:
                logger.info(f"Relay {self.id} boot state is off.")
        except Exception as e:
            logger.error(f"Failed to set up device on pin {self.hardwareConfig.pin}: {e}")

    async def async_turn_on(self) -> None:
        """
        Asynchronously turns the relay ON using the correct logic.
        For NO: logical on calls device.on().
        For NC: logical on calls device.off().
        """
        try:
            if self.hardwareConfig.normallyOpen:
                await asyncio.to_thread(self.device.on)
            else:
                await asyncio.to_thread(self.device.off)
            self.state = "on"
            logger.info(f"Relay {self.id} turned ON asynchronously.")
        except Exception as e:
            logger.error(f"Failed to turn on relay {self.id} asynchronously: {e}")

    async def async_turn_off(self) -> None:
        """
        Asynchronously turns the relay OFF using the correct logic.
        For NO: logical off calls device.off().
        For NC: logical off calls device.on().
        """
        try:
            if self.hardwareConfig.normallyOpen:
                await asyncio.to_thread(self.device.off)
            else:
                await asyncio.to_thread(self.device.on)
            self.state = "off"
            logger.info(f"Relay {self.id} turned OFF asynchronously.")
        except Exception as e:
            logger.error(f"Failed to turn off relay {self.id} asynchronously: {e}")

    async def async_pulse(self) -> None:
        """
        Asynchronously pulses the relay:
          - Turns it on,
          - Waits asynchronously for pulseTime seconds,
          - Then turns it off.
        """
        try:
            await self.async_turn_on()
            logger.info(f"Pulsing relay {self.id} for {self.pulseTime} seconds asynchronously.")
            await asyncio.sleep(self.pulseTime)
            await self.async_turn_off()
        except Exception as e:
            logger.error(f"Failed to pulse relay {self.id} asynchronously: {e}")

    async def async_check_state(self) -> bool:
        """
        Asynchronously checks the relay's state.
        For normally open, the device's value directly indicates the physical state.
        For normally closed, the logical state is the inverse.
        Returns True if the relay is logically ON.
        """
        try:
            value = await asyncio.to_thread(lambda: self.device.value)
            # For normally open: logical on = value True.
            # For normally closed: logical on = not value.
            result = value if self.hardwareConfig.normallyOpen else not value
            logger.info(f"Checked state of relay {self.id} asynchronously: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to check state of relay {self.id} asynchronously: {e}")
            return False

    async def async_cleanup(self) -> None:
        """
        Asynchronously closes the device, releasing the GPIO.
        """
        try:
            await asyncio.to_thread(self.device.close)
            logger.info(f"Device cleanup on pin {self.hardwareConfig.pin} completed asynchronously.")
        except Exception as e:
            logger.error(f"Failed to clean up device on pin {self.hardwareConfig.pin} asynchronously: {e}")

    # (Optional) You may keep synchronous methods if needed, but they are not used in async contexts.
