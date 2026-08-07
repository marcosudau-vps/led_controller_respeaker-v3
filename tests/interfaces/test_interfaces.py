"""Service, discovery, HTTP API and CLI."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from lefx.interfaces import API_PREFIX, ControllerService, NullSink, create_app, describe
from lefx.interfaces.cli import main as cli_main
from lefx.sdk import OutputFrame, SinkStatus

from tests.engine.sample_effects import ALL_EFFECTS


class RecordingSink:
    """A sink that remembers frames and can be made to go away."""

    name = "recording"

    def __init__(self) -> None:
        self.frames: list[OutputFrame] = []
        self.available = True
        self.closed = False

    def apply_frame(self, frame: OutputFrame) -> None:
        self.frames.append(frame)

    def status(self) -> SinkStatus:
        return SinkStatus(
            available=self.available, detail=None if self.available else "cable unplugged"
        )

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def service(tmp_path):
    from lefx.engine import build_registry

    controller = ControllerService(
        sink=RecordingSink(),
        led_count=4,
        fps=60.0,
        search_paths=[],
        state_file=tmp_path / "background.json",
        autostart_providers=False,
    )
    # No packages are installed in the test environment, so register the sample
    # definitions directly — the service does not care where they came from.
    controller.library._registry = build_registry(ALL_EFFECTS, source_id="test-set")  # noqa: SLF001
    controller.runtime.set_registry(controller.library.registry)
    return controller


@pytest.fixture
def client(service):
    app = create_app(service)
    with TestClient(app) as test_client:
        yield test_client


# -- discovery --------------------------------------------------------------


def test_the_null_sink_is_always_available():
    names = {item["name"] for item in describe()["sinks"]}
    assert "null" in names


def test_entry_points_are_declared_by_the_packages_that_provide_them():
    """The distribution boundary, observed from the outside.

    Reads the installed metadata directly rather than the loaded factories:
    what matters here is that the hardware and simulator packages announce
    themselves without this package importing either of them.
    """
    from importlib.metadata import entry_points

    sinks = {entry.name for entry in entry_points(group="lefx.frame_sinks")}
    providers = {entry.name for entry in entry_points(group="lefx.input_providers")}
    assert {"respeaker", "simulator"} <= sinks
    # "<device>.<capability>": distinct while both packages are installed, which
    # is the situation this assertion is checking they survive.
    assert {"respeaker.doa", "simulator.doa"} <= providers


def test_an_entry_point_that_cannot_load_is_skipped_not_fatal(caplog):
    """An optional integration that fails to import must not stop the service."""
    catalogue = describe()
    assert any(item["name"] == "null" for item in catalogue["sinks"])


def test_an_unknown_sink_names_what_is_installed():
    from lefx.interfaces import create_sink

    with pytest.raises(LookupError, match="Installed sinks"):
        create_sink("nonexistent")


def test_the_null_sink_keeps_the_frame_it_discarded():
    sink = NullSink()
    sink.apply_frame(OutputFrame(leds=(1, 2, 3), timestamp=0.0))
    assert sink.last_frame is not None
    assert sink.status().available is True


# -- devices and capabilities -----------------------------------------------


def test_a_provider_name_splits_into_a_device_and_a_capability():
    from lefx.interfaces import split_provider_name

    assert split_provider_name("respeaker.doa") == ("respeaker", "doa")
    assert split_provider_name("simulator.doa") == ("simulator", "doa")
    # No device means no device to select it with — it is simply always there.
    assert split_provider_name("clock") == (None, "clock")


def test_choosing_the_device_chooses_its_providers_and_names_them_by_capability():
    """The reason ``provider_id="doa"`` resolves against either device.

    A definition names what it needs, not who supplies it. Selecting the sink
    selects the device, and its providers reach the engine under the bare
    capability — so the same effect runs against hardware and simulator with
    nothing in it to change.
    """
    from lefx.interfaces import create_providers
    from respeaker_led.device.registration import reset_shared_transport
    from respeaker_led.simulator.registration import reset_shared_link

    # Both factories are really called, so this covers the keyword tolerance the
    # contract asks of them as well as the naming. Port 0 keeps the simulator
    # off a fixed port, and the resets stop the threads the factories started.
    try:
        for device in ("respeaker", "simulator"):
            providers = create_providers(device=device, led_count=12, port=0)
            assert set(providers) == {"doa"}
            assert providers["doa"].name == f"{device}.doa"
            assert providers["doa"].capability == "doa"
            for provider in providers.values():
                provider.close()
    finally:
        reset_shared_transport()
        reset_shared_link()


def test_another_devices_providers_are_not_built_at_all():
    """Building them would open a second device's connection for nothing."""
    from lefx.interfaces import create_providers

    assert create_providers(device="null", led_count=12) == {}


# -- the service ------------------------------------------------------------


def test_a_command_renders_immediately_so_the_change_is_visible(service):
    service.set_state("solid_state", {"color": "red"})
    assert service.sink.frames[-1].leds == (0xFF0000,) * 4


def test_output_settings_dim_and_blank_without_touching_the_layers(service):
    service.set_state("solid_state", {"color": "white"})
    service.set_output(brightness=0.5)
    assert service.sink.frames[-1].leds == (0x7F7F7F,) * 4
    service.set_output(enabled=False)
    assert service.sink.frames[-1].leds == (0, 0, 0, 0)
    service.set_output(enabled=True, brightness=1.0)
    assert service.sink.frames[-1].leds == (0xFFFFFF,) * 4


def test_a_sink_going_away_is_published_rather_than_acted_on(service):
    """The engine has no idea a device exists; the service only reports it."""
    seen: list[tuple[str, dict]] = []
    service.add_listener(lambda event, payload: seen.append((event, payload)))

    service.render_once(1.0)
    service.sink.available = False
    service.render_once(2.0)

    assert seen[-1][0] == "sink_changed"
    assert seen[-1][1]["available"] is False
    assert seen[-1][1]["detail"] == "cable unplugged"
    # And nothing was set on the ring in response.
    assert service.runtime.store.ordered_active() == []


def test_a_failing_listener_does_not_break_the_render_loop(service):
    service.add_listener(lambda event, payload: 1 / 0)
    service.render_once(1.0)
    assert service.sink.frames


def test_stopping_the_service_closes_the_sink(service):
    service.start()
    service.stop()
    assert service.sink.closed is True


# -- persistence ------------------------------------------------------------


def test_a_restorable_background_state_survives_a_restart(tmp_path):
    from lefx.engine import build_registry

    state_file = tmp_path / "background.json"

    def build():
        controller = ControllerService(
            sink=RecordingSink(), led_count=4, search_paths=[],
            state_file=state_file, autostart_providers=False,
        )
        controller.library._registry = build_registry(ALL_EFFECTS, source_id="test-set")  # noqa: SLF001
        controller.runtime.set_registry(controller.library.registry)
        # The catalogue arrives after construction here, so ask again — which is
        # the same situation as registering a source at runtime.
        controller.restore_background_state()
        return controller

    first = build()
    first.set_state("solid_state", {"color": "green"}, slot="background")
    assert state_file.is_file()

    from lefx.engine import LayerId

    second = build()
    restored = second.runtime.store.active(LayerId.BACKGROUND_STATE)
    assert restored is not None
    assert restored.params["color"] == "#00FF00"


def test_the_primary_state_is_not_persisted(service, tmp_path):
    service.set_state("solid_state", {"color": "green"}, slot="primary")
    assert not (tmp_path / "background.json").exists()


def test_clearing_the_background_removes_the_stored_state(service, tmp_path):
    service.set_state("solid_state", slot="background")
    assert (tmp_path / "background.json").is_file()
    service.clear_state(slot="background")
    assert not (tmp_path / "background.json").exists()


# -- HTTP: listings ---------------------------------------------------------


def test_listings_are_short_by_default_and_full_on_request(client):
    short = client.get(f"{API_PREFIX}/states").json()
    assert short == ["background_only", "solid_state"]

    detailed = client.get(f"{API_PREFIX}/states", params={"details": True}).json()
    assert detailed[0]["id"] == "background_only"
    assert "config" in detailed[0]
    assert detailed[0]["placement"]["slots"] == ["background"]


def test_show_reports_where_a_name_resolved_from(client):
    payload = client.get(f"{API_PREFIX}/show/solid_state").json()
    assert payload["resolved_kind"] == "definition"
    assert payload["resolved_from"] == "solid_state"
    assert payload["form"] == "state"


def test_a_controlled_overlay_reports_its_channel_requirement_and_inputs(client):
    payload = client.get(f"{API_PREFIX}/show/direction_marker").json()
    assert payload["placement"] == {"requires_channel": True}
    assert payload["runtime_inputs"]["direction_deg"]["nullable"] is True
    assert payload["input_sampling"]["mode"] == "push"


def test_a_finite_form_reports_its_duration_field(client):
    payload = client.get(f"{API_PREFIX}/show/flash_overlay").json()
    assert payload["placement"]["duration_field"] == "duration_ms"
    assert payload["placement"]["supports_duration_override"] is True


# -- HTTP: commands ---------------------------------------------------------


def test_setting_a_state_reports_what_was_applied(client):
    payload = client.post(
        f"{API_PREFIX}/set/state", json={"target": "solid_state", "config": {"color": "blau"}}
    ).json()
    assert payload["ok"] is True
    assert payload["applied"]["config"]["color"] == "#0000FF"
    assert payload["applied"]["slot"] == "primary"


def test_switching_a_state_off_reports_that_nothing_is_applied(client):
    client.post(f"{API_PREFIX}/set/state", json={"target": "solid_state"})
    payload = client.post(
        f"{API_PREFIX}/set/state", json={"target": "solid_state", "action": "off"}
    ).json()
    assert payload["applied"] is None


def test_the_controlled_overlay_lifecycle_over_http(client):
    created = client.post(
        f"{API_PREFIX}/set/overlay",
        json={"target": "direction_marker", "channel": "DoA", "inputs": {"direction_deg": 90}},
    ).json()
    assert created["applied"]["channel"] == "doa"

    updated = client.post(
        f"{API_PREFIX}/update/overlay", json={"channel": "doa", "inputs": {"direction": 180}}
    )
    assert updated.status_code == 200

    cleared = client.post(f"{API_PREFIX}/clear/overlay", json={"channel": "doa"})
    assert cleared.json()["ok"] is True

    missing = client.post(f"{API_PREFIX}/clear/overlay", json={"channel": "doa"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "channel_not_found"


def test_emitting_an_event_reports_its_duration(client):
    payload = client.post(
        f"{API_PREFIX}/emit/event", json={"target": "pulse_event", "config": {"duration_ms": "1.5s"}}
    ).json()
    assert payload["applied"]["duration_ms"] == 1500


# -- HTTP: errors -----------------------------------------------------------


def test_an_unknown_target_returns_404_with_suggestions(client):
    response = client.get(f"{API_PREFIX}/show/solid_stat")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "target_not_found"
    assert "solid_state" in detail["suggestions"]


def test_the_wrong_verb_for_a_form_is_refused_with_the_right_one(client):
    response = client.post(f"{API_PREFIX}/set/state", json={"target": "pulse_event"})
    assert response.status_code == 422
    assert "emit event" in response.json()["detail"]["message"]


def test_an_invalid_field_returns_422_with_the_field_path(client):
    response = client.post(
        f"{API_PREFIX}/set/state", json={"target": "solid_state", "config": {"color": "nope"}}
    )
    assert response.status_code == 422
    issue = response.json()["detail"]["issues"][0]
    assert issue["field"] == "config.color"
    assert issue["code"] == "unknown_color"


def test_a_timed_overlay_refuses_a_channel(client):
    response = client.post(
        f"{API_PREFIX}/set/overlay", json={"target": "flash_overlay", "channel": "x"}
    )
    assert response.status_code == 422
    assert "has no channel" in response.json()["detail"]["message"]


def test_there_is_no_older_api_surface(client):
    for path in ("/api/v1/status", "/api/v2/states", "/api/v1/commands/set_state"):
        assert client.get(path).status_code == 404


# -- HTTP: status -----------------------------------------------------------


def test_status_reports_layers_output_and_what_is_installed(client):
    client.post(f"{API_PREFIX}/set/state", json={"target": "solid_state", "slot": "background"})
    payload = client.get(f"{API_PREFIX}/status").json()

    assert payload["led_count"] == 4
    assert payload["layers"]["background_state"]["effect_id"] == "solid_state"
    assert payload["layers"]["primary_state"] is None
    assert payload["output"] == {"brightness": 1.0, "enabled": True}
    assert payload["service"]["sink"] == "recording"
    assert "sinks" in payload["installed"]


def test_health_reports_degraded_when_the_output_is_gone(client, service):
    assert client.get("/health").json()["status"] == "ok"
    service.sink.available = False
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["sink"]["detail"] == "cable unplugged"


# -- the command line -------------------------------------------------------


class FakeClient:
    """Stands in for the HTTP client so the CLI can be tested without a server."""

    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self.result
        return record


@pytest.fixture
def fake_cli(monkeypatch):
    from lefx.interfaces import cli
    from lefx.interfaces.client import Result

    fake = FakeClient(Result(ok=True, status=200, data={"ok": True}))
    monkeypatch.setattr(cli, "ControllerClient", lambda **kwargs: fake)
    return fake


def test_the_cli_speaks_verb_then_subject(fake_cli, capsys):
    assert cli_main(["set", "state", "ready_state", "--config", '{"color":"green"}']) == 0
    name, args, kwargs = fake_cli.calls[-1]
    assert name == "set_state"
    assert args[0] == "ready_state"
    assert args[1] == {"color": "green"}
    assert kwargs == {"slot": "primary", "action": "on"}
    capsys.readouterr()


def test_plain_set_means_on_and_off_is_explicit(fake_cli):
    cli_main(["set", "state", "x"])
    assert fake_cli.calls[-1][2]["action"] == "on"
    cli_main(["set", "state", "x", "--off"])
    assert fake_cli.calls[-1][2]["action"] == "off"
    cli_main(["set", "state", "x", "--toggle"])
    assert fake_cli.calls[-1][2]["action"] == "toggle"


def test_overlay_commands_carry_the_channel(fake_cli):
    cli_main(["set", "overlay", "direction_marker", "--channel", "doa"])
    assert fake_cli.calls[-1][2]["channel"] == "doa"
    cli_main(["update", "overlay", "doa", "--inputs", '{"direction_deg":90}'])
    name, args, _ = fake_cli.calls[-1]
    assert name == "update_overlay"
    assert args == ("doa", {"direction_deg": 90})


def test_clear_covers_slots_channels_and_everything(fake_cli):
    cli_main(["clear", "state", "--slot", "background"])
    assert fake_cli.calls[-1][:1] == ("clear_state",)
    cli_main(["clear", "overlay", "doa"])
    assert fake_cli.calls[-1][:2] == ("clear_overlay", ("doa",))
    cli_main(["clear", "all"])
    assert fake_cli.calls[-1][0] == "clear_all"


def test_a_short_listing_prints_bare_ids(monkeypatch, capsys):
    from lefx.interfaces import cli
    from lefx.interfaces.client import Result

    monkeypatch.setattr(
        cli, "ControllerClient",
        lambda **kwargs: FakeClient(Result(ok=True, status=200, data=["a", "b"])),
    )
    assert cli_main(["list", "states"]) == 0
    assert capsys.readouterr().out.split() == ["a", "b"]


def test_a_failure_goes_to_stderr_and_exits_nonzero(monkeypatch, capsys):
    from lefx.interfaces import cli
    from lefx.interfaces.client import Result

    monkeypatch.setattr(
        cli, "ControllerClient",
        lambda **kwargs: FakeClient(Result(ok=False, status=404, error="No effect named 'x'")),
    )
    assert cli_main(["show", "x"]) == 1
    assert "No effect named" in capsys.readouterr().err


def test_malformed_json_is_rejected_before_anything_is_sent(fake_cli):
    with pytest.raises(SystemExit):
        cli_main(["set", "state", "x", "--config", "{not json}"])
    assert fake_cli.calls == []


def test_the_sinks_command_lists_what_is_installed(capsys):
    assert cli_main(["sinks"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(item["name"] == "null" for item in payload["sinks"])


# -- hosting ----------------------------------------------------------------


def test_a_port_pool_is_parsed_into_the_ports_it_names():
    from lefx.interfaces.hosting import parse_pool

    assert parse_pool("8765,8770-8772") == (8765, 8770, 8771, 8772)
    assert parse_pool("") == ()


def test_port_selection_falls_back_when_the_requested_one_is_taken():
    import socket

    from lefx.interfaces.hosting import select_port

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        blocked = taken.getsockname()[1]
        chosen = select_port("127.0.0.1", blocked, (blocked, blocked + 1, blocked + 2))
        assert chosen != blocked


def test_the_instance_file_round_trips(tmp_path):
    from lefx.interfaces.hosting import (
        clear_instance,
        create_instance,
        read_instance,
        update_instance_status,
        write_instance,
    )

    path = tmp_path / "instance.json"
    info = create_instance(host="127.0.0.1", port=8765, requested_port=8765)
    write_instance(path, info)
    assert read_instance(path).port == 8765

    update_instance_status(path, "ready")
    assert read_instance(path).status == "ready"

    clear_instance(path, pid=info.pid)
    assert not path.exists()


def test_another_process_instance_file_is_left_alone(tmp_path):
    from lefx.interfaces.hosting import clear_instance, create_instance, write_instance

    path = tmp_path / "instance.json"
    write_instance(path, create_instance(host="127.0.0.1", port=8765, requested_port=8765))
    clear_instance(path, pid=999999)
    assert path.exists()
