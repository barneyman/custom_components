import logging
import json
import asyncio
from datetime import timedelta
import voluptuous as vol

# Import the device class from the component that you want to support

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

from homeassistant.core import callback
from homeassistant.components.light import (
    PLATFORM_SCHEMA,
    LightEntity,
)


from .barneymanconst import (
    BARNEYMAN_HOST,
    BARNEYMAN_DEVICES_SEEN,
    DEVICES_LIGHT,
    BARNEYMAN_DOMAIN,
    SIGNAL_BARNEYMAN_DISCOVERED,
    BARNEYMAN_BROWSER,
)
from .helpers import (
    BJFDeviceInfo,
    BJFRestData,
    do_post,
    async_do_query,
    BJFFinder,
    chopLocal,
)

from .listener import BJFListener


# Home Assistant depends on 3rd party packages for API specific code.
# REQUIREMENTS = ['awesome_lights==1.2.3']

# custom_components.light.barneyman to enable in config.yaml
_LOGGER = logging.getLogger(__name__)

DOMAIN = BARNEYMAN_DOMAIN

CONF_DEVICES = "devices"


# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({vol.Optional(CONF_DEVICES): cv.ensure_list})


# this gets called if you're a platform under a component
def setup_platform(hass, config, add_devices, discovery_info=None):

    devices = []

    if discovery_info != None:
        configToUse = discovery_info

        _LOGGER.debug("Setting up barneyman via discovery ... %s", configToUse)

        devices = [configToUse[BARNEYMAN_HOST]]

    else:
        configToUse = config
        # could be discovery_info

        _LOGGER.debug("Setting up barneyman via config ... %s", configToUse)

        # walk thru the config, adding any hardcoded values
        devices = configToUse.get(CONF_DEVICES, [])

    if devices is not None:
        for each in devices:
            addBJFlight(each, add_devices, hass)
    else:
        _LOGGER.warning("no quoted barneyman")

    # def device_discovered(service, info):
    #     """Called when a bjflights device has been discovered."""
    #     _LOGGER.debug(
    #         "MDNS Discovered a new %s device: %s", service, info[BARNEYMAN_HOST]
    #     )
    #     addBJFlight(info[BARNEYMAN_HOST], add_devices, hass)


async def async_remove_entry(hass, entry):
    # pylint: disable=unused-argument

    # """Handle removal of an entry."""
    _LOGGER.info("LIGHT async_remove_entry")


# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    # pylint: disable=unused-argument
    _LOGGER.debug("LIGHT async_setup_entry: %s", config_entry.data)

    async def async_setupDevice(z):
        _LOGGER.info("async_setupDevice for Light")
        await addBJFlight(
            z,
            async_add_devices,
            hass,
        )

    # listen for 'device found'
    async_dispatcher_connect(hass, SIGNAL_BARNEYMAN_DISCOVERED, async_setupDevice)

    # go thru what's already bean found
    if hass.data[DOMAIN][BARNEYMAN_BROWSER] is not None:
        for each in hass.data[DOMAIN][BARNEYMAN_BROWSER].getHosts():
            await async_setupDevice(each)

    # TODO
    return True


# doesn't appear to be called
async def async_setup(hass, config_entry):
    # pylint: disable=unused-argument
    _LOGGER.debug("LIGHT async_setup: %s", config_entry)

    # lets hunt for our items


wip = []

# TODO - find all the lights, and inc the ordinal
async def addBJFlight(data, add_devices, hass):

    potentials = []

    hostname = chopLocal(data.server)
    # TODO - i've got - and _ mismatches between host names and mdns names in my esp code
    # so fix that, then remove this
    hostname = ".".join(str(c) for c in data.addresses[0])
    # remove .local.
    host = hostname

    if hostname in wip:
        _LOGGER.debug("already seen in WIP %s", hostname)
        return

    if hostname in hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN + DEVICES_LIGHT]:
        _LOGGER.debug("already seen %s", hostname)
        return

    # optimisation, if they have a platforms property, bail early on that
    if b"platforms" in data.properties:
        platforms = data.properties[b"platforms"].decode("utf8")
        _LOGGER.debug("device has platforms %s", platforms)
        if DEVICES_LIGHT not in platforms.split(","):
            _LOGGER.info("optimised config fetch out")
            return

    # first - query the light
    _LOGGER.info("querying %s @ %s", hostname, host)
    wip.append(hostname)

    config = await async_do_query(host, "/json/config", True)

    coord = None

    if config is not None:

        mac = config["mac"]

        friendly_name = (
            config["friendlyName"] if "friendlyName" in config else config["name"]
        )

        rest = BJFRestData(hass, hostname, "GET", None, None, None)

        # and add a datacoordinator
        coord = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=hostname + "_DUC",
            update_method=rest.async_bjfupdate,
            # they shout back, so update not so often
            update_interval=timedelta(seconds=60),
        )

        if "switchConfig" in config:
            for switchConfig in config["switchConfig"]:

                # switch may have the ability to prod us
                transport = None
                if "impl" in switchConfig:
                    transport = switchConfig["impl"]

                potential = bjfESPLight(
                    hostname,
                    friendly_name,
                    coord,
                    mac,
                    config,
                    switchConfig["switch"],
                    rest,
                    transport,
                    hass,
                )

                # does this already exist?

                _LOGGER.info("adding light %s", potential.unique_id)
                potentials.append(potential)

                hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN + DEVICES_LIGHT].append(
                    hostname
                )

        # await coord.async_config_entry_first_refresh()

    else:
        _LOGGER.error("Failed to query %s at onboarding - device not added", hostname)
        if hostname in hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN + DEVICES_LIGHT]:
            hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN + DEVICES_LIGHT].remove(hostname)

    wip.remove(hostname)

    if add_devices is not None:
        add_devices(potentials)
        if coord is not None:
            await coord.async_config_entry_first_refresh()

        return True

    return False


class bjfESPLight(CoordinatorEntity, BJFDeviceInfo, BJFListener, LightEntity):
    def __init__(
        self, hostname, friendlyName, coord, mac, config, ordinal, rest, transport, hass
    ):
        BJFDeviceInfo.__init__(self, config, mac)
        BJFListener.__init__(self, transport, hass, hostname)
        CoordinatorEntity.__init__(self, coord)

        self._config = config

        self._name = friendlyName
        self._state = None
        self._unique_id = mac + "_switch_" + str(ordinal)
        self._hostname = hostname
        self._ordinal = ordinal
        self._rest = rest
        self._hass = hass
        self._is_on = False

        self._finder = BJFFinder(hass, hostname)

        # and subscribe for data updates
        self.async_on_remove(coord.async_add_listener(self.parseData))

    def handle_incoming_packet(self, data):

        _LOGGER.warning("Publish from %s", self._hostname)

        payload = json.loads(data.decode("utf-8"))

        _LOGGER.debug(payload)
        self._is_on = payload["state"]
        _LOGGER.warning("About to set %s state to %s", self.entity_id, self.state)
        self._hass.states.set(self.entity_id, self.state)

    @property
    def unique_id(self):
        """Return unique ID for light."""
        return self._unique_id

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    def turn_on(self, **kwargs):
        """Instruct the light to turn on.

        You can skip the brightness part if your light does not support
        brightness control.
        """
        # self._light.brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        # self._light.turn_on()

        do_post(
            self._finder.get_ip_address(),
            "/button?action=on&port=" + str(self._ordinal),
        )
        asyncio.run_coroutine_threadsafe(
            self.coordinator.async_refresh(), self.hass.loop
        ).result()

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""

        do_post(
            self._finder.get_ip_address(),
            "/button?action=off&port=" + str(self._ordinal),
        )
        # and reset the cache
        asyncio.run_coroutine_threadsafe(
            self.coordinator.async_refresh(), self.hass.loop
        ).result()

    @callback
    def parseData(self):

        _LOGGER.info("light %s parseData has been called", (self._hostname))

        if self._hass is not None:
            self._hass.add_job(self.subscribe, "light")

        if self._rest.data is None:
            # will be reported by the rest sensor so redundant as error
            _LOGGER.debug("no rest data from %s", self._name)
            return None

        jsonData = json.loads(self._rest.data)

        _LOGGER.debug(jsonData)

        if jsonData is not None:

            try:

                self._name = (
                    jsonData["friendlyName"]
                    if "friendlyName" in jsonData
                    else jsonData["name"]
                )

                currentState = jsonData["switchState"][self._ordinal]["state"]
                self._state = True if currentState == 1 else False

            except Exception as e:
                _LOGGER.error("Exception in light.base_update %s", e)

        return jsonData


#################################
### not migrated to barneyman yet
#################################


# LIGHT_EFFECT_LIST = ["rainbow", "none"]


# class bjfESPRGBLight(bjfESPLight):
#     def __init__(self, hostname, config):
#         bjfESPLight.__init__(self, hostname, config)
#         self._hs_color = None
#         self._brightness = 20
#         self._effect_list = LIGHT_EFFECT_LIST
#         self._effect = "none"

#     def update(self):
#         """Fetch new state data for this light.

#         This is the only method that should fetch new data for Home Assistant.
#         """
#         jsonData = self.base_update()

#         lastRGB = jsonData["switchState"][0]["lastRGB"]
#         fullhsv = color_util.color_RGB_to_hsv(
#             (lastRGB >> 16) & 0xFF, (lastRGB >> 8) & 0xFF, lastRGB & 0xFF
#         )
#         self._hs_color = (fullhsv[0], fullhsv[1])
#         self._brightness = (255 / 100) * fullhsv[2]

#     @property
#     def hs_color(self) -> tuple:
#         """Return the hs color value."""
#         return self._hs_color

#     @property
#     def brightness(self):
#         """Return the brightness of the light.

#         This method is optional. Removing it indicates to Home Assistant
#         that brightness is not supported for this light.
#         """
#         return self._brightness

#     @property
#     def supported_features(self) -> int:
#         """Flag supported features."""
#         return SUPPORT_COLOR | SUPPORT_BRIGHTNESS | SUPPORT_EFFECT

#     def turn_on(self, **kwargs):
#         """Instruct the light to turn on.

#         You can skip the brightness part if your light does not support
#         brightness control.
#         """

#         if ATTR_BRIGHTNESS in kwargs:
#             self._brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
#         # self._light.turn_on()

#         if ATTR_HS_COLOR in kwargs:
#             self._hs_color = kwargs[ATTR_HS_COLOR]

#             # work out what the rgb val is
#         rgb = color_util.color_hsv_to_RGB(
#             self._hs_color[0], self._hs_color[1], (self._brightness / 255) * 100
#         )

#         if ATTR_EFFECT in kwargs:
#             self._effect = kwargs[ATTR_EFFECT]

#         if "action" in kwargs:
#             bjfESPLight.turn_on()
#         else:
#             query = "/button?action=on&r={r}&g={g}&b={b}&effect={effect}".format(
#                 r=rgb[0], g=rgb[1], b=rgb[2], effect=self._effect
#             )
#             _LOGGER.info("querying %s", query)
#             do_post(self._hostname, query)
#         # else:
#         #    self._light.command('on')

#     @property
#     def effect_list(self) -> list:
#         """Return the list of supported effects."""
#         return self._effect_list

#     @property
#     def effect(self) -> str:
#         """Return the current effect."""
#         return self._effect
