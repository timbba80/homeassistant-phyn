"""Support for Phyn Water Monitor sensors."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN as PHYN_DOMAIN
from .device import PhynDeviceDataUpdateCoordinator

from .devices.pp2 import PhynDailyUsageSensor, PhynCurrentFlowRateSensor, PhynTemperatureSensor, PhynPressureSensor

NAME_WATER_TEMPERATURE = "Average water temperature"

import logging
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Flo sensors from config entry."""
    devices: list[PhynDeviceDataUpdateCoordinator] = hass.data[PHYN_DOMAIN][
        config_entry.entry_id
    ]["devices"]
    entities = []

    for device in devices:
        entities.extend([
            entity
            for entity in device.entities
            if isinstance(entity, SensorEntity) or isinstance(entity, BinarySensorEntity)
        ])

    async_add_entities(entities)
