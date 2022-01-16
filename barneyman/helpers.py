import logging
import http.client
import json
from homeassistant.components.rest.data import RestData
from datetime import datetime, timedelta
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
import threading
import socket
import time
import httpx
from .barneymanconst import (
    BARNEYMAN_HOST,
    LISTENING_PORT,
    AUTH_TOKEN
)

import asyncio


_LOGGER = logging.getLogger(__name__)
DOMAIN = "barneyman"


def doExists(hostname):
    jsonRet = doQuery(hostname, "/json/config", True, timeout=2)

    _LOGGER.info("doExists %s ", hostname)

    if jsonRet is None:
        return False

    if "version" not in jsonRet:
        return False

    return True


async def async_doExists(hostname):
    jsonRet = await async_doQuery(hostname, "/json/config", True, timeout=2)

    _LOGGER.info("doExists %s ", hostname)

    if jsonRet is None:
        return False

    if "version" not in jsonRet:
        return False

    return True


def doQuery(
    hostname, url, returnJson=False, httpmethod="GET", timeout=10, jsonBody=None
):

    try:
        _LOGGER.info("doQuery %s%s %s", hostname, url, httpmethod)
        conn = http.client.HTTPConnection(hostname, timeout=timeout)
        conn.request(url=url, method=httpmethod, body=jsonBody)
        r = conn.getresponse()
        if returnJson == True:
            jsonDone = r.read().decode("utf-8")
            _LOGGER.debug(jsonDone)
            r.close()
            conn.close()
            return json.loads(jsonDone)
        r.close()
        conn.close()
        return True
    except Exception as e:
        _LOGGER.error("barneyman doQuery exception %s %s %s", e, hostname, url)

    return None


def doPost(
    hostname, url, jsonBody=None, returnJson=False, httpmethod="POST", timeout=5
):
    return doQuery(hostname, url, returnJson, httpmethod, timeout, jsonBody)

async def async_doPost(
    hostname, url, jsonBody=None, returnJson=False, httpmethod="POST", timeout=5
):
    return async_doQuery(hostname, url, returnJson, httpmethod, timeout, jsonBody)


async def async_doQuery(hostname, url, returnJson=False, httpmethod="GET", timeout=30, jsonBody=None):
#     """Get the latest data from REST service with provided method."""

    builtUrl="http://"+hostname+url

    _LOGGER.info("barneyman async_doQuery to %s", builtUrl)

    try:

        async with httpx.AsyncClient() as client:
            response = await client.request(
                httpmethod,
                builtUrl,
                headers=None,
                params=None,
                auth=None,
                data=jsonBody,
                timeout=timeout,
            )
            response.raise_for_status()
            if returnJson:
                _LOGGER.info("barneyman async_doQuery returned  %s", response.text)
                return json.loads(response.text)
            else:
                return True

    except httpx.HTTPStatusError as exc:
        _LOGGER.error(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.")

    except httpx.RequestError as exc:
        _LOGGER.error(f"An error occurred while requesting {exc.request.url!r}.")

    except Exception as e:
        _LOGGER.error("barneyman async_doQuery exception '%s' host '%s' url '%s'", str(e), hostname, url)

    return None



class BJFDeviceInfo:
    def __init__(self, config):
        self._config = config

    # https://developers.home-assistant.io/docs/device_registry_index/
    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (CONNECTION_NETWORK_MAC, self._mac)
            },
            "name": self._config["name"],
            "model": self._config["version"].split('|')[0],
            "manufacturer": "barneyman",
            "sw_version": self._config["version"].split('|')[1],
            "configuration_url": "http://"+self._config["ip"]
        }




class BJFChildDeviceInfo:
    def __init__(self, config, parent):
        self._config = config
        self._parent=parent.device_info["identifiers"]

    # https://developers.home-assistant.io/docs/device_registry_index/
    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (CONNECTION_NETWORK_MAC, self._mac)
            },
            "name": self._config["name"],
            "manufacturer": "barneyman",
            "model": self._config["version"].split('|')[0],
            "sw_version": self._config["version"].split('|')[1],
            "via_device": self._parent
        }



class BJFFinder:
    def __init__(self, hass, hostname) -> None:
        self._hass=hass
        self._hostname=hostname
        
    def getIPaddress(self):

        _LOGGER.debug("async_getIPaddress for {}".format(self._hostname))

        entries=self._hass.config_entries.async_entries(DOMAIN)

        for eachEntry in entries:

            _LOGGER.debug("eachEntry {}".format(eachEntry))

            myentries=eachEntry.data['Devices']

            _LOGGER.debug("myentries {}".format(myentries))

            for each in myentries:
                if each["hostname"]==self._hostname:
                    _LOGGER.info("found {} for {}".format(each["ip"], self._hostname))
                    return each["ip"]
                
        _LOGGER.info("found nothing for {}".format(self._hostname))
        return None
        
            


# this can be reused by a single sensor
# when it's async, the logic is a bit more complex


class BJFRestData(RestData, BJFFinder):
    def __init__(
        self,
        hass,
        hostname,
        method,
        auth,
        headers,
        data,
        verify_ssl=False
    ):
        RestData.__init__(
            self, hass, method, None, auth, headers,None, data, verify_ssl
        )

        BJFFinder.__init__(self,hass,hostname)

        self._hass = hass
        self._hostname=hostname

    def getUrl(self):

        endip=self.getIPaddress()
        if endip==None:
            return None

        url="http://" + endip + "/json/state"        

        _LOGGER.debug("url for {}".format(url))

        return url

    async def async_bjfupdate(self):

        _LOGGER.debug("async_update for {} {}".format(self._hostname,self._verify_ssl))
        #change _resource ** in the parent **
        # super(BJFRestData,self)._resource=self.getUrl()
        self._resource=self.getUrl()

        await RestData.async_update(self)




class BJFListener:
    def __init__(self, transport, hass, hostname):

        self._lastSubscribed=None
        self._subscribeTimeoutMinutes=5
        self._hass=hass
        self._hostname=hostname

        self._finder=BJFFinder(hass,hostname)

        # spin up a thread, tell it the udp
        if transport == "tcp":
            self._listenThread = threading.Thread(target=self.tcpListener)
            _LOGGER.info("BJFListener called with tcp transport")
        elif transport == "udp":
            self._listenThread = threading.Thread(target=self.udpListener)
            _LOGGER.info("BJFListener called with udp transport")
        elif transport == "rest":
            self._listenThread = None
            self._port = 8123
            _LOGGER.info("BJFListener called with http transport")
        elif transport is None:            
            self._listenThread = None
            self._port = None
            _LOGGER.info("BJFListener called with none transport")
        else:
            self._port = None
            self._listenThread = None
            _LOGGER.error("BJFListener called with unknown transport %s", transport)

        self._transport = transport

        # get the available port
        if self._listenThread is not None:
            self._port = hass.data[DOMAIN][LISTENING_PORT]
            # and inc it
            hass.data[DOMAIN][LISTENING_PORT] = self._port + 1

    def udpListener(self):
        _LOGGER.info("udpListener started port %d ...", self._port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # yes, a tuple '' is 'all local addrs'
        sock.bind(("", self._port))

        while self._runListener:
            data, addr = sock.recvfrom(1024)  # buffer size is 1024 bytes

            self.HandleIncomingPacket(data)

    def tcpListener(self):

        _LOGGER.info("tcpListener started port %d ...", self._port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # yes, a tuple '' is 'all local addrs'
        sock.bind(("", self._port))

        sock.listen(2)

        while self._runListener:

            try:
                (clientsocket, address) = sock.accept()
                data = clientsocket.recv(1024)
                _LOGGER.debug("recv out %d", len(data))
                # deserialise
                _LOGGER.debug(data)

                clientsocket.close()

                self.HandleIncomingPacket(data)

            except Exception as e:
                _LOGGER.warning("tcpListener exception %s", e)

    def HandleIncomingPacket(self, data):
        raise NotImplementedError()

    def getPort(self):
        return self._port

    async def async_added_to_hass(self):
        _LOGGER.info("async_added_to_hass %s", self.entity_id)
        # we don't get an entity id until we're added, so don't start the thread until we are
        if self._listenThread is not None:
            self._runListener = True
            self._listenThread.start()
        else:
            _LOGGER.info("async_added_to_hass %s No Transport Thread started", self.entity_id)

    def subscribe(self, deviceType):

        _LOGGER.info("Subscribing %s '%s' ",deviceType, self.entity_id,self._hostname)

        # we do this periodicall, in case the remote device has been rebooted
        # and forgotten we love them
        if self._lastSubscribed is None or ((time.time()-self._lastSubscribed)>self._subscribeTimeoutMinutes*60):


            recipient = self.build_recipient(deviceType)

            # advise the sensor we're listening
            doPost(self._finder.getIPaddress(), "/json/listen", json.dumps(recipient))

            self._lastSubscribed=time.time()

        else:
            _LOGGER.info("subscribe ignored")


    async def async_subscribe(self, deviceType):

        _LOGGER.info("AsyncSubscribing %s '%s' '%s'",deviceType, self.entity_id,self._hostname)
        # we do this periodicall, in case the remote device has been rebooted
        # and forgotten we love them
        if self._lastSubscribed is None or ((time.time()-self._lastSubscribed)>self._subscribeTimeoutMinutes*60):

            _LOGGER.info("Proceeding %s '%s' '%s'",deviceType, self.entity_id,self._hostname)

            recipient = self.build_recipient(deviceType)

            # advise the sensor we're listening
            async_doPost(self._finder.getIPaddress(), "/json/listen", json.dumps(recipient))

            _LOGGER.info("Succeeded %s '%s' '%s'",deviceType, self.entity_id,self._host)

            self._lastSubscribed=time.time()

        else:
            _LOGGER.info("subscribe ignored")

    def build_recipient(self,deviceType):
        recipient = {}
        if self.getPort() is not None:
            recipient["port"] = self.getPort()
        recipient[deviceType] = self._ordinal
        recipient["endpoint"] = "/api/states/" + self.entity_id  #  light.study_light
        recipient["auth"] = self._hass.data[DOMAIN][AUTH_TOKEN]

        _LOGGER.debug(recipient)

        return recipient
