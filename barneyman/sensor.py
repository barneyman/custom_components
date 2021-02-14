import logging
import json
import voluptuous as vol
from datetime import datetime, timedelta
from homeassistant.helpers.template import Template
from homeassistant.components.rest.sensor import RestSensor, RestData
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from .barneymanconst import (
    BARNEYMAN_HOST,
    LISTENING_PORT,
    AUTH_TOKEN,
)
from .helpers import doQuery, doPost, BJFDeviceInfo, BJFRestData, BJFListener
from typing import Any, Dict, List, Optional

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.components.binary_sensor import BinarySensorEntity


_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"

# called from entity_platform.py line 129
# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    _LOGGER.debug("SENSOR async_setup_entry: %s", config_entry.data)

    await hass.async_add_executor_job(addBJFsensor,config_entry.data[BARNEYMAN_HOST], async_add_devices, hass)

    return True









def addBJFsensor(hostname, add_devices, hass):
    _LOGGER.info("addBJFsensor querying %s", hostname)

    config = doQuery(hostname, "/json/config", True)

    if config != None:

        sensorsToAdd = []
        mac = config["mac"]

        # built early, in case it's shared
        url = "http://" + config["ip"] + "/json/state"
        rest = BJFRestData(hass,"GET", url, None, None, None)

        friendlyName = (
            config["friendlyName"] if "friendlyName" in config else config["name"]
        )


        # add a bunch of rest sensors
        if "sensorConfig" in config:
            for eachSensor in config["sensorConfig"]:
                for element in eachSensor["elements"]:
                    deviceClass = element["type"]
                    potential = None

                    # special case - if there's an instant sensor - PIR generally
                    if "impl" in element:

                        sensorValue = Template(
                            '{{ value_json["sensorState"]['
                            + str(eachSensor["sensor"])
                            + "].state"
                            + " }}",
                            hass,
                        )

                        _LOGGER.debug(sensorValue)

                        _LOGGER.info("Potential BJFBinarySensor")

                        potential = BJFBinarySensor(
                            hass,
                            element["impl"],
                            mac,
                            hostname,
                            rest,
                            # entity name
                            friendlyName+" "+eachSensor["name"] + " " + deviceClass,
                            deviceClass,
                            None,
                            sensorValue,
                            eachSensor["sensor"],
                            deviceClass,
                            config,
                        )

                    else:
                        _LOGGER.info("Potential BJFRestSensor")

                        # uom, round

                        uom = element["uom"] if "uom" in element else None
                        numDP = element["round"] if "round" in element else "0"


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
                            # entity name
                            friendlyName+" "+eachSensor["name"] + " " + deviceClass,
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

        return True
    else:
        _LOGGER.error("Failed to query %s", hostname)

    return False


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
        _LOGGER.info("Creating sensor.%s", name)

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



# inherit from a BinarySensorDevice so the icons work right
class BJFBinarySensor(BJFRestSensor, BJFListener, BinarySensorEntity):
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

    # sent from an announcer
    def HandleIncomingPacket(self, data):
        payload = json.loads(data.decode("utf-8"))
        _LOGGER.debug(payload)
        self._is_on = payload["state"]
        _LOGGER.debug("About to set %s state to %s", self.entity_id, self.state)
        self._hass.states.set(self.entity_id, self.state)


    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._is_on

    @property
    def state(self):
        """Return the state of the binary sensor."""
        return self._is_on #STATE_ON if self._is_on==True else STATE_OFF

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._deviceClass

    def update(self):
        # subscribe
        _LOGGER.info("doing binarysensor update")
        self.subscribe("sensor")
        # call base
        return RestSensor.update(self)

    async def async_update(self):
        # subscribe
        _LOGGER.info("doing binarysensor async_update")
        await self.async_subscribe("sensor")
        # call base
        await RestSensor.async_update(self)
        # work out my on state (._state is provided by the restsensor)
        self._is_on=self._state
                        

