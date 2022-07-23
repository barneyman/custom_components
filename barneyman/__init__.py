"""The example sensor integration."""

import logging
import voluptuous as vol
import json
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components import zeroconf
from datetime import datetime, timedelta
from .barneymanconst import (
    BARNEYMAN_DEVICES,
    DEVICES_LIGHT,
    DEVICES_SENSOR,
    DEVICES_CAMERA,
    LISTENING_PORT,
    AUTH_TOKEN,
    BARNEYMAN_DEVICES_SEEN,
    BARNEYMAN_DOMAIN,
    BARNEYMAN_BROWSER,
)

from .discovery import barneymanBrowser

_LOGGER = logging.getLogger(__name__)

DOMAIN = BARNEYMAN_DOMAIN

import homeassistant.helpers.config_validation as cv


# async handlers


async def async_setup(hass, baseConfig):
    """Set up is called when Home Assistant is loading our component."""

    _LOGGER.debug("barneyman async_setup called %s", baseConfig)

    myAuthToken = None
    # only used if we're not using rest (which we are)
    listeningPort = 49152
    if DOMAIN in baseConfig:
        if AUTH_TOKEN in baseConfig[DOMAIN]:
            myAuthToken = baseConfig[DOMAIN][AUTH_TOKEN]
            _LOGGER.debug("barneyman authtoken found")
        if LISTENING_PORT in baseConfig[DOMAIN]:
            listeningPort = baseConfig[DOMAIN][LISTENING_PORT]
            _LOGGER.debug("barneyman port %d", listeningPort)

    # create my 'i've created these' array
    hass.data[DOMAIN] = {
        AUTH_TOKEN: myAuthToken,
        LISTENING_PORT: listeningPort,
        BARNEYMAN_DEVICES_SEEN + DEVICES_LIGHT: [],
        BARNEYMAN_DEVICES_SEEN + DEVICES_SENSOR: [],
        BARNEYMAN_DEVICES_SEEN + DEVICES_CAMERA: [],
    }

    return True


# called after created by configflow - ADDITIONAL to setup, above
async def async_setup_entry(hass, entry):
    _LOGGER.info("barneyman async_setup_entry called %s %s", entry.title, entry.data)

    # this is in configuration yaml
    if AUTH_TOKEN in entry.data:
        hass.data[DOMAIN][AUTH_TOKEN] = entry.data[AUTH_TOKEN]
        _LOGGER.info("barneyman authtoken found")

    # clean up my legacy config data
    if BARNEYMAN_DEVICES in entry.data:
        _LOGGER.warning(
            "Please remove the Devices array from the barneyman config_entry.data"
        )

    # now set up my discovery class
    # barneymanDiscovery.set_zeroconf(await zeroconf.async_get_instance(hass))
    hass.data[BARNEYMAN_DOMAIN][BARNEYMAN_BROWSER] = barneymanBrowser(
        hass, await zeroconf.async_get_instance(hass)
    )

    # then forward this to all the platforms
    _LOGGER.info("forwarding to platforms %s %s", entry.title, entry.data)

    # use the current stored config, some things may not respond in time
    hass.config_entries.async_setup_platforms(
        entry, [DEVICES_LIGHT, DEVICES_SENSOR, DEVICES_CAMERA]
    )

    return True


async def async_remove_entry(hass, entry):
    # pylint: disable=unused-argument
    """Handle removal of an entry."""
    _LOGGER.info("async_remove_entry")

    # TODO - this should remove all the entities?


#############
