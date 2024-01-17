"""Switch representing the shutoff valve for the Phyn integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN as PHYN_DOMAIN
from .device import PhynDeviceDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Phyn switches from config entry."""
    devices: list[PhynDeviceDataUpdateCoordinator] = hass.data[PHYN_DOMAIN][
        config_entry.entry_id
    ]["devices"]
    entities = []
    for device in devices:
        entities.extend(
            [
                entity
                for entity in device.entities
                if isinstance(entity, BinarySensorEntity)
            ]
        )
    async_add_entities(entities)