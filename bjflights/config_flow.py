from homeassistant import config_entries
import voluptuous as vol
import logging
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers import config_entry_flow


_LOGGER = logging.getLogger(__name__)

DOMAIN = "bjflights"

# removed "zeroconf": ["_bjfLights._tcp.local."], from manifest


@config_entries.HANDLERS.register("bjflights")
class FlowHandler(config_entries.ConfigFlow):
    """Handle a config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):

        _LOGGER.info("bjflights config_flow __init__ called")
        """Initialize flow."""
        self._host = None
        self._import_groups = False

    # this gets called thru "integration - Add (big yellow '+' bottom right!)"
    async def async_step_user(self, user_input):
        _LOGGER.info("bjflights async_step_user ")

        if user_input is None:
            #
            _LOGGER.info("presenting UI")
            return self.async_show_form(
                step_id="user", data_schema=vol.Schema({vol.Required("host"): str})
            )

        _LOGGER.info(user_input)

        return self.async_create_entry(
            title="ESP8266 Lights", data=user_input
        )

    # don't know when this is called
    async def async_step_import(self, user_input):
        _LOGGER.info("bjflights async_step_import ")
        return self.async_abort(reason="under_construction")

    # can't get this called!!
    async def async_step_zeroconf(self, user_input):
        """Handle zeroconf discovery."""
        host = user_input["host"]

        return self.async_abort(reason="under_construction")




# can't get this called!!
async def async_step_discovery(self, user_input):
    """Initialize step from discovery - deprecated?"""
    _LOGGER.info("Discovered device: %s", user_input)
    return self.async_abort(reason="under_construction")




# this get's called with register_discovery_flow

#async def _async_has_devices(hass):
#    # Return if there are devices that can be discovered

#    _LOGGER.info("_async_has_devices has been called")
#    return True

#config_entry_flow.register_discovery_flow(
#    DOMAIN, "barneyman", _async_has_devices, config_entries.CONN_CLASS_LOCAL_PUSH
#)

