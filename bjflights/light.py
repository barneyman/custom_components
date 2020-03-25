import logging

import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.components.light import ATTR_BRIGHTNESS, Light, PLATFORM_SCHEMA
from homeassistant.const import CONF_FILE_PATH
import homeassistant.helpers.config_validation as cv
import homeassistant.util.color as color_util
from homeassistant.helpers.event import async_track_time_interval

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_WHITE_VALUE,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR_TEMP,
    SUPPORT_EFFECT,
    SUPPORT_COLOR,
    SUPPORT_WHITE_VALUE,
    Light,
)

# Home Assistant depends on 3rd party packages for API specific code.
# REQUIREMENTS = ['awesome_lights==1.2.3']

# custom_components.light.bjflights to enable in config.yaml
_LOGGER = logging.getLogger(__name__)

DOMAIN = "bjflights"

CONF_DEVICES = "devices"

# Validation of the user's configuration
# PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
#    vol.Required(CONF_FILE_PATH): cv.string
# })

# from NetDiscovery import MDNSDiscoverable
# class Discoverable(MDNSDiscoverable):
#    """Add support for discovering bjfLights platform devices."""

#    def __init__(self, nd):
#        """Initialize the Cast discovery."""
#        super(Discoverable, self).__init__(nd, '_bjfLights._tcp.local.')


# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({vol.Optional(CONF_DEVICES): cv.ensure_list})


from homeassistant.helpers import discovery

# this gets called if you're a platform under a component
def setup_platform(hass, config, add_devices, discovery_info=None):

    devices = []

    if discovery_info != None:
        configToUse = discovery_info

        _LOGGER.debug("Setting up bjflights via discovery ... %s", configToUse)

        devices = [configToUse["host"]]

    else:
        configToUse = config
        # could be discovery_info

        _LOGGER.debug("Setting up bjflights via config ... %s", configToUse)

        # walk thru the config, adding any hardcoded values
        devices = configToUse.get(CONF_DEVICES, [])

    if devices is not None:
        for each in devices:
            addBJFlight(each, add_devices, hass)
    else:
        _LOGGER.warning("no quoted bjflights")

    def device_discovered(service, info):
        """ Called when a bjflights device has been discovered. """
        _LOGGER.debug("MDNS Discovered a new %s device: %s", service, info["host"])
        # load_platform(hass, 'light', DOMAIN, { "devices":[info["host"]]} )
        addBJFlight(info["host"], add_devices, hass)



# stuff for zero conf
from zeroconf import Zeroconf, ServiceBrowser
r=Zeroconf()

import socket
import time
from datetime import timedelta

class ServiceListener:

    def __init__(self, zc):
        self.host_addresses=[]
        self.zc=zc

    def remove_service(self, zeroconf, type, name):
        _LOGGER.debug("remove_service %s ", name)

    def add_service(self, zeroconf, type, name):
        _LOGGER.debug("add_service name: %s type %s %s", name, type, zeroconf)

        info = self.zc.get_service_info(type, name)
        if info:
            _LOGGER.debug(info)
            _LOGGER.debug("server %s ", info.server)
            address=info.addresses[0]
            _LOGGER.debug("Addr %s",socket.inet_ntoa(address))
            self.host_addresses.append(socket.inet_ntoa(address))

type = "_bjfLights._tcp.local."
listener = ServiceListener(r)
browser = ServiceBrowser(r, type, listener=listener)



# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    _LOGGER.debug("async_setup_entry: %s", config_entry)

    # simply so i have a ref to async_add_devices
    def scanForLights(something):
        _LOGGER.info("scanForLights Called!!!!!")

        time.sleep(2)

        _LOGGER.info("Found %d devices (regularly)",len(listener.host_addresses))

        for host in listener.host_addresses:
            _LOGGER.info("Adding %s", host)
            addBJFlight(host, async_add_devices, hass)


    # Search for devices 
    # removing this causes devices o not be discovered? specuatoive change, enabkibg
    scanForLights(0)

    # then schedule this again for 40 seconds. 
    async_track_time_interval(hass, scanForLights, timedelta(seconds=30))


# this wont compile
#async def async_remove_entry(hass, entry)
#    # just kill my cache
#    _LOGGER.debug("async_remove_entry Called")
#    hass.data[DOMAIN] = {"devicesAdded": []}    



# doesn't appear to be called
async def async_setup(hass, config_entry):
    _LOGGER.debug("async_setup: %s", config_entry)

    # lets hunt for our items




import http.client
import json


def doQuery(hostname, url, returnJson=False, httpmethod="GET"):
    try:
        _LOGGER.info("doQuery %s%s ", hostname, url)
        conn = http.client.HTTPConnection(hostname)
        conn.request(url=url, method=httpmethod)
        r = conn.getresponse()
        if returnJson == True:
            jsonDone = r.read().decode("utf-8")
            r.close()
            conn.close()
            return json.loads(jsonDone)
        r.close()
        conn.close()
        return True
    except Exception as e:
        _LOGGER.error("bjfLights doQuery exception %s %s %s", e, hostname, url)

    return None


import aiohttp
import asyncio


async def async_doQuery(hostname, url, returnJson=False, httpmethod="GET"):
    async def fetch(session, url, returnJson):
        async with session.get(url) as response:
            if returnJson == True:
                return await response.json()
            return response.status

    async with aiohttp.ClientSession() as session:
        try:
            fullUrl = "http://" + hostname + url
            _LOGGER.info("async '%s'", fullUrl)
            response = await fetch(session, fullUrl, returnJson)
            _LOGGER.info(response)
            if returnJson == True:
                return response
            if response == 200:
                return True
            return False
        except Exception as e:
            _LOGGER.error("async_doQuery Exception '%s'", e)
            return None


def addBJFlight(hostname, add_devices, hass):
    # first - query the light
    _LOGGER.info("querying %s", hostname)

    config = doQuery(hostname, "/json/config", True)

    if config != None:
        potential = None
        # depending on the version type (this shouldbe MUCH more robust)
        if config["version"][:8] == "lightRGB":
            potential = bjfESPRGBLight(hostname, config)
        elif config["version"][:5] == "light":
            potential = bjfESPLight(hostname, config)
        else:
            _LOGGER.warning("Unhandled Light Type - ignoring : %s %s", hostname, config)

        if potential != None:
            # make sure it's not already added
            if potential.unique_id not in hass.data[DOMAIN]["devicesAdded"]:
                hass.data[DOMAIN]["devicesAdded"].append(potential.unique_id)
                _LOGGER.info("adding light %s", potential.unique_id)
                # _LOGGER.info(hass.data[DOMAIN])
                if add_devices is not None:
                    add_devices([potential])
                    _LOGGER.info("Entity ID %s", potential.entity_id)
                else:
                    _LOGGER.info("entity_id %s NOT ADDED", potential.entity_id)

            else:
                _LOGGER.warning("Tried to add existing light %s", hostname)

    else:
        _LOGGER.error("Failed to query %s", hostname)


class bjfESPLight(Light):
    def __init__(self, hostname, config):
        self._config = config
        #        self._light = basenodeLight
        self._name = (
            config["friendlyName"] if "friendlyName" in config else config["name"]
        )
        self._state = None
        self._unique_id = hostname

    #        self._brightness = None

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

        doQuery(self._unique_id, "/button?action=on&port=0", False)

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""

        doQuery(self._unique_id, "/button?action=off&port=0", False)

    def update(self):
        """Fetch new state data for this light.

        This is the only method that should fetch new data for Home Assistant.
        """
        self.base_update()

    def base_update(self):
        jsonData = doQuery(self._unique_id, "/json/state", True)

        if jsonData is not None:
            currentState = jsonData["switchState"][0]["state"]
            self._state = True if currentState == 1 else False
            self._name = (
                jsonData["friendlyName"]
                if "friendlyName" in jsonData
                else jsonData["name"]
            )

        return jsonData


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
            doQuery(self._unique_id, query, False)
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

