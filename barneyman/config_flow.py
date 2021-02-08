from homeassistant import config_entries
import voluptuous as vol
import logging
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers import config_entry_flow
from .barneymanconst import BEACH_HEAD, DEVICES_ADDED, AUTH_TOKEN
from .helpers import doExists


_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"


@config_entries.HANDLERS.register("barneyman")
class FlowHandler(config_entries.ConfigFlow):
    """Handle a config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):

        _LOGGER.info("barneyman config_flow __init__ called")
        """Initialize flow."""
        self._host = None
        self._import_groups = False

    # this gets called thru "integration - Add (big yellow '+' bottom right!)"
    async def async_step_user(self, user_input):
        _LOGGER.info("barneyman async_step_user ")

        if user_input is None:
            #
            _LOGGER.info("presenting UI")
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {vol.Optional(BEACH_HEAD): str, vol.Required(AUTH_TOKEN): str,}
                ),
            )

        _LOGGER.info(user_input)

        if BEACH_HEAD in user_input:
            _LOGGER.info("Looking for beachhead")
            title = user_input[BEACH_HEAD]

            # check there IS something there!
            if not doExists(user_input[BEACH_HEAD]):
                _LOGGER.warning("%s beachhead does not exist", user_input[BEACH_HEAD])
                return self.async_abort(reason="nexist")

        else:
            title = "mdns Discovery"
            _LOGGER.info("Looking for mdns")

        return self.async_create_entry(title=title, data=user_input)

    # don't know when this is called
    async def async_step_import(self, user_input):
        _LOGGER.critical("barneyman async_step_import ")
        return self.async_abort(reason="under_construction")

    # when i'm mdns discovered
    async def async_step_zeroconf(self, user_input):
        """Handle zeroconf discovery."""
        host = user_input["host"]

        _LOGGER.critical("barneyman async_step_zeroconf called : {}".format(user_input))

        return self.async_abort(reason="under_construction")


# can't get this called!!
async def async_step_discovery(self, user_input):
    """Initialize step from discovery - deprecated?"""
    _LOGGER.info("Discovered device: %s", user_input)
    return self.async_abort(reason="under_construction")


# this get's called with register_discovery_flow

# async def _async_has_devices(hass):
#    # Return if there are devices that can be discovered

#    _LOGGER.info("_async_has_devices has been called")
#    return True

# config_entry_flow.register_discovery_flow(
#    DOMAIN, "barneyman", _async_has_devices, config_entries.CONN_CLASS_LOCAL_PUSH
# )

