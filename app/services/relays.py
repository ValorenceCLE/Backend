import RPi.GPIO as GPIO  # type: ignore
import logging
from typing import Any
from app.models.relays import Relay, HardwareConfig
import time

# import gpiozero # type: ignore #! Alternative library for GPIO control
#! RPi.GPIO may not be compatable with Pi5, use gpiozero instead


class Controller(Relay):
    """
    Controller class for managing relay states and GPIO configurations.
    """

    def __init__(self, relay: Relay, hardwareConfig: HardwareConfig) -> None:
        super().__init__(**relay.dict())
        self.hardwareConfig = HardwareConfig(**hardwareConfig.dict())
        self._setup_gpio()

    def _setup_gpio(self) -> None:
        """
        Set up GPIO pins based on the relay's hardware configuration.
        """
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.hardwareConfig.pin, GPIO.OUT)
            logging.info(f"GPIO setup for pin {self.hardwareConfig.pin} as {self.hardwareConfig.setup}")
            if self.bootState == "on":
                self.turn_on()
            else:
                logging.info(f"Relay {self.id} boot state is off.")
        except Exception as e:
            logging.error(f"Failed to set up GPIO for pin {self.hardwareConfig.pin}: {e}")

    def turn_on(self) -> None:
        """
        Turn on the relay.
        """
        try:
            GPIO.output(self.hardwareConfig.pin, GPIO.LOW if self.hardwareConfig.normallyOpen else GPIO.HIGH)
            self.state = "on"
            logging.info(f"Relay {self.id} turned on.")
        except Exception as e:
            logging.error(f"Failed to turn on relay {self.id}: {e}")

    def turn_off(self) -> None:
        """
        Turn off the relay.
        """
        try:
            GPIO.output(self.hardwareConfig.pin, GPIO.HIGH if self.hardwareConfig.normallyOpen else GPIO.LOW)
            self.state = "off"
            logging.info(f"Relay {self.id} turned off.")
        except Exception as e:
            logging.error(f"Failed to turn off relay {self.id}: {e}")

    def pulse(self) -> None:
        """
        Pulse the relay for a specified duration.
        """
        try:
            self.turn_on()
            logging.info(f"Pulsing relay {self.id} for {self.pulseTime} seconds.")
            time.sleep(self.pulseTime)
            self.turn_off()
        except Exception as e:
            logging.error(f"Failed to pulse relay {self.id}: {e}")

    def check_state(self) -> bool:
        """
        Check if the relay is currently on.
        """
        try:
            pin_state = GPIO.input(self.hardwareConfig.pin)
            if self.hardwareConfig.normallyOpen:
                return pin_state == GPIO.LOW
            else:
                return pin_state == GPIO.HIGH
        except Exception as e:
            logging.error(f"Failed to check state of relay {self.id}: {e}")
            return False

    def cleanup(self) -> None:
        """
        Clean up GPIO settings.
        """
        try:
            GPIO.cleanup(self.hardwareConfig.pin)
            logging.info(f"GPIO cleanup for pin {self.hardwareConfig.pin} completed.")
        except Exception as e:
            logging.error(f"Failed to clean up GPIO for pin {self.hardwareConfig.pin}: {e}")

    


# Example class usage
# relay = Relay(id="1", name="relay_1", enabled=True, state="off", bootState="off", pulseTime=5, schedule=None, dashboard=None)
# hardware_config = HardwareConfig(id="1", pin=17, address="0x20", setup="OUT", normallyOpen=True)

#! Example JSON config:
#* {
#*     "relays": {
#*         "1": {
#*             "id": "relay_1",
#*             "pin": 22,
#*             "address": "0x46",
#*             "mode": "BCM",
#*             "setup": "OUT",
#*             "normallyOpen": true
#*         },
#*     }
#* }