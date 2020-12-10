import logging
import json
import voluptuous as vol

# Import the device class from the component that you want to support

from datetime import datetime, timedelta
from homeassistant.const import CONF_FILE_PATH
import homeassistant.helpers.config_validation as cv
import homeassistant.util.color as color_util
from homeassistant.helpers.event import async_track_time_interval
from .barneymanconst import (
    BEACH_HEAD,
    DEVICES_ADDED,
    DISCOVERY_ROOT,
    DEVICES_FOUND,
    DEVICES_FOUND_LIGHT,AUTH_TOKEN

)
from .helpers import doQuery, BJFDeviceInfo, BJFRestData, BJFListener, doPost

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_WHITE_VALUE,
    PLATFORM_SCHEMA,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR_TEMP,
    SUPPORT_EFFECT,
    SUPPORT_COLOR,
    SUPPORT_WHITE_VALUE,
    LightEntity,
)

# Home Assistant depends on 3rd party packages for API specific code.
# REQUIREMENTS = ['awesome_lights==1.2.3']

# custom_components.light.barneyman to enable in config.yaml
_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"

CONF_DEVICES = "devices"


# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({vol.Optional(CONF_DEVICES): cv.ensure_list})


from homeassistant.helpers import discovery

# this gets called if you're a platform under a component
def setup_platform(hass, config, add_devices, discovery_info=None):

    devices = []

    if discovery_info != None:
        configToUse = discovery_info

        _LOGGER.debug("Setting up barneyman via discovery ... %s", configToUse)

        devices = [configToUse["host"]]

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

    def device_discovered(service, info):
        """ Called when a bjflights device has been discovered. """
        _LOGGER.debug("MDNS Discovered a new %s device: %s", service, info["host"])
        # load_platform(hass, 'light', DOMAIN, { "devices":[info["host"]]} )
        addBJFlight(info["host"], add_devices, hass)


async def async_remove_entry(hass, entry):
    """Handle removal of an entry."""
    _LOGGER.info("LIGHT async_remove_entry")


# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    _LOGGER.debug("LIGHT async_setup_entry: %s", config_entry)

    # simply so i have a ref to async_add_devices
    def addFoundLights(self):
        _LOGGER.info("addFoundLights Called!!!!!")

        workingList = hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
            DEVICES_FOUND_LIGHT
        ].copy()

        if len(workingList)==0:
            _LOGGER.info("Nothing found")
            return


        hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][DEVICES_FOUND_LIGHT] = []

        for newhost in workingList:
            if not addBJFlight(newhost, async_add_devices, hass):
                hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][DEVICES_FOUND_LIGHT].append(newhost)
                _LOGGER.info("{} re-added to add list}".format(newhost))


    # Search for devices
    # removing this causes devices o not be discovered? specuatoive change, enabkibg
    #await hass.async_add_executor_job(addFoundLights(0))
    addFoundLights(0)


    # then schedule this again for 40 seconds.
    async_track_time_interval(hass, addFoundLights, timedelta(seconds=30))


# doesn't appear to be called
async def async_setup(hass, config_entry):
    _LOGGER.debug("LIGHT async_setup: %s", config_entry)

    # lets hunt for our items


# TODO - find all the lights, and inc the ordinal
def addBJFlight(hostname, add_devices, hass):
    # first - query the light
    _LOGGER.info("querying %s", hostname)

    config = doQuery(hostname, "/json/config", True)

    if config != None:

        potentials = []
        mac = config["mac"]

        url = "http://" + config["ip"] + "/json/state"
        rest = BJFRestData(hass, "GET", url, None, None, None, httptimeout=10)

        for switchConfig in config["switchConfig"]:

            # switch may have the ability to prod us
            transport = None
            if "impl" in switchConfig:
                transport = switchConfig["impl"]

            potential = bjfESPLight(
                hostname, mac, config, switchConfig["switch"], rest, transport, hass
            )

            # does this already exist?

            _LOGGER.info("adding light %s", potential.unique_id)
            potentials.append(potential)

        if add_devices is not None:
            add_devices(potentials)

            return True

    else:
        _LOGGER.error("Failed to query %s at onboarding", hostname)

    return False


class bjfESPLight(BJFDeviceInfo, BJFListener, LightEntity):
    def __init__(self, hostname, mac, config, ordinal, rest, transport, hass):
        BJFDeviceInfo.__init__(self, config)
        BJFListener.__init__(self, transport, hass)

        self._config = config

        self._name = (
            config["friendlyName"] if "friendlyName" in config else config["name"]
        )
        self._state = None
        self._unique_id = mac + "_switch_" + str(ordinal)
        self._mac = mac
        self._hostname = hostname
        self._ordinal = ordinal
        self._rest = rest
        self._hass = hass

        # and get my state
        self.base_update()

    #        self._brightness = None

    def HandleIncomingPacket(self, data):
        payload = json.loads(data.decode("utf-8"))

        _LOGGER.debug(payload)
        self._is_on = payload["state"]
        _LOGGER.debug("About to set %s state to %s", self.entity_id, self.state)
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

    # https://developers.home-assistant.io/docs/en/asyncio_index.html

    # async def async_turn_on(self, **kwargs):
    #    async_doQuery(self._unique_id, "/button?action=on&port=0", False)
    # async def async_turn_off(self, **kwargs):
    #    async_doQuery(self._unique_id, "/button?action=off&port=0", False)
    # async def async_update(self):
    #    jsonData=await async_doQuery(self._unique_id, "/json/state", True)
    #    if jsonData is not None:
    #        currentState=jsonData["switchState"][0]["state"]
    #        self._state=True if currentState==1 else False

    def turn_on(self, **kwargs):
        """Instruct the light to turn on.

        You can skip the brightness part if your light does not support
        brightness control.
        """
        # self._light.brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        # self._light.turn_on()

        doPost(self._hostname, "/button?action=on&port=" + str(self._ordinal))
        self._rest.resetCache()

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""

        doPost(self._hostname, "/button?action=off&port=" + str(self._ordinal))
        # and reset the cache
        self._rest.resetCache()

    def update(self):
        """Fetch new state data for this light.

        This is the only method that should fetch new data for Home Assistant.
        """

        self.subscribe("switch")

        _LOGGER.info("doing update")
        self.base_update()

    def base_update(self):

        self._rest.update()

        if self._rest.data is None:
            _LOGGER.error("no rest data from %s", self._unique_id)
            return None

        jsonData = json.loads(self._rest.data)

        _LOGGER.info(jsonData)

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


LIGHT_EFFECT_LIST = ["rainbow", "none"]


class bjfESPRGBLight(bjfESPLight):
    def __init__(self, hostname, config):
        bjfESPLight.__init__(self, hostname, config)
        self._hs_color = None
        self._brightness = 20
        self._effect_list = LIGHT_EFFECT_LIST
        self._effect = "none"

    def update(self):
        """Fetch new state data for this light.

        This is the only method that should fetch new data for Home Assistant.
        """
        jsonData = self.base_update()

        lastRGB = jsonData["switchState"][0]["lastRGB"]
        fullhsv = color_util.color_RGB_to_hsv(
            (lastRGB >> 16) & 0xFF, (lastRGB >> 8) & 0xFF, lastRGB & 0xFF
        )
        self._hs_color = (fullhsv[0], fullhsv[1])
        self._brightness = (255 / 100) * fullhsv[2]

    @property
    def hs_color(self) -> tuple:
        """Return the hs color value."""
        return self._hs_color

    @property
    def brightness(self):
        """Return the brightness of the light.

        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        return self._brightness

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_COLOR | SUPPORT_BRIGHTNESS | SUPPORT_EFFECT

    def turn_on(self, **kwargs):
        """Instruct the light to turn on.

        You can skip the brightness part if your light does not support
        brightness control.
        """

        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        # self._light.turn_on()

        if ATTR_HS_COLOR in kwargs:
            self._hs_color = kwargs[ATTR_HS_COLOR]

            # work out what the rgb val is
        rgb = color_util.color_hsv_to_RGB(
            self._hs_color[0], self._hs_color[1], (self._brightness / 255) * 100
        )

        if ATTR_EFFECT in kwargs:
            self._effect = kwargs[ATTR_EFFECT]

        if "action" in kwargs:
            bjfESPLight.turn_on()
        else:
            query = "/button?action=on&r={r}&g={g}&b={b}&effect={effect}".format(
                r=rgb[0], g=rgb[1], b=rgb[2], effect=self._effect
            )
            _LOGGER.info("querying %s", query)
            doPost(self._hostname, query)
        # else:
        #    self._light.command('on')

    # async def async_turn_on(self, **kwargs):
    #    """Instruct the light to turn on.

    #    You can skip the brightness part if your light does not support
    #    brightness control.
    #    """

    #    if ATTR_BRIGHTNESS in kwargs:
    #        self._brightness = kwargs.get(ATTR_BRIGHTNESS,255)
    #    #self._light.turn_on()

    #    if ATTR_HS_COLOR in kwargs:
    #        self._hs_color=kwargs[ATTR_HS_COLOR]

    #    _LOGGER.info(kwargs)
    #    _LOGGER.info(self._hs_color)
    #    _LOGGER.info(self._brightness)

    #        # work out what the rgb val is
    #    rgb=color_util.color_hsv_to_RGB(self._hs_color[0],self._hs_color[1], (self._brightness/255)*100)

    #    if ATTR_EFFECT in kwargs:
    #        self._effect=kwargs[ATTR_EFFECT]

    #    if 'action' in kwargs:
    #        bjfESPLight.turn_on();
    #    else:
    #        query="/button?action=on&r={r}&g={g}&b={b}&effect={effect}".format(r=rgb[0], g=rgb[1], b=rgb[2], effect=self._effect)
    #        _LOGGER.info("querying %s",query)
    #        async_doQuery(self._unique_id, query, False)

    @property
    def effect_list(self) -> list:
        """Return the list of supported effects."""
        return self._effect_list

    @property
    def effect(self) -> str:
        """Return the current effect."""
        return self._effect

