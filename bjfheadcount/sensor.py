from homeassistant.const import TEMP_CELSIUS, CONF_HOST, CONF_PORT
from homeassistant.helpers.entity import Entity
import json
import http.client

import logging
_LOGGER = logging.getLogger(__name__)

from homeassistant.components.sensor import PLATFORM_SCHEMA


import homeassistant.helpers.config_validation as cv
import voluptuous as vol

DOMAIN = 'bjfheadcount'

# Validation of the user's configuration
#PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
#    vol.Required(CONF_HOST): cv.string,
#    vol.Optional(CONF_PORT): cv.port
#})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the sensor platform."""
    #configHost=config.get(CONF_HOST)
    #configPort=config.get(CONF_PORT)

    #_LOGGER.info(configHost+":"+str(configPort))
    add_devices([HeadCountSensor()])

class HeadCountSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self):
        self._state = None
        
        
    @property
    def name(self):
        """Return the name of the sensor."""
        return 'Headcount Sensor'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "ppl"

    def update(self):
        """Fetch new state data for the sensor.
		
        This is the only method that should fetch new data for Home Assistant.
        """
        home = 0
        for entity_id in self.hass.states.entity_ids('device_tracker'):
            state = self.hass.states.get(entity_id)
            if state.state == 'home':
                home = home + 1
        
        self._state=home

