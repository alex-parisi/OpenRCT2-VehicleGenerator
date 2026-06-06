"""Tests for the CLI entrypoint (__main__).

`main` is a thin wrapper over the renderer's shared `run_cli`; `_render`
dispatches between the test-render and full-export paths. We stub the heavy
collaborators (context creation, ride export) so the dispatch logic is covered
without Embree or disk rendering.
"""

import argparse
import types

from openrct2_vehicle_generator import __main__ as cli


def _args(input_path, test=False, skip_render=False):
    return argparse.Namespace(input=input_path, test=test, skip_render=skip_render)


def _patch_build_ride(monkeypatch):
    monkeypatch.setattr(cli, "load_meshes", lambda root: [])
    monkeypatch.setattr(cli, "load_preview", lambda root: None)
    monkeypatch.setattr(
        cli, "build_ride", lambda root, meshes, preview: types.SimpleNamespace(units_per_tile=32.0)
    )


def _patch_common(monkeypatch, calls):
    _patch_build_ride(monkeypatch)
    monkeypatch.setattr(
        cli, "make_context", lambda lights, upt, test: ("ctx", upt, test)
    )
    monkeypatch.setattr(cli, "output_directory_of", lambda root: "out-dir")

    def fake_export_ride(ride, ctx, out, skip_render):
        calls["export"] = {"ctx": ctx, "out": out, "skip_render": skip_render}

    def fake_export_ride_test(ride, ctx):
        calls["export_test"] = {"ctx": ctx}

    monkeypatch.setattr(cli, "export_ride", fake_export_ride)
    monkeypatch.setattr(cli, "export_ride_test", fake_export_ride_test)


def test_render_full_export_path(monkeypatch):
    calls = {}
    _patch_common(monkeypatch, calls)
    cli._render(_args("ride.json", skip_render=True), {}, [])
    assert "export_test" not in calls
    assert calls["export"]["out"] == "out-dir"
    assert calls["export"]["skip_render"] is True
    # make_context was told this is not a test render.
    assert calls["export"]["ctx"] == ("ctx", 32.0, False)


def test_render_test_path(monkeypatch):
    calls = {}
    _patch_common(monkeypatch, calls)
    cli._render(_args("ride.json", test=True), {}, [])
    assert "export" not in calls
    assert calls["export_test"]["ctx"] == ("ctx", 32.0, True)


def test_main_delegates_to_run_cli(monkeypatch):
    captured = {}

    def fake_run_cli(prog, argv, render):
        captured["prog"] = prog
        captured["argv"] = argv
        captured["render"] = render
        return 0

    monkeypatch.setattr(cli, "run_cli", fake_run_cli)
    rc = cli.main(["ride.json"])
    assert rc == 0
    assert captured["prog"] == "openrct2-vehicle-generator"
    assert captured["argv"] == ["ride.json"]
    assert captured["render"] is cli._render


def test_main_returns_run_cli_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "run_cli", lambda prog, argv, render: 1)
    assert cli.main([]) == 1


def test_main_end_to_end_through_run_cli(monkeypatch, tmp_path):
    # Drive the real run_cli (arg parsing + config read + lights) but stub the
    # render side, so the wiring from main -> run_cli -> _render is covered.
    cfg = tmp_path / "ride.json"
    cfg.write_text("{}")

    _patch_build_ride(monkeypatch)
    monkeypatch.setattr(cli, "make_context", lambda lights, upt, test: "ctx")
    monkeypatch.setattr(cli, "output_directory_of", lambda root: tmp_path)

    seen = {}
    monkeypatch.setattr(
        cli, "export_ride", lambda ride, ctx, out, skip_render: seen.setdefault("ran", True)
    )
    assert cli.main([str(cfg)]) == 0
    assert seen["ran"] is True


def test_dunder_main_guard_invokes_sys_exit(monkeypatch):
    # Cover the `sys.exit(main())` body inside `if __name__ == "__main__":`.
    # runpy re-executes __main__.py with __name__ == "__main__", so the guard
    # fires.  We patch run_cli (imported by the module at execution time) to
    # return a known code and capture sys.exit so the process doesn't actually
    # exit.
    import runpy
    import sys

    exits = []
    monkeypatch.setattr(sys, "exit", exits.append)

    import openrct2_object_common.cli as _cli
    monkeypatch.setattr(_cli, "run_cli", lambda prog, argv, render: 7)

    sys.modules.pop("openrct2_vehicle_generator.__main__", None)
    runpy.run_module("openrct2_vehicle_generator", run_name="__main__")

    assert exits == [7]
