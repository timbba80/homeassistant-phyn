"""Support for Phyn Plus Water Monitor sensors."""
from __future__ import annotations
from typing import Any

from aiophyn.errors import RequestError
from async_timeout import timeout

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature
)
from homeassistant.const import (
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfVolume,
)

from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from homeassistant.helpers.update_coordinator import UpdateFailed
import homeassistant.util.dt as dt_util

from ..const import GPM_TO_LPM, LOGGER, UnitOfVolumeFlow
from ..entities.base import (
    PhynEntity,
    PhynDailyUsageSensor,
    PhynFirmwareUpdateAvailableSensor,
    PhynFirwmwareUpdateEntity,
    PhynPressureSensor,
    PhynTemperatureSensor,
    PhynSwitchEntity
)
from .base import PhynDevice

WATER_ICON = "mdi:water"
GAUGE_ICON = "mdi:gauge"
NAME_DAILY_USAGE = "Daily water usage"
NAME_FLOW_RATE = "Current water flow rate"
NAME_WATER_TEMPERATURE = "Current water temperature"
NAME_WATER_PRESSURE = "Current water pressure"

class PhynPlusDevice(PhynDevice):
    """Phyn device object."""

    def __init__(
        self, coordinator, home_id: str, device_id: str, product_code: str
    ) -> None:
        """Initialize the device."""
        super().__init__ (coordinator, home_id, device_id, product_code)
        self._device_state: dict[str, Any] = {
            "flow_state": {
                "v": 0.0,
                "ts": 0,
            }
        }
        self._away_mode: dict[str, Any] = {}
        self._water_usage: dict[str, Any] = {}
        self._last_known_valve_state: bool = True
        self._rt_device_state: dict[str, Any] = {}

        self.entities = [
            PhynAwayModeSwitch(self),
            PhynFlowState(self),
            PhynDailyUsageSensor(self),
            PhynCurrentFlowRateSensor(self),
            PhynConsumptionSensor(self),
            PhynFirmwareUpdateAvailableSensor(self),
            PhynFirwmwareUpdateEntity(self),
            PhynLeakTestSensor(self),
            PhynScheduledLeakTestEnabledSwitch(self),
            PhynTemperatureSensor(self, "temperature", NAME_WATER_TEMPERATURE),
            PhynPressureSensor(self, "pressure", NAME_WATER_PRESSURE),
            PhynValve(self),
        ]

    async def async_update_data(self):
        """Update data via library."""
        try:
            async with timeout(20):
                await self._update_device_state()
                await self._update_device_preferences()
                await self._update_consumption_data()

                #Update every hour
                if (self._update_count % 60 == 0):
                    await self._update_firmware_information()
                
                self._update_count += 1
        except (RequestError) as error:
            raise UpdateFailed(error) from error

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
    def leak_test_running(self) -> bool:
        """Check if a leak test is running"""
        return self._device_state["sov_status"]["v"] == "LeakExp"

    @property
    def temperature(self) -> float:
        """Return the current temperature in degrees F."""
        if "v" in self._device_state["temperature"]:
            return round(self._device_state["temperature"]["v"], 2)
        return round(self._device_state["temperature"]["mean"], 2)

    @property
    def scheduled_leak_test_enabled(self) -> bool:
        """Return if the scheduled leak test is enabled"""
        if "scheduler_enable" not in self._device_preferences:
            return None
        return self._device_preferences["scheduler_enable"]["value"] == "true"


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

    async def async_setup(self):
        """Setup a new device coordinator"""
        LOGGER.debug("Setting up coordinator")

        await self._coordinator.api_client.mqtt.add_event_handler("update", self.on_device_update)
        await self._coordinator.api_client.mqtt.subscribe(f"prd/app_subscriptions/{self._phyn_device_id}")
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
        await self._coordinator.api_client.device.set_device_preferences(self._phyn_device_id, params)
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
        await self._coordinator.api_client.device.set_device_preferences(self._phyn_device_id, params)
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
        await self._coordinator.api_client.set_device_preferences(self._phyn_device_id, params)
        self._device_preferences[key]["value"] = val

    async def _update_device_preferences(self, *_) -> None:
        """Update the device preferences from the API"""
        data = await self._coordinator.api_client.device.get_device_preferences(self._phyn_device_id)
        for item in data:
            self._device_preferences.update({item['name']: item})
        #LOGGER.debug("Device Preferences: %s", self._device_preferences)

    async def _update_consumption_data(self, *_) -> None:
        """Update water consumption data from the API."""
        today = dt_util.now().date()
        duration = today.strftime("%Y/%m/%d")
        self._water_usage = await self._coordinator.api_client.device.get_consumption(
            self._phyn_device_id, duration
        )
        LOGGER.debug("Updated Phyn consumption data: %s", self._water_usage)

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
            #LOGGER.debug("Device State: %s", self._device_state)

            for entity in self.entities:
                entity.async_write_ha_state()

    async def _update_away_mode(self, *_) -> None:
        """Update the away mode data from the API"""
        self._away_mode = await self._coordinator.api_client.device.get_away_mode(
            self._phyn_device_id
        )
        #LOGGER.debug("Phyn away mode: %s", self._away_mode)

class PhynAwayModeSwitch(PhynSwitchEntity):
    """Switch class for the Phyn Away Mode."""

    def __init__(self, device) -> None:
        """Initialize the Phyn Away Mode switch."""
        super().__init__("away_mode", "Away Mode", device)
        self._preference_name = "leak_sensitivity_away_mode"

    @property
    def _state(self) -> bool:
        return self._device.away_mode

    @property
    def icon(self):
        """Return the icon to use for the away mode."""
        if self.is_on:
            return "mdi:bag-suitcase"
        return "mdi:home-circle"

class PhynFlowState(PhynEntity, SensorEntity):
    """Flow State for Water Sensor"""
    _attr_icon = WATER_ICON
    #_attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    #_attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    #_attr_device_class = SensorDeviceClass.WATER

    def __init__(self, device):
        """Initialize the daily water usage sensor."""
        super().__init__("water_flow_state", "Water Flowing", device)
        self._state: str = None

    @property
    def native_value(self) -> str | None:
        if "flow_state" in self._device._rt_device_state:
            return self._device._rt_device_state['flow_state']['v']
        return None

class PhynLeakTestSensor(PhynEntity, BinarySensorEntity):
    """Leak Test Sensor"""
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, device):
        """Initialize the leak test sensor."""
        super().__init__("leak_test_running", "Leak Test Running", device)

    @property
    def is_on(self) -> bool:
        return self._device.leak_test_running

class PhynScheduledLeakTestEnabledSwitch(PhynSwitchEntity):
    """Switch class for the Phyn Away Mode."""

    def __init__(self, device) -> None:
        """Initialize the Phyn Away Mode switch."""
        super().__init__("scheduled_leak_test_enabled", "Scheduled Leak Test Enabled", device)
        self._preference_name = "scheduler_enable"
    
    @property
    def _state(self) -> bool:
        return self._device.scheduled_leak_test_enabled

    @property
    def icon(self):
        """Return the icon to use for the away mode."""
        if self.is_on:
            return "mdi:bag-suitcase"
        return "mdi:home-circle"

class PhynConsumptionSensor(PhynEntity, SensorEntity):
    """Monitors the amount of water usage."""

    _attr_icon = WATER_ICON
    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.WATER

    def __init__(self, device):
        """Initialize the daily water usage sensor."""
        super().__init__("consumption", "Total Water Usage", device)
        self._state: float = None

    @property
    def native_value(self) -> float | None:
        """Return the current daily usage."""
        if self._device.consumption is None:
            return None
        return round(self._device.consumption, 1)


class PhynCurrentFlowRateSensor(PhynEntity, SensorEntity):
    """Monitors the current water flow rate."""

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_translation_key = "current_flow_rate"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = UnitOfVolumeFlow.GALLONS_PER_MINUTE

    def __init__(self, device):
        """Initialize the flow rate sensor."""
        super().__init__("current_flow_rate", NAME_FLOW_RATE, device)
        self._state: float = None
    
    @property
    def native_unit_of_measurement(self) -> str:
        if self._device.coordinator.hass.config.units is US_CUSTOMARY_SYSTEM:
            return UnitOfVolumeFlow.GALLONS_PER_MINUTE
        return UnitOfVolumeFlow.LITERS_PER_MINUTE

    @property
    def native_value(self) -> float | None:
        """Return the current flow rate."""
        if self._device.current_flow_rate is None:
            return None
        if self.native_unit_of_measurement is UnitOfVolumeFlow.GALLONS_PER_MINUTE:
            return round(self._device.current_flow_rate, 1) 
        return round(self._device.current_flow_rate * GPM_TO_LPM, 1)

class PhynValve(PhynEntity, ValveEntity):
    """ValveEntity for the Phyn valve."""

    def __init__(self, device) -> None:
        """Initialize the Phyn Valve."""
        super().__init__("shutoff_valve", "Shutoff valve", device)
        self._attr_supported_features = ValveEntityFeature(ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE)
        self._attr_device_class = ValveDeviceClass.WATER
        self._attr_reports_position = False
        self._last_known_state: bool = False
    
    async def async_open_valve(self) -> None:
        """Open the valve."""
        await self._device.coordinator.api_client.device.open_valve(self._device.id)

    def open_valve(self) -> None:
        """Open the valve."""
        raise NotImplementedError()
    
    async def async_close_valve(self) -> None:
        """Close the valve."""
        await self._device.coordinator.api_client.device.close_valve(self._device.id)

    def close_valve(self) -> None:
        """Close valve."""
        raise NotImplementedError()
    
    @property
    def _attr_is_closed(self) -> bool | None:
        """ Is the valve closed """
        if self._device.valve_open is None:
            return None
        self._last_known_state = self._device.valve_open
        return not self._device.valve_open
    
    @property
    def _attr_is_opening(self) -> bool:
        """ Is the valve opening """
        if self._device.valve_changing and self._device._last_known_valve_state is False:
            return True
        return False

    @property
    def _attr_is_closing(self) -> bool:
        """ Is the valve closing """
        if self._device.valve_changing and self._device._last_known_valve_state is True:
            return True
        return False
