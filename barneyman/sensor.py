import logging
import json
import voluptuous as vol
from datetime import datetime, timedelta
from homeassistant.helpers.template import Template
from homeassistant.components.rest.sensor import RestSensor
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from .barneymanconst import (
    BARNEYMAN_HOST,
    LISTENING_PORT,
    AUTH_TOKEN,
    BARNEYMAN_DEVICES,
    BARNEYMAN_DEVICES_SEEN,
    BARNEYMAN_CONFIG_ENTRY

)

from homeassistant.core import callback

from .helpers import doQuery, doPost, BJFDeviceInfo, BJFRestData, BJFListener, async_doQuery
from typing import Any, Dict, List, Optional

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.components.binary_sensor import BinarySensorEntity


_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"

# called from entity_platform.py line 129
# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    _LOGGER.debug("SENSOR async_setup_entry: %s", config_entry.data)

    if config_entry.title != BARNEYMAN_CONFIG_ENTRY:

        _LOGGER.error("Old config entry - removing {}".format(config_entry.title))
        hass.config_entries.async_remove(config_entry)
        return False

    async def async_update_options(hass, entry) -> None:

        _LOGGER.debug("async_update_options {}".format(entry.title))
        # reload me
        await async_scan_for(config_entry)

        """Update options."""
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_scan_for(config_entry):

        _LOGGER.debug("async_scan_for addBJFsensor {}".format(config_entry.data))
        addResult = await addBJFsensor(config_entry.data, async_add_devices, hass)

        if addResult!=True:
            _LOGGER.error("SENSOR async_setup_entry: %s FAILED", config_entry.entry_id)

        return addResult

    # add a listener to the config entry
    _LOGGER.debug("adding listener for {}".format(config_entry.title))
    config_entry.add_update_listener(async_update_options)

    # scan for lights
    _LOGGER.debug("first scan {}".format(config_entry.title))
    addResult = await async_scan_for(config_entry)


    #await hass.async_add_executor_job(addBJFsensor,config_entry.data[BARNEYMAN_HOST], async_add_devices, hass)

    return addResult






from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity


async def addBJFsensor(data, add_devices, hass):

    sensorsToAdd = []

    for hostname in data[BARNEYMAN_DEVICES]:

        if hostname in hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN]:
            _LOGGER.info("device {} has already been added".format(hostname))
            continue

        _LOGGER.info("addBJFsensor querying %s", hostname)

        #config = doQuery(hostname, "/json/config", True)
        config = await async_doQuery(hostname, "/json/config", True)

        if config != None:

            mac = config["mac"]

            # built early, in case it's shared
            url = "http://" + config["ip"] + "/json/state"
            rest = BJFRestData(hass,"GET", url, None, None, None, httptimeout=10, cacheTimeout=0)


            friendlyName = (
                config["friendlyName"] if "friendlyName" in config else config["name"]
            )


            # and add a datacoordinator
            coord = DataUpdateCoordinator(hass,_LOGGER,name=friendlyName+"_DUC", update_method=rest.async_update,update_interval=timedelta(seconds=30))

            await coord.async_config_entry_first_refresh()

            #await hass.async_add_executor_job(coord.async_config_entry_first_refresh)

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
                                coord,
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

                            hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN].append(hostname)


        else:
            _LOGGER.error("Failed to query %s", hostname)

    if add_devices is not None:
        add_devices(sensorsToAdd)
        return True


    return False


# in py, vtable priority is left to right
class BJFRestSensor(CoordinatorEntity, BJFDeviceInfo, RestSensor):
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
        _LOGGER.info("Creating sensor.%s", name)

# self,
#         coordinator,
#         rest,
#         name,
#         unit_of_measurement,
#         device_class,
#         state_class,
#         value_template,
#         json_attrs,
#         force_update,
#         resource_template,
#         json_attrs_path,

        CoordinatorEntity.__init__(self,coord)

        RestSensor.__init__(
            # sensorclass 
            self, coord, rest, name, unit, deviceType, 
                "measurement", 
                value_template=jsonSensorQuery, json_attrs=None, force_update=True, resource_template=None, json_attrs_path=None
        )
        BJFDeviceInfo.__init__(self, config)

        # and subscribe for data updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_alertHA)
        )        


        self._unique_id = mac + "_sensor_" + str(ordinal) + "_" + element
        self._hostname = hostname
        self._mac = mac

    @property
    def unique_id(self):
        """Return unique ID for sensor."""
        return self._unique_id

    @callback
    def async_alertHA(self):
        self._update_from_rest_data()





# inherit from a BinarySensorDevice so the icons work right
class BJFBinarySensor(BJFRestSensor, BJFListener, BinarySensorEntity):
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

        BJFListener.__init__(self, transport, hass)

        self._name = name
        self._hass = hass
        self._ordinal = ordinal
        self._hostname = hostname
        self._deviceClass = deviceType

        # and subscribe for data updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_parseData)
        )        

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

    @callback
    def async_parseData(self):
        # subscribe
        _LOGGER.info("doing binarysensor async_update")
        # work out my on state (._state is provided by the restsensor)
        self._is_on=self._state
                        

