import logging

import voluptuous as vol
import json
import http.client

# Import the device class from the component that you want to support
from homeassistant.components.light import PLATFORM_SCHEMA
from homeassistant.const import CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv

# Home Assistant depends on 3rd party packages for API specific code.
# REQUIREMENTS = ['awesome_lights==1.2.3']

_LOGGER = logging.getLogger(__name__)

DOMAIN="bjfirc"

# Validation of the user's configuration
CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required("host"): cv.string,
        vol.Optional("port"): cv.port
    })
}, extra=vol.ALLOW_EXTRA)




def setup(hass, baseConfig):

    config=baseConfig[DOMAIN]
    """Setup the BJF Light platform."""
    configHost=config.get(CONF_HOST)
    configPort=config.get(CONF_PORT)

#    _LOGGER.info("%s %d",configHost,configPort)
    _LOGGER.info(config)

    def handle_ircSend(call):
        remote = call.data.get("remote", "")
        keycmd = call.data.get("command", "")

        if remote=="" or keycmd=="":
           return;


        #hass.states.set('luxlights.lastcheck', datetime.datetime.now().isoformat())
        #entity_id='light.lamp1'
        #service_data = {'entity_id':  entity_id}
        #hass.services.call('light', 'turn_on', service_data)
        
        request={ "ircsend": { "remote":remote, "command":keycmd } }
        reqheaders = {"Content-type": "application/json", "Accept": "text/plain"}

        conn=http.client.HTTPConnection(configHost+":"+str(configPort))
        conn.request(url="data", method="POST", body=json.dumps(request), headers=reqheaders)
        r=conn.getresponse()
        r.close()
        conn.close()
 

    hass.services.register(DOMAIN, 'send', handle_ircSend)
    return True



