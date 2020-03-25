"""The example sensor integration."""

import logging
import voluptuous as vol
from homeassistant.helpers.discovery import load_platform


_LOGGER = logging.getLogger(__name__)

DOMAIN = "bjflights"

import homeassistant.helpers.config_validation as cv


async def async_setup(hass, baseConfig):
    """Set up is called when Home Assistant is loading our component."""

    _LOGGER.info("bjflights async_setup called")

    # create my 'i've created these' array
    hass.data[DOMAIN] = {"devicesAdded": []}
    _LOGGER.info(hass.data[DOMAIN])

    return True

    """Setup the BJF Light platform."""

    load_platform(hass, "light", DOMAIN, {"host": "sonoff_68ecd4."}, baseConfig)

    return True


# called after created by configflow - ADDITIONAL to setup, above
async def async_setup_entry(hass, entry):
    _LOGGER.info("bjflights async_setup_entry called %s", entry)




    # then forward this to all the platforms
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "light")
    )


    return True
