"""Support for Phyn Plus Water Monitor sensors."""
from __future__ import annotations
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
from homeassistant.core import callback

from ..entity import PhynEntity, PhynSwitchEntity

WATER_ICON = "mdi:water"
GAUGE_ICON = "mdi:gauge"
NAME_DAILY_USAGE = "Daily water usage"
NAME_FLOW_RATE = "Current water flow rate"
NAME_WATER_TEMPERATURE = "Current water temperature"
NAME_WATER_PRESSURE = "Current water pressure"

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

class PhynFirmwareUpdateAvailableSensor(PhynEntity, BinarySensorEntity):
    """Firmware Update Available Sensor"""
    _attr_device_class = BinarySensorDeviceClass.UPDATE

    def __init__(self, device):
        """Intialize Firmware Update Sensor."""
        super().__init__("firmware_update_available", "Firmware Update Available", device)

    @property
    def is_on(self) -> bool:
        return self._device.firmware_has_update

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

class PhynDailyUsageSensor(PhynEntity, SensorEntity):
    """Monitors the daily water usage."""

    _attr_icon = WATER_ICON
    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.WATER

    def __init__(self, device):
        """Initialize the daily water usage sensor."""
        super().__init__("daily_consumption", NAME_DAILY_USAGE, device)
        self._state: float = None

    @property
    def native_value(self) -> float | None:
        """Return the current daily usage."""
        if self._device.consumption_today is None:
            return None
        return round(self._device.consumption_today, 1)

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

    _attr_native_unit_of_measurement = "gpm"
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_translation_key = "current_flow_rate"

    def __init__(self, device):
        """Initialize the flow rate sensor."""
        super().__init__("current_flow_rate", NAME_FLOW_RATE, device)
        self._state: float = None

    @property
    def native_value(self) -> float | None:
        """Return the current flow rate."""
        if self._device.current_flow_rate is None:
            return None
        return round(self._device.current_flow_rate, 1) 


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
        await self._device.api_client.device.open_valve(self._device.id)

    def open_valve(self) -> None:
        """Open the valve."""
        raise NotImplementedError()
    
    async def async_close_valve(self) -> None:
        """Close the valve."""
        await self._device.api_client.device.close_valve(self._device.id)

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


class PhynTemperatureSensor(PhynEntity, SensorEntity):
    """Monitors the temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT

    def __init__(self, device):
        """Initialize the temperature sensor."""
        super().__init__("temperature", NAME_WATER_TEMPERATURE, device)
        self._state: float = None

    @property
    def native_value(self) -> float | None:
        """Return the current temperature."""
        if self._device.temperature is None:
            return None
        return round(self._device.temperature, 1)


class PhynPressureSensor(PhynEntity, SensorEntity):
    """Monitors the water pressure."""

    _attr_device_class = SensorDeviceClass.PRESSURE
    _attr_native_unit_of_measurement = UnitOfPressure.PSI
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT

    def __init__(self, device):
        """Initialize the pressure sensor."""
        super().__init__("water_pressure", NAME_WATER_PRESSURE, device)
        self._state: float = None

    @property
    def native_value(self) -> float | None:
        """Return the current water pressure."""
        if self._device.current_psi is None:
            return None
        return round(self._device.current_psi, 1)
