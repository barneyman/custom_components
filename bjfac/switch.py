import logging

#import voluptuous as vol
#import json
#import http.client

import time

# Import the device class from the component that you want to support
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import DEVICE_DEFAULT_NAME

#import homeassistant.helpers.config_validation as cv

# Home Assistant depends on 3rd party packages for API specific code.
# REQUIREMENTS = ['awesome_lights==1.2.3']

_LOGGER = logging.getLogger(__name__)

DOMAIN="bjfac"

# Validation of the user's configuration
#PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
#    vol.Required(CONF_HOST): cv.string,
#    vol.Optional(CONF_PORT): cv.port
#})




def setup_platform(hass, config, add_devices_callback, discovery_info=None):
    """Set up the demo switches."""
    add_devices_callback([
        #DemoSwitch('Decorative Lights', True, None, True),
        #heaterSwitch('Heater', False, 'mdi:air-conditioner', False),
        airconSwitch('AirCon', False, 'mdi:air-conditioner', False)
    ])



class irSwitch(SwitchEntity):
    """Representation of a demo switch."""

    def __init__(self, name, state, icon, assumed):
        """Initialize the Demo switch."""
        self._name = name or DEVICE_DEFAULT_NAME
        self._state = state
        self._icon = icon
        self._assumed = assumed
        # this happens when the device is added ...
        #self.hass=hass

    @property
    def should_poll(self):
        """No polling needed for a demo switch."""
        return False

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def icon(self):
        """Return the icon to use for device if any."""
        return self._icon

    @property
    def assumed_state(self):
        """Return if the state is based on assumptions."""
        return self._assumed

    @property
    def current_power_w(self):
        """Return the current power usage in W."""
        if self._state:
            return 100

    @property
    def today_energy_kwh(self):
        """Return the today total energy usage in kWh."""
        return 15

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._state

    #def turn_on(self, **kwargs):
    #    """Turn the switch on."""
    #    self._state = True
    #    service_data={ "remote":"LG20bit","command":"heatOn20" }
    #    self.hass.services.call('bjfirc', 'send', service_data)
    #    time.sleep(2)
    #    service_data={ "remote":"LGair","command":"swing_toggle" }
    #    self.hass.services.call('bjfirc', 'send', service_data)
    #    # ONLY because we are Not Poll
    #    self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn the device off."""
        self._state = False
        service_data={ "remote":"LG20bit","command":"all_off" }
        self.hass.services.call('bjfirc', 'send', service_data)
        # ONLY because we are Not Poll
        self.schedule_update_ha_state()

class heaterSwitch(SwitchEntity):

    def __init__(self, name, state, icon, assumed):
        irSwitch.__init__(self,name,state,icon,assumed)

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        self._state = True
        service_data={ "remote":"LG20bit","command":"heatOn20" }
        self.hass.services.call('bjfirc', 'send', service_data)
        time.sleep(2)
        service_data={ "remote":"LGair","command":"swing_toggle" }
        self.hass.services.call('bjfirc', 'send', service_data)
        # ONLY because we are Not Poll
        self.schedule_update_ha_state()


class airconSwitch(SwitchEntity):

    def __init__(self, name, state, icon, assumed):
        irSwitch.__init__(self,name,state,icon,assumed)

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        self._state = True
        service_data={ "remote":"LG20bit","command":"coolOn18" }
        self.hass.services.call('bjfirc', 'send', service_data)
        time.sleep(2)
        service_data={ "remote":"LGair","command":"swing_toggle" }
        self.hass.services.call('bjfirc', 'send', service_data)
        # ONLY because we are Not Poll
        self.schedule_update_ha_state()
