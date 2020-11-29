import logging
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

# The domain of your component. Should be equal to the name of your component.
DOMAIN = "luxlights"


# ATTR_NAME = 'name'
# DEFAULT_NAME = 'World'

import json

# mypersistfile="./luxlights.json"

from homeassistant.helpers.event import async_track_state_change

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


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                "city": vol.Schema({
                    vol.Required("presence_binary"): cv.string,  
                    vol.Required("lux_sensor"): cv.string,
                    vol.Required("off_scene"): cv.string,
                    vol.Optional("jitter", default=10):vol.All(
                            vol.Coerce(float), vol.Range(min=0, max=20)
                        ),
                    "absent": vol.Schema({
                        vol.Optional("unlit_scene"): cv.string,
                        vol.Optional("lit_scene"): cv.string,
                        vol.Required("minLux"): vol.All(
                            vol.Coerce(float), vol.Range(min=0, max=100)
                        ),
                    }),
                    "present": vol.Schema({
                        vol.Optional("unlit_scene"): cv.string,
                        vol.Optional("lit_scene"): cv.string,
                        vol.Required("minLux"): vol.All(
                            vol.Coerce(float), vol.Range(min=0, max=100)
                        ),
                    }),
                })
            }
        )
    }, extra=vol.ALLOW_EXTRA
)

luxInstances=[]


class luxLightInstance:

    def __init__(self, hass, config, name):

        self._hass=hass
        self._name=name
        self._config=config

        self._headcountSensor=config.get("presence_binary")
        self._luxSensor=config.get("lux_sensor")
        self._luxJitter=config.get("jitter")
        self._offScene=config.get("off_scene")

        self._absentDetail=config["absent"]
        self._presentDetail=config["present"]

        # prime the storing
        hass.data[DOMAIN] = { name: {} }

        lastKnownRunState = {"state": "unknown", "scene": "unknown"}
        self.saveState(lastKnownRunState)

        async def _async_sensor_changed(entity_id, old_state, new_state):
            """Handle temperature changes."""
            if new_state is None:
                return

            _LOGGER.info("State change for {} forcing lux check for {}".format(entity_id, name))

            result = await hass.async_add_executor_job(self.handleSensoryCheck)


        async_track_state_change(hass, self._headcountSensor, _async_sensor_changed)
        async_track_state_change(hass, self._luxSensor, _async_sensor_changed)


    def handleSensoryCheck(self):

        # this should run every five mins from before sunset to 11pm
        # first, check the lux
        _LOGGER.info("reading sensors {} {} for instance '{}'".format(self._luxSensor,self._headcountSensor,self._name))
        lux = self._hass.states.get(self._luxSensor)
        hcountBinary = self._hass.states.get(self._headcountSensor)
        # sensor.lux_sensor
        _LOGGER.debug("Lux sensor %s", str(lux))
        _LOGGER.debug("hcountBinary sensor %s", str(hcountBinary))

        # only run if we're enabled (happens by dusk event in automation) after we're turned off
        # also allows for 'unknown' after a reboot
        self._lastKnownRunState = self.loadState()

        _LOGGER.debug("lastKnownRunState")
        _LOGGER.debug(self._lastKnownRunState)

        if self._lastKnownRunState["state"] == "off":
            return

        home = 0

        if lux is None:
            _LOGGER.warning("None for lux results, bailing")
            return
        if hcountBinary is None:
            _LOGGER.warning("None for hcountBinary results, bailing")
            return

        if lux.state == "unavailable":
            _LOGGER.warning("lux sensor unavailable, bailing")
            return

        if hcountBinary.state == "unavailable":
            _LOGGER.warning("headcount sensor unavailable, bailing")
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
            nextStateValue["state"] = "absent"
            meta = self._absentDetail

        _LOGGER.debug("meta")
        _LOGGER.debug(meta)

        # work out minlux
        minLuxValue = meta["minLux"]
        # to stop us turning on and off at the threshold 
        if self._lastKnownRunState["scene"]=="lit_scene":
            minLuxValue=minLuxValue+self._luxJitter
            _LOGGER.debug("applying jitter {} {} {}".format(meta["minLux"],self._luxJitter,minLuxValue))


        # check lux
        if luxValue < minLuxValue:
            nextStateValue["scene"] = "lit_scene"
        else:
            nextStateValue["scene"] = "unlit_scene"

        _LOGGER.debug("nextStateValue")
        _LOGGER.debug(nextStateValue)

        # do we need a transition - off gets checked for above
        if self._lastKnownRunState["state"] != nextStateValue["state"]:
            _LOGGER.info("state different")
            # which transition
            if nextStateValue["scene"] in meta:
                sceneToGo = meta[nextStateValue["scene"]]
                _LOGGER.info("turning on %s", sceneToGo)
                self._hass.services.call("scene", "turn_on", {"entity_id": sceneToGo})

            self.saveState(nextStateValue)
            return

        # same state - different scene?
        if self._lastKnownRunState["scene"] != nextStateValue["scene"]:
            _LOGGER.info("scene different")
            if nextStateValue["scene"] in meta:
                sceneToGo = meta[nextStateValue["scene"]]
                _LOGGER.info("turning on %s", sceneToGo)
                self._hass.services.call("scene", "turn_on", {"entity_id": sceneToGo})

            self.saveState(nextStateValue)
            return

        # nothing to do
        _LOGGER.info("Left doing nothing")

        return

    def saveState(self, data):
        self._hass.data[DOMAIN][self._name] = json.dumps(data)

    def loadState(self):
        return json.loads(self._hass.data[DOMAIN][self._name])

    # only turn off if no-one present
    def softOff(self):

        home = (self._hass.states.get(self._headcountSensor).state)

        if home=="on":
            # turn on occupied
            _LOGGER.info("off ignored")
        else:
            service_data = {"entity_id": _SCENE_OFF}
            _LOGGER.info("{} to vacant".format(self._name))
            lastKnownRunState = {"state": "off", "scene": _SCENE_OFF}

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


    def hardOff(self):

        service_data = {"entity_id": _SCENE_OFF}
        _LOGGER.info("{} to vacant FORCED ".format(self._name))
        lastKnownRunState = {"state": "off", "scene": _SCENE_OFF}
        self._hass.services.call("scene", "turn_on", service_data)
        self.saveState(lastKnownRunState)

    def resetCheck(self):

        lastKnownRunState = {"state": "check", "scene": "unknown"}
        self.saveState(lastKnownRunState)



def setup(hass, baseConfig):
    """Set up is called when Home Assistant is loading our component."""

    _LOGGER.info("luxlights setup")

    config = baseConfig[DOMAIN]



    # get the city one

    luxInstances.append(luxLightInstance(hass,config["city"],"city"))


    # TODO check this function
    def handle_turnoff(call):
        for instance in luxInstances:
            instance.softOff()

    # this gets called from an automation, it's a hard OFF
    def handle_forceoff(call):
        for instance in luxInstances:
            instance.hardOff()

    # reset my state, normally done sunset-hrs
    def handle_enableCheck(call):
        for instance in luxInstances:
            instance.resetCheck()


    hass.services.register(DOMAIN, "enable_check", handle_enableCheck)
    hass.services.register(DOMAIN, "turn_off", handle_turnoff)
    hass.services.register(DOMAIN, "force_off", handle_forceoff)


    # Return boolean to indicate that initialization was successfully.
    return True
