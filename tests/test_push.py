from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reitti_tracker.const import DOMAIN

URL = "http://reitti.test:8080"
ENDPOINT = f"{URL}/api/v1/ingest/owntracks"
DATA = {"url": URL, "api_key": "tok", "device": "device_tracker.iphone13"}


async def _setup(hass, aioclient_mock, status=200):
    aioclient_mock.post(ENDPOINT, status=status, json={"result": "ok"})
    hass.states.async_set(
        "device_tracker.iphone13",
        "not_home",
        {"latitude": 48.2, "longitude": 11.5, "gps_accuracy": 5, "altitude": 500},
    )
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id=DATA["device"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(URL, status=200)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert r["type"] == FlowResultType.FORM
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {**DATA, "url": "reitti.test:8080"}
    )
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["data"]["url"] == "http://reitti.test:8080"


async def test_push_payload(hass, aioclient_mock):
    await _setup(hass, aioclient_mock)
    call = aioclient_mock.mock_calls[-1]
    method, url, body, headers = call
    print("URL:", url, "BODY:", body)
    assert str(url).startswith(ENDPOINT) and url.query["token"] == "tok"
    assert body["_type"] == "location" and body["tid"] == "IP"
    assert body["lat"] == 48.2 and body["lon"] == 11.5
    assert isinstance(body["tst"], int)


async def test_push_now_service_and_500(hass, aioclient_mock, caplog):
    await _setup(hass, aioclient_mock, status=500)
    n = len(aioclient_mock.mock_calls)
    await hass.services.async_call(DOMAIN, "push_now", blocking=True)
    assert len(aioclient_mock.mock_calls) == n + 1
    assert "rejected push: 500" in caplog.text


async def test_state_change_pushes(hass, aioclient_mock):
    await _setup(hass, aioclient_mock)
    n = len(aioclient_mock.mock_calls)
    hass.states.async_set("device_tracker.iphone13", "home", {"latitude": 48.3, "longitude": 11.6})
    await hass.async_block_till_done()
    assert len(aioclient_mock.mock_calls) == n + 1


async def test_unload_removes_service(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.services.has_service(DOMAIN, "push_now")


async def test_options_change_token(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    aioclient_mock.get(URL, status=200)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        {"url": URL, "api_key": "newtok", "enable_push": True, "interval_seconds": 30},
    )
    assert r["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert aioclient_mock.mock_calls[-1][1].query["token"] == "newtok"
