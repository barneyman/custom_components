import logging
import json
from datetime import timedelta
from homeassistant.helpers.template import Template
from homeassistant.components.rest.sensor import RestSensor
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .barneymanconst import (
    BARNEYMAN_DEVICES,
    BARNEYMAN_DEVICES_SEEN,
    DEVICES_SENSOR,
    BARNEYMAN_DOMAIN,
    BARNEYMAN_BROWSER,
    SIGNAL_BARNEYMAN_DISCOVERED,
)

from homeassistant.core import callback

from .helpers import (
    BJFDeviceInfo,
    BJFRestData,
    BJFListener,
    async_do_query,
    BJFFinder,
    chopLocal,
)
from homeassistant.components.binary_sensor import BinarySensorEntity


_LOGGER = logging.getLogger(__name__)

DOMAIN = BARNEYMAN_DOMAIN


# called from entity_platform.py line 129
# this gets forwarded from the component async_setup_entry
async def async_setup_entry(hass, config_entry, async_add_devices):

    _LOGGER.debug("SENSOR async_setup_entry: %s", config_entry.data)

    async def async_setupDevice(z):
        _LOGGER.info("async_setupDevice for Sensor")
        await addBJFsensor(
            z,
            async_add_devices,
            hass,
        )

    # listen for 'device found'
    async_dispatcher_connect(hass, SIGNAL_BARNEYMAN_DISCOVERED, async_setupDevice)

    # go thru what's already bean found
    if hass.data[DOMAIN][BARNEYMAN_BROWSER] is not None:
        for each in hass.data[DOMAIN][BARNEYMAN_BROWSER].getHosts():
            await async_setupDevice(each)

    # TODO
    return True


from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

wip = []


async def addBJFsensor(data, add_devices, hass):

    sensorsToAdd = []

    hostname = chopLocal(data.server)
    # TODO - i've got - and _ mismatches between host names and mdns names in my esp code
    # so fix that, then remove this
    hostname = ".".join(str(c) for c in data.addresses[0])
    # remove .local.
    host = hostname

    if hostname in wip:
        _LOGGER.debug("already seen in WIP %s", hostname)
        return

    if hostname in hass.data[DOMAIN][BARNEYMAN_DEVICES_SEEN + DEVICES_SENSOR]:
        _LOGGER.info("device %s has already been added", (hostname))
        return

    # optimisation, if they have a platforms property, bail early on that
    if b"platforms" in data.properties:
        platforms = data.properties[b"platforms"].decode("utf8")
        _LOGGER.debug("device has platforms %s", platforms)
        if DEVICES_SENSOR not in platforms.split(","):
            _LOGGER.info("optimised config fetch out")
            return

    _LOGGER.info("addBJFsensor querying %s @ %s", hostname, host)
    wip.append(hostname)

    config = await async_do_query(host, "/json/config", True)

    if config != None:

        mac = config["mac"]

        # built early, in case it's shared
        rest = BJFRestData(hass, hostname, "GET", None, None, None)

        friendly_name = (
            config["friendlyName"] if "friendlyName" in config else config["name"]
        )

        # and add a datacoordinator
        coord = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=friendly_name + "_DUC",
            update_method=rest.async_bjfupdate,
            update_interval=timedelta(seconds=10),
        )

        # add a bunch of rest sensors
        if "sensorConfig" in config:
            for eachSensor in config["sensorConfig"]:
                for element in eachSensor["elements"]:
                    deviceClass = element["type"]
                    potential = None

                    # special case - if there's an instant sensor - PIR generally
                    if "impl" in element:

                        sensorValue = Template(
                            '{{ value_json["sensorState"]['
                            + str(eachSensor["sensor"])
                            + "].state"
                            + " }}",
                            hass,
                        )

                        _LOGGER.debug(sensorValue)

                        _LOGGER.info("Potential BJFBinarySensor")

                        potential = BJFBinarySensor(
                            hass,
                            coord,
                            element["impl"],
                            mac,
                            hostname,
                            rest,
                            # entity name
                            friendly_name
                            + " "
                            + eachSensor["name"]
                            + " "
                            + deviceClass,
                            deviceClass,
                            None,
                            sensorValue,
                            eachSensor["sensor"],
                            deviceClass,
                            config,
                        )

                    else:
                        _LOGGER.info("Potential BJFRestSensor")

                        # uom, round

                        uom = element["uom"] if "uom" in element else None
                        numDP = element["round"] if "round" in element else "0"

                        # build the template string
                        sensorValue = Template(
                            '{{ value_json["sensorState"]['
                            + str(eachSensor["sensor"])
                            + "]."
                            + deviceClass
                            + " | round("
                            + numDP
                            + ") }}",
                            hass,
                        )

                        _LOGGER.debug(sensorValue)

                        potential = BJFRestSensor(
                            hass,
                            coord,
                            mac,
                            hostname,
                            rest,
                            # entity name
                            friendly_name
                            + " "
                            + eachSensor["name"]
                            + " "
                            + deviceClass,
                            deviceClass,
                            uom,
                            sensorValue,
                            eachSensor["sensor"],
                            deviceClass,
                            config,
                        )

                    if potential is not None:
                        _LOGGER.info("Adding sensor %s", potential.unique_id)
                        sensorsToAdd.append(potential)

                        hass.data[DOMAIN][
                            BARNEYMAN_DEVICES_SEEN + DEVICES_SENSOR
                        ].append(hostname)

        await coord.async_config_entry_first_refresh()

    else:
        _LOGGER.error("Failed to query %s at onboarding - device not added", hostname)
        if hostname in data[BARNEYMAN_DEVICES]:
            data[BARNEYMAN_DEVICES].remove(hostname)

    wip.remove(hostname)

    if add_devices is not None:
        add_devices(sensorsToAdd)
        return True

    return False


# in py, vtable priority is left to right
class BJFRestSensor(CoordinatorEntity, BJFDeviceInfo, BJFFinder, RestSensor):
    def __init__(
        self,
        hass,
        coord,
        mac,
        hostname,
        rest,
        name,
        device_type,
        unit,
        jsonSensorQuery,
        ordinal,
        element,
        config,
    ):
        _LOGGER.info("Creating sensor.'%s' - '%s'", name, jsonSensorQuery)

        BJFFinder.__init__(self, hass, hostname)

        CoordinatorEntity.__init__(self, coord)

        # self,
        # coordinator,
        # rest,
        # name,
        # unit_of_measurement,
        # device_class,
        # state_class,
        # value_template,
        # json_attrs,
        # force_update,
        # resource_template,
        # json_attrs_path,

        RestSensor.__init__(
            # sensorclass
            self,
            coord,
            rest,
            name,
            unit,
            device_type,
            "measurement",
            value_template=jsonSensorQuery,
            json_attrs=None,
            force_update=True,
            resource_template=None,
            json_attrs_path=None,
        )
        BJFDeviceInfo.__init__(self, config, mac)

        # and subscribe for data updates
        self.async_on_remove(self.coordinator.async_add_listener(self.alertUpdate))

        self._unique_id = mac + "_sensor_" + str(ordinal) + "_" + element
        self._hostname = hostname
        self._hass = hass

    @property
    def unique_id(self):
        """Return unique ID for sensor."""
        return self._unique_id

    @callback
    def alertUpdate(self):
        self._update_from_rest_data()
        # if self._hass is not None:
        #     self._hass.add_job(self.async_subscribe,"sensor")


# inherit from a BinarySensorDevice so the icons work right
class BJFBinarySensor(BJFListener, BinarySensorEntity, BJFRestSensor):  # , ):
    def __init__(
        self,
        hass,
        coord,
        transport,
        mac,
        hostname,
        rest,
        name,
        device_type,
        unit,
        jsonData,
        ordinal,
        element,
        config,
    ):
        BJFRestSensor.__init__(
            self,
            hass,
            coord,
            mac,
            hostname,
            rest,
            name,
            device_type,
            unit,
            jsonData,
            ordinal,
            element,
            config,
        )

        BJFListener.__init__(self, transport, hass, hostname)

        self._name = name
        self._hass = hass
        self._ordinal = ordinal
        self._hostname = hostname
        self._deviceClass = device_type

        # # and subscribe for data updates
        # self.async_on_remove(
        #     self.coordinator.async_add_listener(self.async_parseData)
        # )

        self._is_on = None

    # sent from an announcer
    def handle_incoming_packet(self, data):
        payload = json.loads(data.decode("utf-8"))
        _LOGGER.debug(payload)
        self._is_on = payload["state"]
        _LOGGER.debug("About to set %s state to %s", self.entity_id, self.state)
        self._hass.states.set(self.entity_id, self.state)

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        _LOGGER.debug("is_on called %s state %s ", self.entity_id, self._state)
        return self._is_on

    # @property
    # def state(self):
    #     """Return the state of the binary sensor."""
    #     _LOGGER.debug("state called %s state %s ", self.entity_id, self._state)
    #     return self._is_on  # STATE_ON if self._is_on==True else STATE_OFF

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._deviceClass

    @callback
    def alertUpdate(self):
        # subscribe
        _LOGGER.info("doing binarysensor async_update")
        if self._hass is not None:
            self._hass.add_job(self.subscribe, "sensor")

        self._update_from_rest_data()
        if self.hass is not None:
            self.async_write_ha_state()

        _LOGGER.debug(
            "Got %s from %s using %s", self._state, self.rest.data, self._value_template
        )
        # work out my on state (._state is provided by the restsensor)
        self._is_on = self._state
