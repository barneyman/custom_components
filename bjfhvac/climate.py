"""
Demo platform that offers a fake climate device.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/demo/
"""
from homeassistant.components.climate import (
    ClimateEntity, ATTR_TARGET_TEMP_HIGH, ATTR_TARGET_TEMP_LOW,
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_TARGET_HUMIDITY,
    SUPPORT_FAN_MODE,
    SUPPORT_AUX_HEAT, SUPPORT_SWING_MODE,
    SUPPORT_TARGET_TEMPERATURE_RANGE,
    
    HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL,HVAC_MODE_HEAT_COOL
    )
from homeassistant.const import TEMP_CELSIUS, TEMP_FAHRENHEIT, ATTR_TEMPERATURE

from homeassistant.helpers.event import (
    async_track_state_change, async_track_time_interval)

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE 

import logging
_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Demo climate devices."""
    add_entities([
        LGirClimate(hass, 'LG AirCon', 22, TEMP_CELSIUS, 
                    None, None, None, None, 
                    None, None, "On", 
                    'autoDetect', None, 24, 20,
                    False)
        #LGirClimate('Hvac', 21, TEMP_CELSIUS, True, None, 22, 'On High',
        #            67, 54, 'Off', 'cool', False, None, None, None),
        #LGirClimate('Ecobee', None, TEMP_CELSIUS, None, 'home', 23, 'Auto Low',
        #            None, None, 'Auto', 'auto', None, 24, 21, None)
    ])


class LGirClimate(ClimateEntity):
    """Representation of a demo climate device."""

    def __init__(self, hass, name, target_temperature, unit_of_measurement,
                 away, hold, current_temperature, current_fan_mode,
                 target_humidity, current_humidity, current_swing_mode,
                 current_operation, aux, target_temp_high, target_temp_low,
                 is_on):
        """Initialize the climate device."""
        self._name = name
        self._lower_kwh=0
        self._support_flags = SUPPORT_FLAGS
        self._last_service_data={ "remote":"","command":"" }
        if target_temperature is not None:
            self._support_flags = \
                self._support_flags | SUPPORT_TARGET_TEMPERATURE
                
                
#        if hold is not None:
#            self._support_flags = self._support_flags | SUPPORT_HOLD_MODE
#        if current_fan_mode is not None:
#           self._support_flags = self._support_flags | SUPPORT_FAN_MODE
#        if target_humidity is not None:
#            self._support_flags = \
#                self._support_flags | SUPPORT_TARGET_HUMIDITY
#        if current_swing_mode is not None:
#            self._support_flags = self._support_flags | SUPPORT_SWING_MODE
#        if aux is not None:
#            self._support_flags = self._support_flags | SUPPORT_AUX_HEAT
#       if target_temp_high is not None:
#            self._support_flags = \
#               self._support_flags | SUPPORT_TARGET_TEMPERATURE_RANGE
#        if target_temp_low is not None:
#            self._support_flags = \
#                self._support_flags | SUPPORT_TARGET_TEMPERATURE_RANGE

  
        self._target_temperature = target_temperature
        self._target_humidity = target_humidity
        self._unit_of_measurement = unit_of_measurement
        self._away = away
        self._hold = hold
        self._current_temperature = current_temperature
        self._current_humidity = current_humidity
        self._current_fan_mode = current_fan_mode
        self._current_operation = current_operation
        self._aux = aux
        self._current_swing_mode = current_swing_mode
        self._fan_list = ['On Low', 'On High', 'Auto Low', 'Auto High', 'Off']
        self._operation_list = ['heat', 'cool', 'auto', 'autoDetect', 'off']
        self._swing_list = ['On', 'Off']
        self._target_temperature_high = target_temp_high
        self._target_temperature_low = target_temp_low
        self._on = is_on
        self._hvac_mode=HVAC_MODE_OFF

#self._current_temperature=self.hass.states.get("sensor.interior_temp.state")

        # listen for interior temp changes
        async_track_state_change(hass, "sensor.interior_temp", self._async_tempsensor_changed)
        #listen for solar changes
        async_track_state_change(hass, "sensor.solar", self._async_solar_changed)
        #listen for who's in changes
        # done as headcount() - should be exposed as a sensor sensor.headcount_sensor        
        async_track_state_change(hass, "sensor.headcount_sensor", self._async_headcount_changed)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    async def _async_tempsensor_changed(self, entity_id, old_state, new_state):
        """Handle temperature changes."""
        if new_state is None:
            return

        try:
            self._current_temperature = float(new_state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s %s", ex, new_state)
            
        result = await self.hass.async_add_executor_job(self.decideWhatToDo)
        
        await self.async_update_ha_state()


    async def _async_solar_changed(self, entity_id, old_state, new_state):
        """Handle solar KW changes."""
        if new_state is None or new_state.state=="unavailable":
            return

        try:
            self._current_kwh = float(new_state.state)
        except ValueError as ex:
            _LOGGER.warning("Unable to update from sensor: %s %s", ex, new_state)
        
        result = await self.hass.async_add_executor_job(self.decideWhatToDo)
       
        
        await self.async_update_ha_state()


    async def _async_headcount_changed(self, entity_id, old_state, new_state):
        """Handle solar KW changes."""
        if new_state is None or new_state.state=="unknown":
            return

        try:
            self._headcount = int(new_state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s %s", ex, new_state)
        
        await self.async_update_ha_state()

        
        



    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature


    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        return self._target_temperature_high

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        return self._target_temperature_low

    @property
    def current_humidity(self):
        """Return the current humidity."""
        return self._current_humidity

    @property
    def target_humidity(self):
        """Return the humidity we try to reach."""
        return self._target_humidity

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return self._operation_list

    @property
    def is_away_mode_on(self):
        """Return if away mode is on."""
        return self._away

    @property
    def current_hold_mode(self):
        """Return hold mode setting."""
        return self._hold

    @property
    def hvac_mode(self):
        """Return hold mode setting."""
        return self._hvac_mode
        
    @property
    def hvac_modes(self):
        """Return the list of available hvac operation modes.
        Need to be a subset of HVAC_MODES.
        """
        hvac_list = [HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL,HVAC_MODE_HEAT_COOL]        
        return hvac_list
        
    def set_hvac_mode(self, new_mode):
        if new_mode is not None:
            self._hvac_mode = new_mode
            
            if new_mode==HVAC_MODE_OFF:
                self.turn_off()
            else:
                self.turn_on()
            
        self.schedule_update_ha_state()
        
    @property
    def is_aux_heat_on(self):
        """Return true if aux heat is on."""
        return self._aux

    @property
    def is_on(self):
        """Return true if the device is on."""
        return self._on

    @property
    def current_fan_mode(self):
        """Return the fan setting."""
        return self._current_fan_mode

    @property
    def fan_list(self):
        """Return the list of available fan modes."""
        return self._fan_list

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            self._target_temperature = kwargs.get(ATTR_TEMPERATURE)
        if kwargs.get(ATTR_TARGET_TEMP_HIGH) is not None and \
           kwargs.get(ATTR_TARGET_TEMP_LOW) is not None:
            self._target_temperature_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
            self._target_temperature_low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        self.schedule_update_ha_state()

    def set_humidity(self, humidity):
        """Set new target temperature."""
        self._target_humidity = humidity
        self.schedule_update_ha_state()

    def set_swing_mode(self, swing_mode):
        """Set new target temperature."""
        service_data={ "remote":"LGair","command":"swing_toggle" }
        self.hass.services.call('bjfirc', 'send', service_data)

        self._current_swing_mode = swing_mode
        self.schedule_update_ha_state()

    def set_fan_mode(self, fan_mode):
        """Set new target temperature."""
        self._current_fan_mode = fan_mode
        self.schedule_update_ha_state()

    def set_operation_mode(self, operation_mode):
        """Set new target temperature."""
        self._current_operation = operation_mode
        self.schedule_update_ha_state()



    @property
    def current_swing_mode(self):
        """Return the swing setting."""
        return self._current_swing_mode

    @property
    def swing_list(self):
        """List of available swing modes."""
        return self._swing_list

    def turn_away_mode_on(self):
        """Turn away mode on."""
        self._away = True
        self.schedule_update_ha_state()

    def turn_away_mode_off(self):
        """Turn away mode off."""
        self._away = False
        self.schedule_update_ha_state()

    def set_hold_mode(self, hold_mode):
        """Update hold_mode on."""
        self._hold = hold_mode
        self.schedule_update_ha_state()

    def turn_aux_heat_on(self):
        """Turn auxiliary heater on."""
        self._aux = True
        self.schedule_update_ha_state()

    def turn_aux_heat_off(self):
        """Turn auxiliary heater off."""
        self._aux = False
        self.schedule_update_ha_state()

    # this turns on the self-aware'ness 
    # the on actually happens in a loop
    def turn_on(self):
        """Turn on."""
        self._on = True

        #service_data={ "remote":"LG20bit","command":"heatOn20" }
        #self.hass.services.call('bjfirc', 'send', service_data)
        self.decideWhatToDo()
        self.schedule_update_ha_state()
        

    def turn_off(self):
        """Turn off."""
        self._on = False
        # send immediately
        service_data={ "remote":"LG20bit","command":"all_off" }
        self.hass.services.call('bjfirc', 'send', service_data)
        
        self._last_service_data=""

        self.schedule_update_ha_state()

        
    def decideWhatToDo(self):
        _LOGGER.info("decideWhatToDo")

        # first, are we on?
        if self._on==False:
            _LOGGER.info("not on, bailing")
            return;

        service_data={ "remote":"LG20bit","command":"" }
        
        # what does the current temp suggest we do?
        # suggestedMode="coolOn18" if self._current_temperature > self._target_temperature_high else "heatOn20"
        
        if self._current_temperature is None:
            return
            
         
            
        _LOGGER.info(str(self._current_temperature))
        
        if self._current_temperature > self._target_temperature_high:
            suggestedMode="coolOn18"
        elif self._current_temperature < self._target_temperature_low:
            suggestedMode="heatOn20"
        else:
            suggestedMode="all_off"
        
        
        if self._hvac_mode==HVAC_MODE_HEAT_COOL:
            _LOGGER.info("autoDetect")
            # aha! 
            # people here?
            if self._headcount==0 or self._current_kwh < self._lower_kwh:
                _LOGGER.info("lower threshholds (Cnt or KW) reached")
                service_data['command']="all_off"
            else:
                service_data['command']=suggestedMode
        elif self._hvac_mode==HVAC_MODE_HEAT:
            _LOGGER.info("heat")
            service_data['command']="heatOn20"
        elif self._hvac_mode==HVAC_MODE_COOL:
            _LOGGER.info("cool")
            service_data['command']="coolOn18"
        else:
            _LOGGER.info("all off")
            service_data['command']="all_off"

        if service_data == self._last_service_data:
           _LOGGER.info("redundant")
           return;

        _LOGGER.info(service_data)

        self._last_service_data=service_data
        
        self.hass.services.call('bjfirc', 'send', service_data)
        # this may need some logic behind it
        #self.set_swing_mode("On")
        
    
    