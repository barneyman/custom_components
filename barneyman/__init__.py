"""The example sensor integration."""

import logging
import voluptuous as vol
import json
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers.event import async_track_time_interval
from datetime import datetime, timedelta
from .barneymanconst import (
    BEACH_HEAD,
    DEVICES_ADDED,
    DISCOVERY_ROOT,
    DEVICES_FOUND,
    DEVICES_FOUND_UNQUALIFIED,
    DEVICES_FOUND_LIGHT,
    DEVICES_FOUND_SENSOR,
    DEVICES_FOUND_CAMERA,
    LISTENING_PORT,
    AUTH_TOKEN,
)
from .helpers import doQuery

_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"

import homeassistant.helpers.config_validation as cv


# stuff for zero conf
from zeroconf import Zeroconf, ServiceBrowser

r = Zeroconf()

import socket
import time
from datetime import timedelta


class ServiceListener:
    def __init__(self, zc):
        self.host_addresses = []
        self.zc = zc

    def remove_service(self, zeroconf, type, name):
        _LOGGER.debug("remove_service %s ", name)

    def add_service(self, zeroconf, type, name):
        _LOGGER.debug("add_service name: %s type %s %s", name, type, zeroconf)

        info = self.zc.get_service_info(type, name)
        if info:
            _LOGGER.debug(info)
            _LOGGER.debug("server %s ", info.server)
            address = info.addresses[0]
            _LOGGER.debug("Addr %s", socket.inet_ntoa(address))
            self.host_addresses.append(socket.inet_ntoa(address))


type = "_barneyman._tcp.local."
listener = ServiceListener(r)
browser = ServiceBrowser(r, type, listener=listener)


# async handlers


async def async_setup(hass, baseConfig):
    """Set up is called when Home Assistant is loading our component."""

    _LOGGER.debug("barneyman async_setup called %s", baseConfig)

    # create my 'i've created these' array
    hass.data[DOMAIN] = {
        AUTH_TOKEN: "",
        DISCOVERY_ROOT: {
            LISTENING_PORT: 49152,
            DEVICES_ADDED: [],
            BEACH_HEAD: [],
            DEVICES_FOUND: {
                DEVICES_FOUND_UNQUALIFIED: [],
                DEVICES_FOUND_LIGHT: [],
                DEVICES_FOUND_SENSOR: [],
                DEVICES_FOUND_CAMERA: [],
            },
        },
    }

    def searchForDevices(self):

        # always do a local discovery
        for host in listener.host_addresses:
            if (
                host not in hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_ADDED]
                and host
                not in hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
                    DEVICES_FOUND_UNQUALIFIED
                ]
            ):
                hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
                    DEVICES_FOUND_UNQUALIFIED
                ].append(host)

        # then ask the beachheads
        for bhead in hass.data[DOMAIN][DISCOVERY_ROOT][BEACH_HEAD]:

            if (
                bhead not in hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_ADDED]
                and bhead
                not in hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
                    DEVICES_FOUND_UNQUALIFIED
                ]
            ):
                hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
                    DEVICES_FOUND_UNQUALIFIED
                ].append(bhead)

            result = doQuery(bhead, "/json/peers", True)

            if result is not None:
                for host in result["peers"]:
                    if (
                        host["ip"]
                        not in hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_ADDED]
                    ):
                        hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
                            DEVICES_FOUND_UNQUALIFIED
                        ].append(host["ip"])

            _LOGGER.debug(hass.data[DOMAIN][DISCOVERY_ROOT])

        # and assume we're done with them
        for host in hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
            DEVICES_FOUND_UNQUALIFIED
        ]:
            config = doQuery(host, "/json/config", True)
            if config is not None:

                if "sensorConfig" in config:
                    hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
                        DEVICES_FOUND_SENSOR
                    ].append(host)
                    _LOGGER.debug("Adding %s to %s", host, DEVICES_FOUND_SENSOR)

                if "switchConfig" in config:
                    hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
                        DEVICES_FOUND_LIGHT
                    ].append(host)
                    _LOGGER.debug("Adding %s to %s", host, DEVICES_FOUND_LIGHT)

                if "cameraConfig" in config:
                    hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
                        DEVICES_FOUND_CAMERA
                    ].append(host)
                    _LOGGER.debug("Adding %s to %s", host, DEVICES_FOUND_CAMERA)


                # only add it to found if we could query it, otherwise we'll discovber it again and retry
                hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_ADDED].append(host)

        # hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_ADDED].extend(
        #     hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][DEVICES_FOUND_UNQUALIFIED]
        #)

        hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][DEVICES_FOUND_UNQUALIFIED] = []

        _LOGGER.debug(hass.data[DOMAIN][DISCOVERY_ROOT])

    # _LOGGER.debug("getDeviceList defined")
    # def getDeviceList(call):
    #     listOfDevices=[]
    #     for each in hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_ADDED]:
    #         listOfDevices.append(each)
    #     ret=json.dumps(listOfDevices)
    #     _LOGGER.debug("getDeviceList")
    #     _LOGGER.debug(ret)
    #     return ret


    # # register a service
    # _LOGGER.debug("about to register getDeviceList")
    # try:
    #     hass.services.async_register(DOMAIN,"getDeviceList", getDeviceList)
        

    # except Exception as e:
    #     _LOGGER.error(e)
 

    _LOGGER.debug("defined")


    # look for our devices
    searchForDevices(0)
    async_track_time_interval(hass, searchForDevices, timedelta(seconds=120))

    return True


entryTypes = []
# called after created by configflow - ADDITIONAL to setup, above
async def async_setup_entry(hass, entry):
    _LOGGER.info("barneyman async_setup_entry called %s %s", entry.title, entry.data)

    if AUTH_TOKEN in entry.data:
        hass.data[DOMAIN][AUTH_TOKEN] = entry.data[AUTH_TOKEN]

    # is there a beachhead?
    if BEACH_HEAD in entry.data:
        # let's just check!
        if entry.data[BEACH_HEAD] not in hass.data[DOMAIN][DISCOVERY_ROOT][BEACH_HEAD]:
            hass.data[DOMAIN][DISCOVERY_ROOT][BEACH_HEAD].append(entry.data[BEACH_HEAD])
        else:
            _LOGGER.warning(
                "tried to append %s into beachheads", entry.data[BEACH_HEAD]
            )

    # then forward this to all the component
    for component in [DEVICES_FOUND_LIGHT, DEVICES_FOUND_SENSOR, DEVICES_FOUND_CAMERA]:
        if component not in entryTypes:
            _LOGGER.info("barneyman async_setup_entry forwarding to %s", component)
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setup(entry, component)
            )
            entryTypes.append(component)

    return True


async def async_remove_entry(hass, entry):
    """Handle removal of an entry."""
    _LOGGER.info("async_remove_entry")

    # TODO - this should remove all the entities?

    # is there a beachhead?
    if BEACH_HEAD in entry.data:
        hass.data[DOMAIN][DISCOVERY_ROOT][BEACH_HEAD].remove(entry.data[BEACH_HEAD])
        _LOGGER.info("removing beachhead %s", entry.data[BEACH_HEAD])


#############

