import RPi.GPIO as GPIO # type: ignore
import logging
from typing import *
from app.models.relays import Relay, HardwareConfig
from app.utils.config import settings
import time


class Controller(Relay):
    """
    Controller class for managing relay states and GPIO configurations.
    """
    def __init__(self, relay: Relay, hardwareConfig: HardwareConfig):
        super().__init__(**relay.dict())
        self._setup_gpio()
        self.hardwareConfig = HardwareConfig(**hardwareConfig.dict())
    def _setup_gpio(self):
        """
        Set up GPIO pins based on the relay's hardware configuration.
        """
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.hardwareConfig.pin, GPIO.OUT)
        if self.bootState == "on":
            self.turn_on()
        else:
            pass


    def turn_on(self):
        """
        Turn on the relay.
        """
        if self.hardwareConfig.normallyOpen:
            GPIO.output(self.hardwareConfig.pin, GPIO.LOW)
        else:
            GPIO.output(self.hardwareConfig.pin, GPIO.HIGH)
        self.state = "on"
        logging.info(f"Relay {self.id} turned on.")

    def turn_off(self):
        """
        Turn off the relay.
        """
        if self.hardwareConfig.normallyOpen:
            GPIO.output(self.hardwareConfig.pin, GPIO.HIGH)
        else:
            GPIO.output(self.hardwareConfig.pin, GPIO.LOW)
        self.state = "off"
        logging.info(f"Relay {self.id} turned off.")
    
    def pulse(self):
        """
        Pulse the relay for a specified duration.
        """
        self.turn_on()
        GPIO.output(self.hardwareConfig.pin, GPIO.HIGH)
        time.sleep(self.pulseTime)
        self.turn_off()


# Example class usage
# relay = Relay(id="1", name="relay_1", enabled=True, state="off", bootState="off", pulseTime=5, schedule=None, dashboard=None)
# hardware_config = HardwareConfig(id="1", pin=17, address="0x20", setup="OUT", normallyOpen=True)