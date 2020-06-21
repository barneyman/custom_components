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
    BEACH_HEAD,
    DEVICES_ADDED,
    DISCOVERY_ROOT,
    DEVICES_FOUND,
    DEVICES_FOUND_CAMERA,
    LISTENING_PORT,
    AUTH_TOKEN,
)
from .helpers import doQuery, doPost, BJFDeviceInfo, BJFListener

_LOGGER = logging.getLogger(__name__)

DOMAIN = "barneyman"

# called from entity_platform.py line 129
# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):
    _LOGGER.debug("CAMERA async_setup_entry: %s", config_entry)

    # simply so i have a ref to async_add_devices
    def scanForCameras(self):
        _LOGGER.info("scanForCameras Called!!!!!")

        workingList = hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][
            DEVICES_FOUND_CAMERA
        ].copy()
        hass.data[DOMAIN][DISCOVERY_ROOT][DEVICES_FOUND][DEVICES_FOUND_CAMERA] = []

        for newhost in workingList:
            _LOGGER.info("addBJFcamera %s", newhost)
            addBJFcamera(newhost, async_add_devices, hass)

    # Search for devices
    # removing this causes devices o not be discovered? specuatoive change, enabkibg
    scanForCameras(0)

    # then schedule this again for X seconds.
    async_track_time_interval(hass, scanForCameras, timedelta(seconds=30))

    return True


def addBJFcamera(hostname, add_devices, hass):
    _LOGGER.info("addBJFcamera querying %s", hostname)

    config = doQuery(hostname, "/json/config", True)

    if config != None:

        camerasToAdd = []
        mac = config["mac"]

        # built early, in case it's shared
        url = "http://" + config["ip"] + "/camera?cam="

        friendlyName = (
            config["friendlyName"] if "friendlyName" in config else config["name"]
        )


        # add a bunch of cameras
        for eachCamera in config["cameraConfig"]:

            potential = None

            _LOGGER.info("Potential BJFRestSensor")

            camNumber=eachCamera["camera"]

            potential = BJFEspCamera(
                hass,
                mac,
                hostname,
                # entity name
                friendlyName+" "+eachCamera["name"] + " " + str(camNumber),
                url+str(camNumber),
                camNumber,
                config,
            )

            if potential is not None:
                _LOGGER.info("Adding camera %s", potential._unique_id)
                camerasToAdd.append(potential)

        add_devices(camerasToAdd)

    else:
        _LOGGER.error("Failed to query %s", hostname)


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
        self._frame_interval=2
        self._camUrl=camUrl
        self._last_image=None

        self._supported_features = 0

    @property
    def unique_id(self):
        """Return unique ID for sensor."""
        return self._unique_id


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

    async def async_camera_image(self):
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
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting image from: %s", self._name)
            return self._last_image
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting new camera image: %s", err)
            return self._last_image

        self._last_url = self._camUrl
        return self._last_image

