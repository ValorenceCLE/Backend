HardwareConfig = [
    {
        "id": "relay_1",
        "pin": 23,
        "sensor": "0x45",
        "normally": "open",
    },
    {
        "id": "relay_2",
        "pin": 24,
        "sensor": "0x46",
        "normally": "open",
    },
    {
        "id": "relay_3",
        "pin": 4,
        "sensor": "0x47",
        "normally": "open",
    },
    {
        "id": "relay_4",
        "pin": 17,
        "sensor": "0x48",
        "normally": "open",
    },
    {
        "id": "relay_5",
        "pin": 27,
        "sensor": "0x49",
        "normally": "open",
    },
    {
        "id": "relay_6",
        "pin": 22,
        "sensor": "0x50",
        "normally": "open",
    },
]

class Settings:
    """
    Maybe use a class instead of list for config.
    This will allow for more complex configurations and easier management.
    This will have all of the config as well as the hardware config.
    This will also allow for easier validation and error handling.
    We can set this up with functions to make sure that we have easy access to the config.
    This will also allow for easier testing and mocking.
    """
    pass