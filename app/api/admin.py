from fastapi import APIRouter, HTTPException
from pathlib import Path
import json

router = APIRouter(prefix="/api", tags=["Public Configuration"])

# Define the path to your configuration file.
# Adjust the path if needed.
CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"

def load_config():
    """Reads and returns the JSON configuration file."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading config file: {e}")

@router.get("/general", summary="Retrieve general configuration")
def get_general():
    config = load_config()
    return config.get("general", {})

@router.get("/network", summary="Retrieve network configuration")
def get_network():
    config = load_config()
    return config.get("network", {})

@router.get("/date_time", summary="Retrieve date and time configuration")
def get_date_time():
    config = load_config()
    return config.get("date_time", {})

@router.get("/email", summary="Retrieve email configuration")
def get_email():
    config = load_config()
    return config.get("email", {})

@router.get("/relays", summary="Retrieve relays configuration")
def get_relays():
    config = load_config()
    return config.get("relays", {})

@router.get("/tasks", summary="Retrieve tasks configuration")
def get_tasks():
    config = load_config()
    return config.get("tasks", {})
