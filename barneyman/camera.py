import logging
import json
import asyncio
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp
import async_timeout
import voluptuous as vol
from datetime import datetime, timedelta
from homeassistant.helpers.template import Template
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.camera import Camera
from .barneymanconst import (
    BARNEYMAN_DEVICES,
    BARNEYMAN_DEVICES_SEEN,
    DEVICES_CAMERA

)
from .helpers import async_doQuery, doQuery, doPost, BJFDeviceInfo, BJFListener

_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"

# called from entity_platform.py line 129
# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    _LOGGER.debug("CAMERA async_setup_entry: %s", config_entry.data)

    async def async_update_options(hass, entry) -> None:

        # reload me
        await async_scan_for(config_entry)

    async def async_scan_for(config_entry):

        addResult = await addBJFcamera(config_entry.data, async_add_devices, hass)

        if addResult!=True:
            _LOGGER.error("CAMERA async_setup_entry: %s FAILED", config_entry.entry_id)

        return addResult

    # add a listener to the config entry
    config_entry.add_update_listener(async_update_options)

    # scan for lights
    addResult = await async_scan_for(config_entry)


    if addResult!=True:
        _LOGGER.error("CAMERA async_setup_entry: %s FAILED", config_entry.entry_id)

    return addResult

wip=[]
async def addBJFcamera(data, add_devices, hass):
    _LOGGER.info("addBJFcamera querying %s", data)

    camerasToAdd = []

    if BARNEYMAN_DEVICES not in data:
        return False

    for device in data[BARNEYMAN_DEVICES]:
        
        hostname=device["hostname"]
        host=device["ip"]

        if hostname in wip:
            _LOGGER.debug("already seen in WIP %s", hostname)
            continue

        if hostname in hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN]:
            continue

        # optimisation, if they have a pltforms property, bail early on that
        if "properties" in device and "platforms" in device["properties"]:
            _LOGGER.info("device has platforms %s", device["properties"]["platforms"])
            if DEVICES_CAMERA not in device["properties"]["platforms"].split(","):
                _LOGGER.info("optimised config fetch out")
                continue


        wip.append(hostname)


        config = await async_doQuery(host, "/json/config", True)

        if config != None:

            mac = config["mac"]

            # built early, in case it's shared
            url = "http://" + config["ip"] + "/camera?cam="

            friendlyName = (
                config["friendlyName"] if "friendlyName" in config else config["name"]
            )


            # add a bunch of cameras
            if "cameraConfig" in config:
                for eachCamera in config["cameraConfig"]:

                    potential = None

                    _LOGGER.info("Potential BJFRestSensor")

                    camNumber=eachCamera["camera"]

                    potential = BJFEspCamera(
                        hass,
                        mac,
                        hostname,
                        # entity name - +1 for the cosmetic name - that's confusing!
                        friendlyName+" "+eachCamera["name"] + " " + str(camNumber+1),
                        url+str(camNumber),
                        camNumber,
                        config,
                    )

                    if potential is not None:
                        _LOGGER.info("Adding camera %s", potential._unique_id)
                        camerasToAdd.append(potential)
        else:
            _LOGGER.error("Failed to query %s at onboarding - device not added", hostname)
            if hostname in data[BARNEYMAN_DEVICES]:
                data[BARNEYMAN_DEVICES].remove(hostname)


        wip.remove(hostname)

    if add_devices is not None:
        add_devices(camerasToAdd)
        return True

    
    return False


# in py, vtable priority is left to right
class BJFEspCamera(BJFDeviceInfo, Camera):
    def __init__(
        self,
        hass,
        mac,
        hostname,
        name,
        camUrl,
        camNumber,
        config,
    ):
        Camera.__init__(
            self
        )
        BJFDeviceInfo.__init__(self, config)

        self._unique_id = mac + "_camera_" + str(camNumber)
        self._hostname = hostname
        self._mac = mac
        self._name=name
        self._frame_interval=5
        self._camUrl=camUrl
        self._last_image=None
        self._incommserror=False

        self._supported_features = 0

    @property
    def unique_id(self):
        """Return unique ID for sensor."""
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def brand(self) -> str:
        """Return the camera brand."""
        return "AI Thinker"

    @property
    def model(self) -> str:
        """Return the camera model."""
        return "ESP32-CAM"



    @property
    def supported_features(self):
        """Return supported features for this camera."""
        return self._supported_features

    @property
    def frame_interval(self):
        """Return the interval between frames of the mjpeg stream."""
        return self._frame_interval

    def camera_image(self):
        """Return bytes of camera image."""
        return asyncio.run_coroutine_threadsafe(
            self.async_camera_image(), self.hass.loop
        ).result()

    async def async_camera_image(self, width = None, height = None):
        """Return a still image response from the camera."""

        # if self._camUrl == self._last_url and self._limit_refetch:
        #     return self._last_image

        try:
            websession = async_get_clientsession(
                self.hass, verify_ssl=False
            )
            with async_timeout.timeout(10):
                response = await websession.get(self._camUrl)
            self._last_image = await response.read()
            if self._incommserror:
                _LOGGER.error("%s no longer in comms error", self._name)
                self._incommserror=False
        except asyncio.TimeoutError:
            if not self._incommserror:
                _LOGGER.error("Timeout getting image from: %s", self._name)
                self._incommserror=True
            return self._last_image
        except aiohttp.ClientError as err:
            if not self._incommserror:
                _LOGGER.error("Error getting new camera image: %s", err)
                self._incommserror=True
            return self._last_image

        self._last_url = self._camUrl
        return self._last_image

