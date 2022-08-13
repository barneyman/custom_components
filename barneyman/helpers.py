import logging
import http.client
import json
from homeassistant.components.rest.data import RestData

# from datetime import datetime, timedelta
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
import httpx
from .barneymanconst import BARNEYMAN_DOMAIN

# import asyncio


_LOGGER = logging.getLogger(__name__)
DOMAIN = BARNEYMAN_DOMAIN


def chopLocal(hostname):
    if str(hostname).endswith(".local."):
        hostname = hostname[: -len(".local.")]
    return hostname


def do_exists(hostname):

    json_ret = do_query(hostname, "/json/config", True, timeout=2)

    _LOGGER.info("do_exists %s ", hostname)

    if json_ret is None:
        return False

    if "version" not in json_ret:
        return False

    return True


async def async_do_exists(hostname):
    json_ret = await async_do_query(hostname, "/json/config", True, timeout=2)

    _LOGGER.info("do_exists %s ", hostname)

    if json_ret is None:
        return False

    if "version" not in json_ret:
        return False

    return True


def do_query(
    hostname, url, return_json=False, httpmethod="GET", timeout=10, json_body=None
):
    hostname = chopLocal(hostname)

    try:
        _LOGGER.info("do_query %s%s %s", hostname, url, httpmethod)
        conn = http.client.HTTPConnection(hostname, timeout=timeout)
        conn.request(url=url, method=httpmethod, body=json_body)
        response = conn.getresponse()
        if return_json:
            json_done = response.read().decode("utf-8")
            _LOGGER.debug(json_done)
            response.close()
            conn.close()
            return json.loads(json_done)
        response.close()
        conn.close()
        return True
    except Exception as exception:
        _LOGGER.error("barneyman do_query exception %s %s %s", exception, hostname, url)

    return None


def do_post(
    hostname, url, json_body=None, return_json=False, httpmethod="POST", timeout=5
):
    return do_query(hostname, url, return_json, httpmethod, timeout, json_body)


async def async_do_post(
    hostname, url, json_body=None, return_json=False, httpmethod="POST", timeout=5
):
    return async_do_query(hostname, url, return_json, httpmethod, timeout, json_body)


async def async_do_query(
    hostname, url, return_json=False, httpmethod="GET", timeout=30, json_body=None
):
    #     """Get the latest data from REST service with provided method."""
    hostname = chopLocal(hostname)

    built_url = "http://" + hostname + url

    _LOGGER.info("barneyman async_do_query to %s", built_url)

    try:

        async with httpx.AsyncClient() as client:
            response = await client.request(
                httpmethod,
                built_url,
                headers=None,
                params=None,
                auth=None,
                data=json_body,
                timeout=timeout,
            )
            response.raise_for_status()
            if return_json:
                _LOGGER.info("barneyman async_do_query returned  %s", response.text)
                return json.loads(response.text)
            else:
                return True

    except httpx.HTTPStatusError as exc:
        _LOGGER.error(
            "Error response '%s' while requesting %s.",
            str(exc.response.status_code),
            exc.request.url,
        )

    except httpx.RequestError as exc:
        _LOGGER.error(
            "An error '%s' occurred while requesting %s.", exc, exc.request.url
        )

    except Exception as exception:
        _LOGGER.error(
            "barneyman async_do_query exception '%s' host '%s' url '%s'",
            str(exception),
            hostname,
            url,
        )

    return None


class BJFDeviceInfo:
    def __init__(self, config, mac):
        self._config = config
        self._mac = mac

    # https://developers.home-assistant.io/docs/device_registry_index/
    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (CONNECTION_NETWORK_MAC, self._mac)
            },
            "name": self._config["name"],
            "model": self._config["version"].split("|")[0],
            "manufacturer": BARNEYMAN_DOMAIN,
            "sw_version": self._config["version"].split("|")[1],
            "configuration_url": "http://" + self._config["ip"],
        }


class BJFChildDeviceInfo:
    def __init__(self, config, mac, parent):
        self._config = config
        self._mac = mac
        self._parent = parent.device_info["identifiers"]

    # https://developers.home-assistant.io/docs/device_registry_index/
    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (CONNECTION_NETWORK_MAC, self._mac)
            },
            "name": self._config["name"],
            "manufacturer": BARNEYMAN_DOMAIN,
            "model": self._config["version"].split("|")[0],
            "sw_version": self._config["version"].split("|")[1],
            "via_device": self._parent,
        }


class BJFFinder:
    def __init__(self, hass, hostname) -> None:
        self._hass = hass
        self._hostname = hostname

    def get_ip_address(self):

        _LOGGER.debug("async_get_ip_address for %s", (self._hostname))

        return self._hostname


# this can be reused by a single sensor
# when it's async, the logic is a bit more complex


class BJFRestData(RestData, BJFFinder):
    def __init__(self, hass, hostname, method, auth, headers, data, verify_ssl=False):
        RestData.__init__(
            self, hass, method, None, auth, headers, None, data, verify_ssl
        )

        BJFFinder.__init__(self, hass, hostname)

        self._hass = hass
        self._hostname = hostname

    def get_url(self):

        endip = self.get_ip_address()
        if endip is None:
            return None

        url = "http://" + endip + "/json/state"

        _LOGGER.debug("url for %s", (url))

        return url

    async def async_bjfupdate(self):

        _LOGGER.debug("async_update for %s %s", self._hostname, str(self._verify_ssl))
        # change _resource ** in the parent **
        # super(BJFRestData,self)._resource=self.get_url()
        self._resource = self.get_url()

        await RestData.async_update(self)

        return self.data
