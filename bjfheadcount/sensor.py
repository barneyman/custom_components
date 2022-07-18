from homeassistant.helpers.entity import Entity

import logging

_LOGGER = logging.getLogger(__name__)


from homeassistant.helpers.event import async_track_state_change

DOMAIN = "bjfheadcount"

# Validation of the user's configuration
# PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
#    vol.Required(CONF_HOST): cv.string,
#    vol.Optional(CONF_PORT): cv.port
# })


def setup_platform(hass, config, add_devices, discovery_info=None):
    # pylint: disable=unused-argument
    """Setup the sensor platform."""
    # configHost=config.get(CONF_HOST)
    # configPort=config.get(CONF_PORT)

    # _LOGGER.info(configHost+":"+str(configPort))
    add_devices([HeadCountSensor(hass)])


class HeadCountSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, hass):
        self._state = None
        self._hass = hass

        async def _async_sensor_changed(entity_id, old_state, new_state):
            # pylint: disable=unused-argument
            if new_state is None:
                return
            _LOGGER.info("seen state change for %s",(entity_id))

            await hass.async_add_executor_job(self.update)

        # walk thru all the tracked entities, and listen for their state change
        for entity_id in hass.states.entity_ids("device_tracker"):
            _LOGGER.info("subscribing to state change for %s",(entity_id))
            async_track_state_change(hass, entity_id, _async_sensor_changed)

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Headcount Sensor"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "pax"

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        home = 0
        for entity_id in self._hass.states.entity_ids("device_tracker"):
            state = self._hass.states.get(entity_id)
            if state.state == "home":
                home = home + 1

        _LOGGER.info("headcount %d",(home))

        self._state = home
