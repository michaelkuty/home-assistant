"""
Support for the Broadlink RM2 Pro (only temperature) and A1/SP devices.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.broadlink/
"""
from datetime import timedelta
import binascii
import logging
import socket

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_HOST, CONF_MAC, CONF_MONITORED_CONDITIONS, CONF_NAME, TEMP_CELSIUS,
    CONF_TIMEOUT, CONF_TYPE)
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = [
    'https://github.com/mjg59/python-broadlink/archive/master.zip#broadlink']

_LOGGER = logging.getLogger(__name__)

CONF_UPDATE_INTERVAL = 'update_interval'
DEVICE_DEFAULT_NAME = 'Broadlink sensor'
DEFAULT_TIMEOUT = 10

SENSOR_TYPES = {
    'temperature': ['Temperature', TEMP_CELSIUS],
    'air_quality': ['Air Quality', ' '],
    'humidity': ['Humidity', '%'],
    'light': ['Light', ' '],
    'noise': ['Noise', ' '],
    'energy': ['Energy', 'W'],
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEVICE_DEFAULT_NAME): vol.Coerce(str),
    vol.Optional(CONF_MONITORED_CONDITIONS, default=[]):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_UPDATE_INTERVAL, default=timedelta(seconds=300)): (
        vol.All(cv.time_period, cv.positive_timedelta)),
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_TYPE): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int
})


# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Broadlink device sensors."""
    host = config.get(CONF_HOST)
    type = config.get(CONF_TYPE)
    mac = config.get(CONF_MAC).encode().replace(b':', b'')
    mac_addr = binascii.unhexlify(mac)
    name = config.get(CONF_NAME)
    timeout = config.get(CONF_TIMEOUT)
    dev = []
    for variable in config[CONF_MONITORED_CONDITIONS]:
        dev.append(BroadlinkSensor(name, variable,
                                   host, mac_addr, timeout, type))
    add_devices(dev, True)


class BroadlinkSensor(Entity):
    """Representation of a Broadlink device sensor."""

    def __init__(self, name, sensor_type,
                 ip_addr, mac_addr, timeout, device_type=None):
        """Initialize the sensor."""
        self._name = '{} {}'.format(name, SENSOR_TYPES[sensor_type][0])
        self._state = None
        self._device_type = device_type
        self._type = sensor_type
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self.ip_addr = ip_addr
        self.mac_addr = mac_addr
        self.timeout = timeout

        self._schema = vol.Schema({
            vol.Optional('temperature'): vol.Range(min=-50, max=150),
            vol.Optional('humidity'): vol.Range(min=0, max=100),
            vol.Optional('light'): vol.Any(0, 1, 2, 3),
            vol.Optional('air_quality'): vol.Any(0, 1, 2, 3),
            vol.Optional('noise'): vol.Any(0, 1, 2),
            vol.Optional('energy'): vol.Range(min=0, max=3500),
        })

        self._connect()
        if not self._auth():
            _LOGGER.warning("Failed to connect to device")

    def _connect(self):
        import broadlink
        _type = self._device_type or 'a1'
        self._device = getattr(broadlink, _type)(
            (self.ip_addr, 80), self.mac_addr, None)
        self._device.timeout = self.timeout

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self._unit_of_measurement

    def update(self):
        """Get the latest data from the sensor."""
        try:
            if self._type == 'energy':
                self._state = self._device.get_energy()
            else:
                data = self._device.check_sensors_raw()
                if data is not None:
                    self._state = self._schema(data)
        except socket.timeout as error:
            _LOGGER.error(error)
            return
        except (vol.Invalid, vol.MultipleInvalid):
            pass  # Continue quietly if device returned malformed data

    def _auth(self, retry=3):
        try:
            auth = self._device.auth()
        except socket.timeout:
            auth = False
        if not auth and retry > 0:
            self._connect()
            return self._auth(retry-1)
        return auth
