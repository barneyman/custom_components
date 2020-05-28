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
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("presence_binary"): cv.string,  # sensor.headcount_sensor
                vol.Required("lux_sensor"): cv.string,
                vol.Required("off_scene"): cv.string,
                "absent": {
                    vol.Optional("unlit_scene"): cv.string,
                    vol.Optional("lit_scene"): cv.string,
                    vol.Required("minLux"): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=100)
                    ),
                },
                "present": {
                    vol.Optional("unlit_scene"): cv.string,
                    vol.Optional("lit_scene"): cv.string,
                    vol.Required("minLux"): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=100)
                    ),
                },
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass, baseConfig):
    """Set up is called when Home Assistant is loading our component."""

    _LOGGER.info("luxlights setup")

    config = baseConfig[DOMAIN]

    _HEADCOUNT_BINARY = config.get("presence_binary")
    _LUX_SENSOR = config.get("lux_sensor")

    _ABSENT = config["absent"]
    _PRESENT = config["present"]

    _SCENE_OFF = config.get("off_scene")

    # the ln(lux) below which we trigger ON
    # occupied, we open the blind
    ## _MIN_LUX_VALUE_OCCUPIED = config.get("minlux_Occupied")

    # uoccupied, we don't
    ## _MIN_LUX_VALUE = config.get("minlux_Vacant")

    ## _SCENE_VACANT = config.get("scene_vacant")
    ## _SCENE_OCCUPIED = config.get("scene_occupied")
    ## _SCENE_FAKE = config.get("scene_fake")

    def saveState(data):
        hass.data[DOMAIN] = json.dumps(data)

    #        with open(mypersistfile, 'w') as outfile:
    #            json.dump(data, outfile)

    lastKnownRunState = {"state": "unknown", "scene": "unknown"}
    saveState(lastKnownRunState)

    def loadState():
        #        with open(mypersistfile) as json_file:
        #            return json.load(json_file)
        return json.loads(hass.data[DOMAIN])

    # TODO check this function
    def handle_turnoff(call):

        home = int(hass.states.get(_HEADCOUNT_BINARY).state)

        if home=="on":
            # turn on occupied
            _LOGGER.info("off ignored")
        else:
            service_data = {"entity_id": _SCENE_OFF}
            _LOGGER.info("to vacant")
            lastKnownRunState = {"state": "off", "scene": "unknown"}

            hass.services.call("scene", "turn_on", service_data)
            saveState(lastKnownRunState)
            # tell the boss
            # hass.services.call(
            #     "hangouts",
            #     "send_message",
            #     {
            #         "target": [{"id": "UgyKl3VkJ2F2G_ykyb14AaABAagBjd2cDg"}],
            #         "message": [{"text": "Lights OFF at the beach house"}],
            #     },
            # )

    # this gets called from an automation, it's a hard OFF
    def handle_forceoff(call):

        service_data = {"entity_id": _SCENE_OFF}
        _LOGGER.info("to vacant")
        lastKnownRunState = {"state": "off", "scene": "unknown"}
        hass.services.call("scene", "turn_on", service_data)
        saveState(lastKnownRunState)

    # TODO check this function
    def handle_enableCheck(call):

        lastKnownRunState = {"state": "check", "scene": "unknown"}
        saveState(lastKnownRunState)

    def handle_check():

        # this should run every five mins from before sunset to 11pm
        # first, check the lux
        _LOGGER.info("reading sensors")
        lux = hass.states.get(_LUX_SENSOR)
        hcountBinary = hass.states.get(_HEADCOUNT_BINARY)
        # sensor.lux_sensor
        _LOGGER.debug("Lux sensor %s", str(lux))
        _LOGGER.debug("hcountBinary sensor %s", str(hcountBinary))

        # only run if we're enabled (happens by dusk event in automation) after we're turned off
        # also allows for 'unknown' after a reboot
        lastKnownRunState = loadState()

        _LOGGER.debug("lastKnownRunState")
        _LOGGER.debug(lastKnownRunState)

        if lastKnownRunState["state"] == "off":
            return

        home = 0

        if lux is None:
            _LOGGER.warning("None for lux results, bailing")
            return
        if hcountBinary is None:
            _LOGGER.warning("None for hcountBinary results, bailing")
            return

        if lux.state == "unavailable" or hcountBinary.state == "unavailable":
            _LOGGER.warning("sensors unavailable, bailing")
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
            meta = _PRESENT
        else:
            nextStateValue["state"] = "absent"
            meta = _ABSENT

        _LOGGER.debug("meta")
        _LOGGER.debug(meta)

        # check lux
        if luxValue < float(meta["minLux"]):
            nextStateValue["scene"] = "lit_scene"
        else:
            nextStateValue["scene"] = "unlit_scene"

        _LOGGER.debug("nextStateValue")
        _LOGGER.debug(nextStateValue)

        # do we need a transition - off gets checked for above
        if lastKnownRunState["state"] != nextStateValue["state"]:
            _LOGGER.info("state different")
            # which transition
            if nextStateValue["scene"] in meta:
                sceneToGo = meta[nextStateValue["scene"]]
                _LOGGER.info("turning on %s", sceneToGo)
                hass.services.call("scene", "turn_on", {"entity_id": sceneToGo})

            saveState(nextStateValue)
            return

        # same state - different scene?
        if lastKnownRunState["scene"] != nextStateValue["scene"]:
            _LOGGER.info("scene different")
            if nextStateValue["scene"] in meta:
                sceneToGo = meta[nextStateValue["scene"]]
                _LOGGER.info("turning on %s", sceneToGo)
                hass.services.call("scene", "turn_on", {"entity_id": sceneToGo})

            saveState(nextStateValue)
            return

        # nothing to do
        _LOGGER.info("Left doing nothing")

        return


    async def _async_sensor_changed(entity_id, old_state, new_state):
        """Handle temperature changes."""
        if new_state is None:
            return
        result = await hass.async_add_executor_job(handle_check)

    async_track_state_change(hass, _HEADCOUNT_BINARY, _async_sensor_changed)
    async_track_state_change(hass, _LUX_SENSOR, _async_sensor_changed)

    hass.services.register(DOMAIN, "enable_check", handle_enableCheck)
    hass.services.register(DOMAIN, "turn_off", handle_turnoff)
    hass.services.register(DOMAIN, "force_off", handle_forceoff)

    saveState(lastKnownRunState)

    # Return boolean to indicate that initialization was successfully.
    return True
