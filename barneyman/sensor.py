import logging
import json
import voluptuous as vol
from datetime import datetime, timedelta
from homeassistant.helpers.template import Template
from homeassistant.components.rest.sensor import RestSensor, RestData
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from .barneymanconst import (
    BEACH_HEAD,
    DEVICES_ADDED,
    DISCOVERY_ROOT,
    DEVICES_FOUND,
    DEVICES_FOUND_SENSOR,
    LISTENING_PORT,
    AUTH_TOKEN,
)
from .helpers import doQuery, doPost, BJFDeviceInfo, BJFRestData, BJFListener

_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"

# called from entity_platform.py line 129
# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    _LOGGER.debug("SENSOR async_setup_entry: %s", config_entry)

    # simply so i have a ref to async_add_devices
    def scanForSensors(self):
        _LOGGER.info("scanForSensors Called!!!!!")

        workingList = hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
            DEVICES_FOUND_SENSOR
        ].copy()
        hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][DEVICES_FOUND_SENSOR] = []

        for newhost in workingList:
            _LOGGER.info("addBJFsensor %s", newhost)
            addBJFsensor(newhost, async_add_devices, hass)

    # Search for devices
    # removing this causes devices o not be discovered? specuatoive change, enabkibg
    scanForSensors(0)

    # then schedule this again for X seconds.
    async_track_time_interval(hass, scanForSensors, timedelta(seconds=30))

    return True


def addBJFsensor(hostname, add_devices, hass):
    _LOGGER.info("addBJFsensor querying %s", hostname)

    config = doQuery(hostname, "/json/config", True)

    if config != None:

        sensorsToAdd = []
        mac = config["mac"]

        # built early, in case it's shared
        url = "http://" + config["ip"] + "/json/state"
        rest = BJFRestData("GET", url, None, None, None)

        # add a bunch of rest sensors
        for eachSensor in config["sensorConfig"]:
            for element in eachSensor["elements"]:
                deviceClass = element["type"]
                potential = None

                # special case
                if (
                    element["impl"] == "tcp"
                    or element["impl"] == "udp"
                    or element["impl"] == "http"
                ):

                    sensorValue = Template(
                        '{{ value_json["sensorState"]['
                        + str(eachSensor["sensor"])
                        + "].state"
                        + " }}",
                        hass,
                    )

                    _LOGGER.debug(sensorValue)

                    potential = BJFBinarySensor(
                        hass,
                        element["impl"],
                        mac,
                        hostname,
                        rest,
                        eachSensor["name"] + "_" + deviceClass,
                        deviceClass,
                        None,
                        sensorValue,
                        eachSensor["sensor"],
                        deviceClass,
                        config,
                    )

                if element["impl"] == "rest":
                    # type, uom, round
                    uom = element["uom"]
                    numDP = element["round"]

                    # build the template string
                    sensorValue = Template(
                        '{{ value_json["sensorState"]['
                        + str(eachSensor["sensor"])
                        + "]."
                        + deviceClass
                        + " | round("
                        + numDP
                        + ") }}",
                        hass,
                    )

                    _LOGGER.debug(sensorValue)

                    potential = BJFRestSensor(
                        hass,
                        mac,
                        hostname,
                        rest,
                        eachSensor["name"] + "_" + deviceClass,
                        deviceClass,
                        uom,
                        sensorValue,
                        eachSensor["sensor"],
                        deviceClass,
                        config,
                    )

                if potential is not None:
                    _LOGGER.info("Adding sensor %s", potential._unique_id)
                    sensorsToAdd.append(potential)

        add_devices(sensorsToAdd)
    else:
        _LOGGER.error("Failed to query %s", hostname)


# in py, vtable priority is left to right
class BJFRestSensor(BJFDeviceInfo, RestSensor):
    def __init__(
        self,
        hass,
        mac,
        hostname,
        rest,
        name,
        deviceType,
        unit,
        json,
        ordinal,
        element,
        config,
    ):
        RestSensor.__init__(
            self, hass, rest, name, unit, deviceType, json, None, True, None, None
        )
        BJFDeviceInfo.__init__(self, config)

        self._unique_id = mac + "_sensor_" + str(ordinal) + "_" + element
        self._hostname = hostname
        self._mac = mac

    @property
    def unique_id(self):
        """Return unique ID for sensor."""
        return self._unique_id


from homeassistant.const import STATE_OFF, STATE_ON


from homeassistant.components.binary_sensor import BinarySensorDevice

# inherit from a BinarySensorDevice so the icons work right
class BJFBinarySensor(BJFRestSensor, BJFListener, BinarySensorDevice):
    def __init__(
        self,
        hass,
        transport,
        mac,
        hostname,
        rest,
        name,
        deviceType,
        unit,
        json,
        ordinal,
        element,
        config,
    ):
        BJFRestSensor.__init__(
            self,
            hass,
            mac,
            hostname,
            rest,
            name,
            deviceType,
            unit,
            json,
            ordinal,
            element,
            config,
        )

        BJFListener.__init__(self, transport, hass)

        self._name = name
        self._hass = hass
        self._ordinal = ordinal
        self._hostname = hostname
        self._deviceClass = deviceType

        self._is_on = None

    def HandleIncomingPacket(self, data):

        payload = json.loads(data.decode("utf-8"))

        _LOGGER.debug(payload)
        self._is_on = payload["state"]
        _LOGGER.debug("About to set %s state to %s", self.entity_id, self.state)
        self._hass.states.set(self.entity_id, self.state)

    def subscribe(self):

        _LOGGER.debug("Subscribing %s", self.entity_id)

        recipient = {}
        if self.getPort() is not None:
            recipient["port"] = self.getPort()
        recipient["sensor"] = self._ordinal
        recipient["endpoint"] = "/api/states/" + self.entity_id  #  light.study_light
        # dev container - "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiI4MGZlMTdlYjJlZTQ0OTQ0ODJmY2I2Njc4ZTFmMmE1MyIsImlhdCI6MTU4MzYzNDIzOCwiZXhwIjoxODk4OTk0MjM4fQ.B0UOKz2aK0hjJzPbAzY1dDzsYSaFnZZEBba3FyBHf38"
        # rpi3b - "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiI0YjhkYmU3ZDE0ZGE0MjIyOWFmNjU1NWFiYTY3NTZhZSIsImlhdCI6MTU4MzY0MTE3OCwiZXhwIjoxODk5MDAxMTc4fQ.p7qROsU9p_5iV2LGqaJ_O2FvUTsZsE72XKNZdWmWq34"
        recipient["auth"] = self.hass.data[DOMAIN][AUTH_TOKEN]

        _LOGGER.debug(recipient)

        # advise the sensor we're listening
        doPost(self._hostname, "/json/listen", json.dumps(recipient))

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._is_on

    @property
    def state(self):
        """Return the state of the binary sensor."""
        return STATE_ON if self.is_on else STATE_OFF

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._deviceClass

    def update(self):
        # subscribe
        self.subscribe()

        # call base
        return RestSensor.update(self)
