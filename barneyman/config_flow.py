import copy
import logging
from typing import Any  ##, Optional, TypeVar, cast
from homeassistant import config_entries
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResult
from homeassistant.components import onboarding, zeroconf

# from homeassistant.helpers.discovery import load_platform
# from homeassistant.helpers import config_entry_flow
from homeassistant.config_entries import data_entry_flow
from .barneymanconst import (
    BARNEYMAN_HOST,
    BARNEYMAN_CONFIG_ENTRY,
    BARNEYMAN_DEVICES,
    BARNEYMAN_DOMAIN,
)


# from .helpers import async_do_exists

_LOGGER = logging.getLogger(__name__)

DOMAIN = BARNEYMAN_DOMAIN


@config_entries.HANDLERS.register(BARNEYMAN_CONFIG_ENTRY)
class FlowHandler(config_entries.ConfigFlow):
    """Handle a config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):

        _LOGGER.info("barneyman config_flow __init__ called")
        # """Initialize flow."""
        self._host = None
        self._import_groups = False
        self.zeroconf_info = None

    # this gets called thru "integration - Add (big yellow '+' bottom right!)"
    # or from zeroconf
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        _LOGGER.info("barneyman async_step_user")

        if user_input is None:
            # "integration - Add (big yellow '+' bottom right!)"
            _LOGGER.info("presenting UI")
            return self.async_show_form(
                step_id="parseuser",
                data_schema=vol.Schema({vol.Required(BARNEYMAN_HOST): str}),
            )

        _LOGGER.info(user_input)

        return self.async_abort(reason="unexpected")

    async def async_step_parseuser(self, user_input):

        title = BARNEYMAN_CONFIG_ENTRY

        return self.async_create_entry(title=title, data=user_input)

    # don't know when this is called
    async def async_step_import(self, user_input):
        _LOGGER.critical("barneyman async_step_import %s", user_input)
        return self.async_abort(reason="under_construction")

    # when i'm mdns discovered
    # components.zeroconf.ZeroconfServiceInfo
    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle zeroconf discovery."""

        # ZeroconfServiceInfo(host='192.168.51.144', port=80, hostname='esp_b75c4f.local.',
        # #type='_barneyman._tcp.local.', name='esp_b75c4f._barneyman._tcp.local.',
        # properties={'_raw': {}}, _warning_logged=False)
        _LOGGER.info("barneyman async_step_zeroconf called : %s", discovery_info)

        if discovery_info is None:
            return self.async_abort(reason="cannot_connect")

        # kill the _raw key
        if "_raw" in discovery_info.properties:
            discovery_info.properties.pop("_raw", None)

        _LOGGER.debug(discovery_info.properties)

        # check we're not already doing this in a configflow
        if len(self._async_in_progress()) > 1:
            _LOGGER.warning("barneyman is already being configured")
            return self.async_abort(reason="already_in_progress")

        # and check we haven't already seen this host, and recorded it as a configentry device
        _LOGGER.debug(
            "_async_current_entries called : %s", self._async_current_entries()
        )
        for entry in self._async_current_entries():
            if BARNEYMAN_CONFIG_ENTRY == entry.title:
                # ignore setup from here
                return self.async_abort(reason="single_instance_allowed")

        # we have seen a barneyman device, but my integration is not
        # installed - create a config flow step so we can ask for
        # an auth key and a listening port (data we previously got
        # from the configuration.yaml)
        # breakpoint()

        # lets add our config entry, with our first item in the list
        self.zeroconf_info = {
            BARNEYMAN_DEVICES: [
                {
                    "hostname": discovery_info.hostname,
                    "ip": discovery_info.host,
                    "properties": discovery_info.properties,
                }
            ],
        }

        await self.async_set_unique_id(DOMAIN)

        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        """Confirm the setup."""

        # data = self._get_data()

        if user_input is not None or not onboarding.async_is_onboarded(self.hass):
            return self.async_create_entry(
                title=BARNEYMAN_CONFIG_ENTRY, data=self.zeroconf_info
            )

        return self.async_show_form(step_id="confirm")


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
