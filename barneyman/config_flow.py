from homeassistant import config_entries
import voluptuous as vol
import logging
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers import config_entry_flow
from .barneymanconst import BARNEYMAN_HOST, BARNEYMAN_CONFIG_ENTRY, BARNEYMAN_DEVICES
from .helpers import async_doExists


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
    # or from zeroconf
    async def async_step_user(self, user_input):
        _LOGGER.info("barneyman async_step_user ")

        if user_input is None:
            # "integration - Add (big yellow '+' bottom right!)"
            _LOGGER.info("presenting UI")
            return self.async_show_form(
                step_id="parseuser",
                data_schema=vol.Schema(
                    {vol.Required(BARNEYMAN_HOST): str}
                ),
            )

        _LOGGER.info(user_input)

        return self.async_abort(reason="unexpected")

    async def async_step_parseuser(self, user_input):

        title = BARNEYMAN_CONFIG_ENTRY

        return self.async_create_entry(title=title, data=user_input)



    # don't know when this is called
    async def async_step_import(self, user_input):
        _LOGGER.critical("barneyman async_step_import ")
        return self.async_abort(reason="under_construction")

    # when i'm mdns discovered
    async def async_step_zeroconf(self, disco_info):
        """Handle zeroconf discovery."""

        _LOGGER.warning("barneyman async_step_zeroconf called : {}".format(disco_info))

        if disco_info is None:
            return self.async_abort(reason="cannot_connect")

        # TODO fix this check
        # check we're not already doing this in a configflow
        # if any(
        #     BARNEYMAN_CONFIG_ENTRY == flow["context"].get(BARNEYMAN_HOST)
        #     for flow in self._async_in_progress()
        # ):
        #     _LOGGER.info("host {} is already being configured".format(disco_info[BARNEYMAN_HOST]))
        #     return self.async_abort(reason="already_in_progress")

        # and check we haven't already seen this host
        _LOGGER.debug("_async_current_entries called : {}".format(self._async_current_entries()))
        for entry in self._async_current_entries():
            if BARNEYMAN_CONFIG_ENTRY == entry.title:
                # it's already there - have we seen this host before?
                if not any(
                    disco_info[BARNEYMAN_HOST] == host 
                    for host in entry.data[BARNEYMAN_DEVICES]
                ):
                    # add it to the list
                    newdata=entry.data[BARNEYMAN_DEVICES]
                    newdata.append(disco_info[BARNEYMAN_HOST])
                    _LOGGER.info("updating config entry {}".format(entry.title))
                    _LOGGER.debug("debug: {}".format(entry))
                    newentrydata={ BARNEYMAN_DEVICES : newdata }
                    # force a change - the 'has anything changed' logic is not great with data
                    entry.data=None
                    heard = self.hass.config_entries.async_update_entry(entry, data=newentrydata )
                    if not heard:
                        _LOGGER.error("config change for {} unheard".format(newentrydata))
                else:
                    _LOGGER.info("host {} has already been added".format(disco_info[BARNEYMAN_HOST]))

                return self.async_abort(reason="already_configured")


        # lets add our config entry, with our first item in the list
        self.zeroconf_info={
            BARNEYMAN_DEVICES: [ disco_info[BARNEYMAN_HOST] ],
        }

        return await self.async_step_parseuser(self.zeroconf_info)

        





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

