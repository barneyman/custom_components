import logging
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

# The domain of your component. Should be equal to the name of your component.
DOMAIN = "luxlights"


# ATTR_NAME = 'name'
# DEFAULT_NAME = 'World'

import json

# mypersistfile="./luxlights.json"

from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_point_in_time,
    track_point_in_time,
)
from homeassistant.util.dt import as_local, utcnow
from homeassistant.helpers.entity import Entity
import datetime
from homeassistant.const import STATE_ON

import homeassistant.helpers.config_validation as cv


# Validation of the user's configuration

# instanceSchema=vol.Schema(
#         {
#             vol.Required("presence_binary"): cv.string,
#             vol.Required("lux_sensor"): cv.string,
#             vol.Required("off_scene"): cv.string,
#             vol.Optional("jitter", default=10):vol.All(
#                     vol.Coerce(float), vol.Range(min=0, max=20)
#                 ),
#             "absent": {
#                 vol.Optional("unlit_scene"): cv.string,
#                 vol.Optional("lit_scene"): cv.string,
#                 vol.Required("minLux"): vol.All(
#                     vol.Coerce(float), vol.Range(min=0, max=100)
#                 ),
#             },
#             "present": {
#                 vol.Optional("unlit_scene"): cv.string,
#                 vol.Optional("lit_scene"): cv.string,
#                 vol.Required("minLux"): vol.All(
#                     vol.Coerce(float), vol.Range(min=0, max=100)
#                 ),
#             }
#         }
#     )

offSchema = vol.Schema({vol.Required("at"): cv.time})

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("instances"): vol.All(
                    cv.ensure_list,
                    [
                        {
                            vol.Required("name"): cv.string,
                            vol.Required("presence_binary"): cv.string,
                            vol.Required("lux_sensor"): cv.string,
                            vol.Required("off_scene"): cv.string,
                            "softOff": offSchema,
                            "hardOff": offSchema,
                            "reset": offSchema,
                            vol.Optional("jitter", default=30): vol.All(
                                vol.Coerce(float), vol.Range(min=0, max=50)
                            ),
                            "absent": vol.Schema(
                                {
                                    vol.Optional("unlit_scene"): cv.string,
                                    vol.Optional("lit_scene"): cv.string,
                                    vol.Required("minLux"): vol.All(
                                        vol.Coerce(float), vol.Range(min=0, max=100)
                                    ),
                                }
                            ),
                            "present": vol.Schema(
                                {
                                    vol.Optional("unlit_scene"): cv.string,
                                    vol.Optional("lit_scene"): cv.string,
                                    vol.Required("minLux"): vol.All(
                                        vol.Coerce(float), vol.Range(min=0, max=100)
                                    ),
                                }
                            ),
                            vol.Optional("veto_sensors", default=[]): cv.entity_ids,
                        },
                    ],
                )
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

luxInstances = []


class luxLightInstance(Entity):
    def __init__(self, hass, config):

        self._hass = hass
        self._config = config

        self._name = config.get("name")

        _LOGGER.info("Creating luxLightInstance '%s'", (self._name))

        self._headcountSensor = config.get("presence_binary")
        self._luxSensor = config.get("lux_sensor")
        self._luxJitter = config.get("jitter")
        self._offScene = config.get("off_scene")

        self._lastKnownRunState = None
        self._softOff = None
        self._hardOff = None

        self._absentDetail = config["absent"]
        self._presentDetail = config["present"]

        if "veto_sensors" in config:
            self._veto_sensors=config["veto_sensors"]
        else:
            self._veto_sensors=[]


        # prime the storing
        hass.data[DOMAIN][self._name]={}

        lastKnownRunState = {"state": "unknown", "scene": "unknown"}
        self.saveState(lastKnownRunState)

        async def _async_sensor_changed(entity_id, old_state, new_state):
            # pylint: disable=unused-argument
            """Handle temperature changes."""
            if new_state is None:
                return

            _LOGGER.info(
                "State change for %s forcing lux check for %s", entity_id, self._name
            )

            await hass.async_add_executor_job(self.handleSensoryCheck)

        self.scheduleOffTimes()
        self.scheduleReset()

        async_track_state_change(hass, self._headcountSensor, _async_sensor_changed)
        async_track_state_change(hass, self._luxSensor, _async_sensor_changed)

    def timeStringToDateTime(self, stringTime):
        # get now from homeassistant.util.dt import as_local, utcnow
        now = utcnow()
        # turn it local
        now = as_local(now)
        # fix the time component
        then = now.replace(
            hour=stringTime.hour,
            minute=stringTime.minute,
            second=stringTime.second,
            microsecond=0,
        )
        _LOGGER.info("now %s then %s", now, then)
        # check for 'gone'
        if then < now:
            _LOGGER.info("missed it - adding a day")
            # add a day
            then += datetime.timedelta(days=1)
        return then

    def scheduleReset(self):

        # get my hard/soft off times
        self._reset = self.timeStringToDateTime(self._config["reset"]["at"])

        _LOGGER.info("reset time is %s", (self._reset))

        track_point_in_time(self._hass, self.resetCheck, self._reset)

    def scheduleOffTimes(self):

        self.scheduleSoftOffTimes()
        self.scheduleHardOffTimes()

    def scheduleSoftOffTimes(self):

        # get my hard/soft off times
        self._softOff = self.timeStringToDateTime(self._config["softOff"]["at"])
        _LOGGER.info("Soft Off times is %s", (self._softOff))
        track_point_in_time(self._hass, self.softOff, self._softOff)

    def scheduleHardOffTimes(self):

        # get my hard/soft off times
        self._hardOff = self.timeStringToDateTime(self._config["hardOff"]["at"])
        _LOGGER.info("Hard Off times is %s", (self._hardOff))
        track_point_in_time(self._hass, self.hardOff, self._hardOff)

    def handleSensoryCheck(self):

        # this should run every five mins from before sunset to 11pm
        # first, check the lux
        _LOGGER.info(
            "reading sensors %s %s for instance '%s'",
            self._luxSensor,
            self._headcountSensor,
            self._name,
        )
        lux = self._hass.states.get(self._luxSensor)
        hcountBinary = self._hass.states.get(self._headcountSensor)
        # sensor.lux_sensor
        _LOGGER.debug("Lux sensor %s", str(lux))
        _LOGGER.debug("hcountBinary sensor %s", str(hcountBinary))

        # only run if we're enabled (happens by dusk event in automation) after we're turned off
        # also allows for 'unknown' after a reboot
        self._lastKnownRunState = self.loadState()

        _LOGGER.debug("lastKnownRunState : %s", (self._lastKnownRunState))

        # distinguish between hardoff and softoff
        if self._lastKnownRunState["state"] == "off":
            return

        home = 0

        if lux is None:
            _LOGGER.warning("None for lux results, bailing")
            return
        if hcountBinary is None:
            _LOGGER.warning("None for hcountBinary results, bailing")
            return

        if lux.state in ["unavailable","unknown"]:
            _LOGGER.info("lux sensor unavailable, bailing")
            return

        if hcountBinary.state in ["unavailable","unknown"]:
            _LOGGER.info("headcount sensor unavailable, bailing")
            return

        # check to see we're not locked out
        for each in self._veto_sensors: #["sensor.sunload_southside", "sensor.sunload_northside"]:
            _LOGGER.debug("checking veto_sensor %s", each)
            if self._hass.states.is_state(each, "True"):
                _LOGGER.info("headcount sensor disabled by %s, bailing", (each))
                return

        # get the values we need
        try:
            luxValue = float(lux.state)
            home = hcountBinary.state

        except Exception as e:
            _LOGGER.warning("luxlights exception %s", e)
            return

        nextStateValue = {}

        if home == "on":
            nextStateValue["state"] = "present"
            meta = self._presentDetail
        else:

            # if presence hasn't changed, and we're softOff, just ignore this (or we'll visit it redundantly, regularly)
            if self._lastKnownRunState["state"] == "softOff":
                _LOGGER.debug("softOff already in effect, bailing")
                return

            nextStateValue["state"] = "absent"
            meta = self._absentDetail

        _LOGGER.debug("meta : %s", (meta))

        # work out minlux
        minLuxValue = meta["minLux"]
        # to stop us turning on and off at the threshold
        if self._lastKnownRunState["scene"] == "lit_scene":
            minLuxValue = minLuxValue + self._luxJitter
            _LOGGER.debug(
                "applying jitter %f + %f = %f",
                meta["minLux"],
                self._luxJitter,
                minLuxValue,
            )

        # check lux
        if luxValue <= minLuxValue:
            nextStateValue["scene"] = "lit_scene"
        else:
            nextStateValue["scene"] = "unlit_scene"

        _LOGGER.debug("nextStateValue : %s", (nextStateValue))

        # do we need a transition - off gets checked for above
        if self._lastKnownRunState["state"] != nextStateValue["state"]:
            _LOGGER.info("state different")
            # which transition
            if nextStateValue["scene"] in meta:
                sceneToGo = meta[nextStateValue["scene"]]
                _LOGGER.info("turning on %s", sceneToGo)
                self._hass.services.call("scene", "turn_on", {"entity_id": sceneToGo})
            else:
                _LOGGER.info("no scene in config for this state")

            self.saveState(nextStateValue)
            return

        # same state - different scene?
        if self._lastKnownRunState["scene"] != nextStateValue["scene"]:
            _LOGGER.info("scene different")
            if nextStateValue["scene"] in meta:
                sceneToGo = meta[nextStateValue["scene"]]
                _LOGGER.info("turning on %s", sceneToGo)
                self._hass.services.call("scene", "turn_on", {"entity_id": sceneToGo})
            else:
                _LOGGER.info("no scene in config for this state")

            self.saveState(nextStateValue)
            return

        # nothing to do
        _LOGGER.info("Left doing nothing")

        return

    def saveState(self, data):
        _LOGGER.debug("saving state for {} ...".format(self._name))

        self._hass.data[DOMAIN][self._name] = json.dumps(data)
#	LOGGER.info(json.dumps(data))

        self._hass.states.set(
            "sensor.{}_luxlights".format(self._name), data["state"], data
        )

        _LOGGER.info(self._hass.data[DOMAIN])

    def loadState(self):
        _LOGGER.info(self._hass.data[DOMAIN])
        return json.loads(self._hass.data[DOMAIN][self._name])

    # only turn off if no-one present
    def softOff(self, call):
        # pylint: disable=unused-argument

        home = self._hass.states.get(self._headcountSensor).state

        if home == "on":
            # turn on occupied
            _LOGGER.info("off ignored")
        else:
            service_data = {"entity_id": self._offScene}
            _LOGGER.info("%s to vacant", (self._name))
            lastKnownRunState = {"state": "softOff", "scene": self._offScene}

            self._hass.services.call("scene", "turn_on", service_data)
            self.saveState(lastKnownRunState)
            # tell the boss
            # hass.services.call(
            #     "hangouts",
            #     "send_message",
            #     {
            #         "target": [{"id": "UgyKl3VkJ2F2G_ykyb14AaABAagBjd2cDg"}],
            #         "message": [{"text": "Lights OFF at the beach house"}],
            #     },
            # )

        # and reschedule
        self.scheduleSoftOffTimes()

    # this is called by track_point_in_time so needs a rednudant  arg
    # i need to understand why
    def hardOff(self, call):
        # pylint: disable=unused-argument
        service_data = {"entity_id": self._offScene}
        _LOGGER.info("%s to vacant FORCED ", (self._name))
        lastKnownRunState = {"state": "off", "scene": self._offScene}
        self._hass.services.call("scene", "turn_on", service_data)
        self.saveState(lastKnownRunState)

        # and reschedule
        self.scheduleHardOffTimes()

    def resetCheck(self, call):
        # pylint: disable=unused-argument

        lastKnownRunState = {"state": "check", "scene": "unknown"}
        self.saveState(lastKnownRunState)

        self.scheduleReset()

    # sensor stuff

    @property
    def unique_id(self):
        """Return unique ID for sensor."""
        return "LuxSensor_" + self._name

    @property
    def name(self):
        return "LuxSensor " + self._name

    @property
    def state(self):
        """Return the state of the binary sensor."""
        return STATE_ON

    def update(self):
        pass


def setup(hass, baseConfig):
    """Set up is called when Home Assistant is loading our component."""

    _LOGGER.info("luxlights setup")

    config = baseConfig[DOMAIN]

    hass.data[DOMAIN]={}

    # iterate thru the items
    for eachInstance in config["instances"]:
        luxInstances.append(luxLightInstance(hass, eachInstance))


    # Return boolean to indicate that initialization was successfully.
    return True
