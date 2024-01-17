"""Phyn device object."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from aiophyn.api import API
from aiophyn.errors import RequestError
from async_timeout import timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .exceptions import HaAuthError, HaCannotConnect
from .const import DOMAIN as PHYN_DOMAIN, LOGGER

from .devices.pp import (
    PhynAwayModeSwitch,
    PhynFlowState,
    PhynDailyUsageSensor,
    PhynConsumptionSensor,
    PhynCurrentFlowRateSensor,
    PhynFirmwareUpdateAvailableSensor,
    PhynLeakTestSensor,
    PhynScheduledLeakTestEnabledSwitch,
    PhynValve,
    PhynTemperatureSensor,
    PhynPressureSensor
)


class PhynDeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Phyn device object."""

    def __init__(
        self, hass: HomeAssistant, api_client: API, home_id: str, device_id: str,
        product_code: str
    ) -> None:
        """Initialize the device."""
        self.hass: HomeAssistant = hass
        self.api_client: API = api_client
        self._phyn_home_id: str = home_id
        self._phyn_device_id: str = device_id
        self._product_code: str = product_code
        self._manufacturer: str = "Phyn"
        self._device_state: dict[str, Any] = {
            "flow_state": {
                "v": 0.0,
                "ts": 0,
            }
        }
        self._device_preferences: dict[dict[str, Any]] = {}
        self._firmware_info: dict[str, Any] = {}
        self._rt_device_state: dict[str, Any] = {}
        self._away_mode: dict[str, Any] = {}
        self._water_usage: dict[str, Any] = {}
        self._last_known_valve_state: bool = True

        if product_code in ['PP1','PP2']:
            # Entities for Phyn Plus 1 and Phyn Plus 2
            self.entities = [
                PhynAwayModeSwitch(self),
                PhynFlowState(self),
                PhynDailyUsageSensor(self),
                PhynCurrentFlowRateSensor(self),
                PhynConsumptionSensor(self),
                PhynFirmwareUpdateAvailableSensor(self),
                PhynLeakTestSensor(self),
                PhynScheduledLeakTestEnabledSwitch(self),
                PhynTemperatureSensor(self),
                PhynPressureSensor(self),
                PhynValve(self),
            ]

        super().__init__(
            hass,
            LOGGER,
            name=f"{PHYN_DOMAIN}-{device_id}",
            update_interval=timedelta(seconds=60),
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            async with timeout(20):
                await self._update_device()
                await self._update_device_preferences()
                await self._update_firmware_information()
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
        if "v" not in self._device_state["flow"]:
            return None
        return round(self._device_state["flow"]["v"], 3)

    @property
    def current_psi(self) -> float:
        """Return the current pressure in psi."""
        if "v" in self._device_state["pressure"]:
            return round(self._device_state["pressure"]["v"], 2)
        return round(self._device_state["pressure"]["mean"], 2)

    @property
    def temperature(self) -> float:
        """Return the current temperature in degrees F."""
        if "v" in self._device_state["temperature"]:
            return round(self._device_state["temperature"]["v"], 2)
        return round(self._device_state["temperature"]["mean"], 2)

    @property
    def consumption(self) -> float:
        """Return the current consumption for today in gallons."""
        if "consumption" not in self._rt_device_state:
            return None
        return self._rt_device_state["consumption"]["v"]

    @property
    def consumption_today(self) -> float:
        """Return the current consumption for today in gallons."""
        return self._water_usage["water_consumption"]

    @property
    def firmware_version(self) -> str:
        """Return the firmware version for the device."""
        return self._device_state["fw_version"]
    
    @property
    def firmware_has_update(self) -> bool:
        """Return if the firmware has an update"""
        if "fw_version" not in self._firmware_info:
            return None
        return int(self._firmware_info["fw_version"]) > int(self._device_state["fw_version"])

    @property
    def scheduled_leak_test_enabled(self) -> bool:
        """Return if the scheduled leak test is enabled"""
        if "scheduler_enable" not in self._device_preferences:
            return None
        return self._device_preferences["scheduler_enable"]["value"] == "true"

    @property
    def serial_number(self) -> str:
        """Return the serial number for the device."""
        return self._device_state["serial_number"]

    @property
    def valve_open(self) -> bool:
        """Return the valve state for the device."""
        if self.valve_changing:
            return self._last_known_valve_state
        self._last_known_valve_state = self._device_state["sov_status"]["v"] == "Open"
        return self._device_state["sov_status"]["v"] == "Open"

    @property
    def valve_changing(self) -> bool:
        """Return the valve changing status"""
        return self._device_state["sov_status"]["v"] == "Partial"

    @property
    def leak_test_running(self) -> bool:
        """Check if a leak test is running"""
        return self._device_state["sov_status"]["v"] == "LeakExp"

    async def async_setup(self):
        """Setup a new device coordinator"""
        LOGGER.debug("Setting up coordinator")

        await self.api_client.mqtt.add_event_handler("update", self.on_device_update)
        await self.api_client.mqtt.subscribe(f"prd/app_subscriptions/{self._phyn_device_id}")
        return self._device_state["sov_status"]["v"]

    @property
    def away_mode(self) -> bool:
        """Return True if device is in away mode."""
        if "leak_sensitivity_away_mode" not in self._device_preferences:
            return None
        return self._device_preferences["leak_sensitivity_away_mode"]["value"] == "true"

    async def set_device_preference(self, name: str, val: bool) -> None:
        """Set Device Preference"""
        if name not in ["leak_sensitivity_away_mode", "scheduler_enable"]:
            LOGGER.debug("Tried setting preference for %s but not avialable", name)
            return None
        if val not in ["true", "false"]:
            return None
        params = [{
            "device_id": self._phyn_device_id,
            "name": name,
            "value": val
        }]
        LOGGER.debug("Setting preference '%s' to '%s'", name, val)
        await self.api_client.device.set_device_preferences(self._phyn_device_id, params)
        if name not in self._device_preferences:
            self._device_preferences[name] = {}
        self._device_preferences[name]["value"] = val
    
    async def set_away_mode(self, state: bool) -> None:
        """Manually set away mode value"""
        key = "leak_sensitivity_away_mode"
        val = "true" if state else "false"
        params = [{
            "device_id": self._phyn_device_id,
            "name": key,
            "value": val
        }]
        await self.api_client.device.set_device_preferences(self._phyn_device_id, params)
        self._device_preferences[key]["value"] = val

    async def set_scheduler_enabled(self, state: bool) -> None:
        """Manually set the scheduler enabled mode"""
        key = "scheduler_enable"
        val = "true" if state else "false"
        params = [{
            "device_id": self._phyn_device_id,
            "name": key,
            "value": val
        }]
        await self.api_client.set_device_preferences(self._phyn_device_id, params)
        self._device_preferences[key]["value"] = val

    async def _update_device(self, *_) -> None:
        """Update the device state from the API."""
        self._device_state.update(await self.api_client.device.get_state(
            self._phyn_device_id
        ))
        #LOGGER.debug("Phyn device state: %s", self._device_state)

    async def _update_device_preferences(self, *_) -> None:
        """Update the device preferences from the API"""
        data = await self.api_client.device.get_device_preferences(self._phyn_device_id)
        for item in data:
            self._device_preferences.update({item['name']: item})
        LOGGER.debug("Device Preferences: %s", self._device_preferences)

    async def _update_consumption_data(self, *_) -> None:
        """Update water consumption data from the API."""
        today = dt_util.now().date()
        duration = today.strftime("%Y/%m/%d")
        self._water_usage = await self.api_client.device.get_consumption(
            self._phyn_device_id, duration
        )
        LOGGER.debug("Updated Phyn consumption data: %s", self._water_usage)

    async def _update_firmware_information(self, *_) -> None:
        self._firmware_info.update((await self.api_client.device.get_latest_firmware_info(self._phyn_device_id))[0])
        #LOGGER.debug("Firmware Info: %s", self._firmware_info)

    async def on_device_update(self, device_id, data):
        if device_id == self._phyn_device_id:
            self._rt_device_state = data

            update_data = {}
            if "flow" in data:
                update_data.update({"flow": data["flow"]})
            if "flow_state" in data:
                update_data.update({"flow_state": data["flow_state"]})
            if "sov_state" in data:
                update_data.update({"sov_status":{"v": data["sov_state"]}})
            if "sensor_data" in data:
                if "pressure" in data["sensor_data"]:
                    update_data.update({"pressure": data["sensor_data"]["pressure"]})
                if "temperature" in data["sensor_data"]:
                    update_data.update({"temperature": data["sensor_data"]["temperature"]})
            self._device_state.update(update_data)
            LOGGER.debug("Device State: %s", self._device_state)

            for entity in self.entities:
                entity.async_write_ha_state()

    async def _update_away_mode(self, *_) -> None:
        """Update the away mode data from the API"""
        self._away_mode = await self.api_client.device.get_away_mode(
            self._phyn_device_id
        )
        LOGGER.debug("Phyn away mode: %s", self._away_mode)
