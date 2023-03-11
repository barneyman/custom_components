"""The example sensor integration."""

import logging
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components import zeroconf
from .barneymanconst import (
    BARNEYMAN_DEVICES,
    DEVICES_LIGHT,
    DEVICES_SENSOR,
    DEVICES_CAMERA,
    BARNEYMAN_DOMAIN,
    BARNEYMAN_BROWSER,
    BARNEYMAN_USER_ID,
)

import asyncio

from datetime import timedelta

from .discovery import barneymanBrowser
from .auth import async_prepareUserAuth

_LOGGER = logging.getLogger(__name__)

DOMAIN = BARNEYMAN_DOMAIN

import homeassistant.helpers.config_validation as cv


# async handlers


async def async_setup(hass, baseConfig):
    """Set up is called when Home Assistant is loading our component."""

    _LOGGER.debug("barneyman async_setup called %s", baseConfig)
    return True


# called after created by configflow - ADDITIONAL to setup, above
async def async_setup_entry(hass, entry):
    _LOGGER.info("barneyman async_setup_entry called %s %s", entry.title, entry.data)

    # clean up my legacy config data
    if BARNEYMAN_DEVICES in entry.data:
        _LOGGER.warning(
            "Please remove the Devices array from the barneyman config_entry.data"
        )

    llat_lifetime = timedelta(minutes=60)


    await async_prepareUserAuth(hass, entry, llat_lifetime)

    async def async_remove_llat(offset_from_now: timedelta):
        while True:
            _LOGGER.info(
                "async_remove_llat sleeping for %ld secs", offset_from_now.total_seconds()
            )
            await asyncio.sleep(offset_from_now.total_seconds())
            _LOGGER.debug("async_remove_llat awake")
            # and around again
            await async_prepareUserAuth(hass, entry,llat_lifetime)

    # then start a background task that will update the auth token
    entry.async_create_background_task(hass,async_remove_llat(llat_lifetime),"LLAT refresh")

    # now set up my discovery class
    # barneymanDiscovery.set_zeroconf(await zeroconf.async_get_instance(hass))
    hass.data[BARNEYMAN_DOMAIN][BARNEYMAN_BROWSER] = barneymanBrowser(
        hass, await zeroconf.async_get_instance(hass)
    )

    # then forward this to all the platforms
    _LOGGER.info("forwarding to platforms %s %s", entry.title, entry.data)

    # use the current stored config, some things may not respond in time
    await hass.config_entries.async_forward_entry_setups(
        entry, [DEVICES_LIGHT, DEVICES_SENSOR, DEVICES_CAMERA]
    )
    return True


async def async_remove_entry(hass, entry):
    # pylint: disable=unused-argument
    """Handle removal of an entry."""
    _LOGGER.info("async_remove_entry")

    my_user_id = entry.data.get(BARNEYMAN_USER_ID, None)
    if my_user_id is not None:
        my_user = await hass.auth.async_get_user(my_user_id)
        await hass.auth.async_remove_user(my_user)

        _LOGGER.info("removed  %s found", my_user.name)


#############
