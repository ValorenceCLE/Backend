import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Depends, status, Request, Body
from app.utils.dependencies import is_authenticated

# Info for the dashboard 

# We should have an endpoint that easily returns all the active relays and basically all the info
# That is needed to display all the relays on the dashboard