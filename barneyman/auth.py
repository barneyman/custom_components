import logging
from homeassistant import auth
from datetime import timedelta
from .barneymanconst import (
    DEVICES_LIGHT,
    DEVICES_SENSOR,
    DEVICES_CAMERA,
    LISTENING_PORT,
    AUTH_TOKEN,
    BARNEYMAN_DEVICES_SEEN,
    BARNEYMAN_DOMAIN,
    BARNEYMAN_USER_ID,
    BARNEYMAN_USER,
    BARNEYMAN_ID,
    BARNEYMAN_ANNOUNCE_CLIENT,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = BARNEYMAN_DOMAIN


async def async_prepareMemoryData(hass, myAuthToken, listeningPort, uniqueid):
    # create my 'i've created these' array
    hass.data[DOMAIN] = {
        AUTH_TOKEN: myAuthToken,
        LISTENING_PORT: listeningPort,
        BARNEYMAN_ID: uniqueid,
        BARNEYMAN_DEVICES_SEEN + DEVICES_LIGHT: [],
        BARNEYMAN_DEVICES_SEEN + DEVICES_SENSOR: [],
        BARNEYMAN_DEVICES_SEEN + DEVICES_CAMERA: [],
    }


# cribbed from https://github.com/home-assistant/core/blob/7cd68381f1d4f58930ffd631dfbfc7159d459832/tests/auth/test_init.py

# called by async_setup_entry
async def async_prepareUserAuth(hass, entry):

    # clean up
    # # TODO kill this BEGIN
    # users = await hass.auth.async_get_users()
    # for user in users:
    #     if user.name.startswith("barneyman"):
    #         _LOGGER.warning("removing %s", user.name)
    #         await hass.auth.async_remove_user(user)
    # # TODO kill this END

    # get my (previous) userid, or None if this is first time
    my_user_id = entry.data.get(BARNEYMAN_USER_ID, None)
    my_user = None

    # get user if we have an id
    if my_user_id is not None:
        # oooh get my user
        my_user = await hass.auth.async_get_user(my_user_id)
        _LOGGER.info("user %s found", my_user)

    # bootstrap - create a user
    if my_user is None:
        # create standard user (sys users cant have LLAT)
        my_user = await hass.auth.async_create_user(
            BARNEYMAN_USER, group_ids=[auth.const.GROUP_ID_USER]
        )
        _LOGGER.info("created user %s with id %s", my_user.name, my_user.id)

        # update the config entry
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, BARNEYMAN_USER_ID: my_user.id}
        )

    # if this user has refresh tokens, use the first one
    if my_user.refresh_tokens:
        refresh_token = list(my_user.refresh_tokens.values())[0]
    else:
        # otherwise create one
        _LOGGER.info("creating long lived access token")
        refresh_token = await hass.auth.async_create_refresh_token(
            user=my_user,
            client_name=BARNEYMAN_USER,
            token_type=auth.models.TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
            access_token_expiration=timedelta(weeks=520),
        )

    # generate an LLAT
    llat = hass.auth.async_create_access_token(refresh_token)

    # TODO remove this log
    _LOGGER.warning("got token %s", llat)

    # TODO
    # revoke this refresh token on unload and/or restart so that the
    # LLAT is also revoked

    # get my uniqueid from the entry
    uuid = entry.unique_id

    # set my memory data up
    await async_prepareMemoryData(hass, llat, 49152, uuid)
