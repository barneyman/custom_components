import logging
import json
import voluptuous as vol
from datetime import datetime, timedelta
from homeassistant.helpers.template import Template
from homeassistant.components.rest.sensor import RestSensor
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from .barneymanconst import BARNEYMAN_DEVICES, BARNEYMAN_DEVICES_SEEN, DEVICES_SENSOR

from homeassistant.core import callback

from .helpers import (
    doQuery,
    doPost,
    BJFDeviceInfo,
    BJFRestData,
    BJFListener,
    async_doQuery,
    BJFFinder,
)
from typing import Any, Dict, List, Optional

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.components.binary_sensor import BinarySensorEntity


_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"

# called from entity_platform.py line 129
# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    _LOGGER.debug("SENSOR async_setup_entry: %s", config_entry.data)

    async def async_update_options(hass, entry) -> None:

        _LOGGER.info("async_update_options {}".format(entry.title))
        # reload me
        await async_scan_for(config_entry)

    async def async_scan_for(config_entry):

        _LOGGER.debug("async_scan_for addBJFsensor {}".format(config_entry.data))
        addResult = await addBJFsensor(config_entry.data, async_add_devices, hass)

        if addResult != True:
            _LOGGER.error("SENSOR async_setup_entry: %s FAILED", config_entry.entry_id)

        return addResult

    # add a listener to the config entry
    _LOGGER.debug("adding listener for {}".format(config_entry.title))
    config_entry.add_update_listener(async_update_options)

    # scan for lights
    _LOGGER.debug("first scan {}".format(config_entry.title))
    addResult = await async_scan_for(config_entry)

    # await hass.async_add_executor_job(addBJFsensor,config_entry.data[BARNEYMAN_HOST], async_add_devices, hass)

    return addResult


from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

wip = []


async def addBJFsensor(data, add_devices, hass):

    sensorsToAdd = []

    if BARNEYMAN_DEVICES not in data:
        return False

    for device in data[BARNEYMAN_DEVICES]:

        hostname = device["hostname"]
        host = device["ip"]

        if hostname in wip:
            _LOGGER.debug("already seen in WIP %s", hostname)
            continue

        if hostname in hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN]:
            _LOGGER.info("device {} has already been added".format(hostname))
            continue

        # optimisation, if they have a pltforms property, bail early on that
        if "properties" in device and "platforms" in device["properties"]:
            _LOGGER.info("device has platforms %s", device["properties"]["platforms"])
            if DEVICES_SENSOR not in device["properties"]["platforms"].split(","):
                _LOGGER.info("optimised config fetch out")
                continue

        _LOGGER.info("addBJFsensor querying %s @ %s", hostname, host)
        wip.append(hostname)

        # config = doQuery(hostname, "/json/config", True)
        config = await async_doQuery(host, "/json/config", True)

        if config != None:

            mac = config["mac"]

            # built early, in case it's shared
            rest = BJFRestData(hass, hostname, "GET", None, None, None)

            friendlyName = (
                config["friendlyName"] if "friendlyName" in config else config["name"]
            )

            # and add a datacoordinator
            coord = DataUpdateCoordinator(
                hass,
                _LOGGER,
                name=friendlyName + "_DUC",
                update_method=rest.async_bjfupdate,
                update_interval=timedelta(seconds=10),
            )

            # await hass.async_add_executor_job(coord.async_config_entry_first_refresh)

            # asyncio.run_coroutine_threadsafe(
            #     coordinator.async_config_entry_first_refresh(), hass.loop
            #     ).result()

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
                                coord,
                                element["impl"],
                                mac,
                                hostname,
                                rest,
                                # entity name
                                friendlyName
                                + " "
                                + eachSensor["name"]
                                + " "
                                + deviceClass,
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
                                coord,
                                mac,
                                hostname,
                                rest,
                                # entity name
                                friendlyName
                                + " "
                                + eachSensor["name"]
                                + " "
                                + deviceClass,
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

                            hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN].append(hostname)

            await coord.async_config_entry_first_refresh()

        else:
            _LOGGER.error(
                "Failed to query %s at onboarding - device not added", hostname
            )
            if hostname in data[BARNEYMAN_DEVICES]:
                data[BARNEYMAN_DEVICES].remove(hostname)

        wip.remove(hostname)

    if add_devices is not None:
        add_devices(sensorsToAdd)
        return True

    return False


# in py, vtable priority is left to right
class BJFRestSensor(CoordinatorEntity, BJFDeviceInfo, BJFFinder, RestSensor):
    def __init__(
        self,
        hass,
        coord,
        mac,
        hostname,
        rest,
        name,
        deviceType,
        unit,
        jsonSensorQuery,
        ordinal,
        element,
        config,
    ):
        _LOGGER.info("Creating sensor.'{}' - '{}'".format(name, jsonSensorQuery))

        BJFFinder.__init__(self, hass, hostname)

        CoordinatorEntity.__init__(self, coord)

        # self,
        # coordinator,
        # rest,
        # name,
        # unit_of_measurement,
        # device_class,
        # state_class,
        # value_template,
        # json_attrs,
        # force_update,
        # resource_template,
        # json_attrs_path,

        RestSensor.__init__(
            # sensorclass
            self,
            coord,
            rest,
            name,
            unit,
            deviceType,
            "measurement",
            value_template=jsonSensorQuery,
            json_attrs=None,
            force_update=True,
            resource_template=None,
            json_attrs_path=None,
        )
        BJFDeviceInfo.__init__(self, config, mac)

        # and subscribe for data updates
        self.async_on_remove(self.coordinator.async_add_listener(self.alertUpdate))

        self._unique_id = mac + "_sensor_" + str(ordinal) + "_" + element
        self._hostname = hostname
        self._hass = hass

    @property
    def unique_id(self):
        """Return unique ID for sensor."""
        return self._unique_id

    @callback
    def alertUpdate(self):
        self._update_from_rest_data()
        # if self._hass is not None:
        #     self._hass.add_job(self.async_subscribe,"sensor")


# inherit from a BinarySensorDevice so the icons work right
class BJFBinarySensor(BJFListener, BinarySensorEntity, BJFRestSensor):  # , ):
    def __init__(
        self,
        hass,
        coord,
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
            coord,
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

        BJFListener.__init__(self, transport, hass, hostname)

        self._name = name
        self._hass = hass
        self._ordinal = ordinal
        self._hostname = hostname
        self._deviceClass = deviceType

        # # and subscribe for data updates
        # self.async_on_remove(
        #     self.coordinator.async_add_listener(self.async_parseData)
        # )

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
        _LOGGER.debug("is_on called %s state %s ", self.entity_id, self._state)
        return self._is_on

    @property
    def state(self):
        """Return the state of the binary sensor."""
        _LOGGER.debug("state called %s state %s ", self.entity_id, self._state)
        return self._is_on  # STATE_ON if self._is_on==True else STATE_OFF

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._deviceClass

    @callback
    def alertUpdate(self):
        # subscribe
        _LOGGER.info("doing binarysensor async_update")
        if self._hass is not None:
            self._hass.add_job(self.subscribe, "sensor")

        self._update_from_rest_data()
        if self.hass is not None:
            self.async_write_ha_state()

        _LOGGER.debug(
            "Got {} from {} using {}".format(
                self._state, self.rest.data, self._value_template
            )
        )
        # work out my on state (._state is provided by the restsensor)
        self._is_on = self._state
