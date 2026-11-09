from unittest.mock import patch

import aiohttp

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


async def test_config_flow_lists_only_gps_trackers(hass: HomeAssistant):
    hass.states.async_set("device_tracker.phone", "home", {"source_type": "gps", "latitude": 1, "longitude": 2})
    hass.states.async_set("device_tracker.nogpsattr", "home", {"latitude": 1, "longitude": 2})
    hass.states.async_set("device_tracker.router_pc", "home", {"source_type": "router"})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    selector = r["data_schema"].schema["device"]
    assert sorted(selector.config["include_entities"]) == [
        "device_tracker.nogpsattr",
        "device_tracker.phone",
    ]


async def test_config_flow(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(URL, status=200)
    hass.states.async_set("device_tracker.iphone13", "home", {"source_type": "gps", "latitude": 1, "longitude": 2})
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


async def test_reconfigure_changes_device_and_token(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    hass.states.async_set(
        "device_tracker.other", "home",
        {"source_type": "gps", "latitude": 49.0, "longitude": 12.0},
    )
    aioclient_mock.get(URL, status=200)

    r = await entry.start_reconfigure_flow(hass)
    assert r["type"] == FlowResultType.FORM and r["step_id"] == "reconfigure"
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {"url": URL, "api_key": "newtok", "device": "device_tracker.other"},
    )
    assert r["type"] == FlowResultType.ABORT and r["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert entry.unique_id == "device_tracker.other"
    assert entry.title == "Reitti (device_tracker.other)"
    url = aioclient_mock.mock_calls[-1][1]
    assert url.query["token"] == "newtok"
    assert aioclient_mock.mock_calls[-1][2]["lat"] == 49.0


async def test_reconfigure_clears_shadowing_options(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    hass.config_entries.async_update_entry(
        entry, options={"api_key": "old", "device": "device_tracker.iphone13", "interval_seconds": 60}
    )
    await hass.async_block_till_done()
    hass.states.async_set("device_tracker.other", "home", {"source_type": "gps", "latitude": 1, "longitude": 2})
    aioclient_mock.get(URL, status=200)

    r = await entry.start_reconfigure_flow(hass)
    await hass.config_entries.flow.async_configure(
        r["flow_id"], {"url": URL, "api_key": "fresh", "device": "device_tracker.other"}
    )
    await hass.async_block_till_done()
    assert entry.options == {"interval_seconds": 60}  # kept, but url/token/device dropped
    assert entry.runtime_data._opts["device"] == "device_tracker.other"
    assert entry.runtime_data._opts["api_key"] == "fresh"


async def test_reconfigure_rejects_device_used_by_other_entry(hass, aioclient_mock):
    first = await _setup(hass, aioclient_mock)
    second = MockConfigEntry(
        domain=DOMAIN, data={**DATA, "device": "device_tracker.other"}, unique_id="device_tracker.other"
    )
    second.add_to_hass(hass)
    hass.states.async_set("device_tracker.other", "home", {"source_type": "gps", "latitude": 1, "longitude": 2})
    aioclient_mock.get(URL, status=200)

    r = await first.start_reconfigure_flow(hass)
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"url": URL, "api_key": "tok", "device": "device_tracker.other"}
    )
    assert r["type"] == FlowResultType.ABORT and r["reason"] == "already_configured"
    assert first.unique_id == "device_tracker.iphone13"


async def test_reconfigure_connection_error(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, exc=aiohttp.ClientError)
    r = await entry.start_reconfigure_flow(hass)
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"url": URL, "api_key": "tok", "device": "device_tracker.iphone13"}
    )
    assert r["type"] == FlowResultType.FORM and r["errors"] == {"base": "cannot_connect"}
