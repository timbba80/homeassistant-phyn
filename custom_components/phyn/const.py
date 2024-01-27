"""Constants for the phyn integration."""
import logging
from enum import StrEnum

LOGGER = logging.getLogger(__package__)

CLIENT = "client"
DOMAIN = "phyn"

GPM_TO_LPM = 3.78541
class UnitOfVolumeFlow(StrEnum):
    """Volume units."""
    LITERS_PER_MINUTE = "l/m"
    GALLONS_PER_MINUTE = "gpm"