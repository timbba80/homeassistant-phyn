"""Phyn device object."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from aiophyn.api import API
from aiophyn.errors import RequestError
from async_timeout import timeout

from .exceptions import HaAuthError, HaCannotConnect

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .const import DOMAIN as PHYN_DOMAIN, LOGGER

from .devices.pp2 import (
    PhynFlowState,
    PhynDailyUsageSensor,
    PhynCurrentFlowRateSensor,
    PhynSwitch,
    PhynTemperatureSensor,
    PhynPressureSensor
)

import json


class PhynDeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Phyn device object."""

    def __init__(
        self, hass: HomeAssistant, api_client: API, home_id: str, device_id: str
    ) -> None:
        """Initialize the device."""
        self.hass: HomeAssistant = hass
        self.api_client: API = api_client
        self._phyn_home_id: str = home_id
        self._phyn_device_id: str = device_id
        self._manufacturer: str = "Phyn"
        self._device_state: dict[str, Any] = {}
        self._rt_device_state: dict[str, Any] = {}
        self._water_usage: dict[str, Any] = {}

        self.entities = [
            PhynFlowState(self),
            PhynDailyUsageSensor(self),
            PhynCurrentFlowRateSensor(self),
            PhynTemperatureSensor(self),
            PhynPressureSensor(self),

            PhynSwitch(self),
        ]

        super().__init__(
            hass,
            LOGGER,
            name=f"{PHYN_DOMAIN}-{device_id}",
            #update_interval=timedelta(seconds=60),
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            async with timeout(20):
                await self._update_device()
                await self._update_consumption_data()
        except (RequestError) as error:
            raise UpdateFailed(error) from error

    @property
    def home_id(self) -> str:
        """Return Phyn home id."""
        return self._phyn_home_id

    @property
    def id(self) -> str:
        """Return Phyn device id."""
        return self._phyn_device_id

    @property
    def device_name(self) -> str:
        """Return device name."""
        return f"{self.manufacturer} {self.model}"

    @property
    def manufacturer(self) -> str:
        """Return manufacturer for device."""
        return self._manufacturer

    @property
    def model(self) -> str:
        """Return model for device."""
        return self._device_state["product_code"]

    @property
    def rssi(self) -> float:
        """Return rssi for device."""
        if "rssi" in self._rt_device_state:
            return self._rt_device_state['rssi']
        return self._device_state["signal_strength"]

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        return self._device_state["online_status"]["v"] == "online"

    @property
    def current_flow_rate(self) -> float:
        """Return current flow rate in gpm."""
        if "flow" in self._rt_device_state:
            if round(self._rt_device_state['flow']['v'], 2) == 0:
                return 0.0
            return round(self._rt_device_state['flow']['v'], 3)
        return round(self._device_state["flow"]["mean"], 3)

    @property
    def current_psi(self) -> float:
        """Return the current pressure in psi."""
        if "sensor_data" in self._rt_device_state:
            return round(self._rt_device_state['sensor_data']['pressure']['v'], 2)
        return round(self._device_state["pressure"]["mean"], 2)

    @property
    def temperature(self) -> float:
        """Return the current temperature in degrees F."""
        if "sensor_data" in self._rt_device_state:
            return round(self._rt_device_state['sensor_data']['temperature']['v'], 2)
        return round(self._device_state["temperature"]["mean"], 2)

    @property
    def consumption_today(self) -> float:
        """Return the current consumption for today in gallons."""
        return self._water_usage["water_consumption"]

    @property
    def firmware_version(self) -> str:
        """Return the firmware version for the device."""
        return self._device_state["fw_version"]

    @property
    def serial_number(self) -> str:
        """Return the serial number for the device."""
        return self._device_state["serial_number"]

    @property
    def valve_state(self) -> str:
        """Return the valve state for the device."""
        if "sov_state" in self._rt_device_state:
            return self._rt_device_state["sov_state"]
        if "sov_status" in self._device_state:
            return self._device_state["sov_status"]["v"]
        return None

    async def async_setup(self):
        """Setup a new device coordinator"""
        LOGGER.debug("Setting up coordinator")

        await self.api_client.mqtt.add_event_handler("update", self.on_device_update)
        await self.api_client.mqtt.subscribe("prd/app_subscriptions/%s" % self._phyn_device_id)

    async def _update_device(self, *_) -> None:
        """Update the device state from the API."""
        self._device_state = await self.api_client.device.get_state(
            self._phyn_device_id
        )
        LOGGER.debug("Phyn device state: %s", self._device_state)

    async def _update_consumption_data(self, *_) -> None:
        """Update water consumption data from the API."""
        today = dt_util.now().date()
        duration = today.strftime("%Y/%m/%d")
        self._water_usage = await self.api_client.device.get_consumption(
            self._phyn_device_id, duration
        )
        LOGGER.debug("Updated Phyn consumption data: %s", self._water_usage)

    async def on_device_update(self, device_id, data):
        #LOGGER.debug("Received new data: %s" % json.dumps(data, indent=2))
        if device_id == self._phyn_device_id:
            self._rt_device_state = data
            for entity in self.entities:
                #LOGGER.debug(f"Updating {entity} ({entity.unique_id}, {entity.entity_id})")
                entity.async_write_ha_state()
