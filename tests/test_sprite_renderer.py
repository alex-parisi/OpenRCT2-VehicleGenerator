"""Render-dispatch helpers: worker-count selection and the serial/parallel split.

These don't touch Embree -- they decide how many threads to issue `render_view`
calls on and preserve sprite order. We stub the scene so they run anywhere.
"""

import numpy as np
from openrct2_vehicle_generator import sprite_renderer
from openrct2_vehicle_generator.sprite_renderer import _render_views, _render_workers
from openrct2_vehicle_generator.types import IndexedImage


class _CountingScene:
    """Records each view it renders so we can assert order is preserved."""

    def __init__(self):
        self.seen: list[float] = []

    def render_view(self, view):
        self.seen.append(float(view[0]))
        return IndexedImage.blank(1, 1)


def test_render_workers_env_override(monkeypatch):
    monkeypatch.setenv("OPENRCT2VG_RENDER_THREADS", "4")
    assert _render_workers() == 4


def test_render_workers_env_floor_is_one(monkeypatch):
    # max(1, int(env)) clamps zero/negative requests up to a single worker.
    monkeypatch.setenv("OPENRCT2VG_RENDER_THREADS", "0")
    assert _render_workers() == 1


def test_render_workers_invalid_env_falls_back(monkeypatch):
    # A non-integer override is ignored; we fall back to the cpu-count cap.
    monkeypatch.setenv("OPENRCT2VG_RENDER_THREADS", "not-a-number")
    monkeypatch.setattr(sprite_renderer.os, "cpu_count", lambda: 6)
    assert _render_workers() == 6


def test_render_workers_default_caps_at_eight(monkeypatch):
    monkeypatch.delenv("OPENRCT2VG_RENDER_THREADS", raising=False)
    monkeypatch.setattr(sprite_renderer.os, "cpu_count", lambda: 32)
    assert _render_workers() == 8


def test_render_workers_default_handles_unknown_cpu_count(monkeypatch):
    monkeypatch.delenv("OPENRCT2VG_RENDER_THREADS", raising=False)
    monkeypatch.setattr(sprite_renderer.os, "cpu_count", lambda: None)
    assert _render_workers() == 1


def test_render_views_serial_path(monkeypatch):
    # Force the single-worker branch: views render in order, no thread pool.
    monkeypatch.setenv("OPENRCT2VG_RENDER_THREADS", "1")
    scene = _CountingScene()
    views = [np.array([float(i)]) for i in range(4)]
    out = _render_views(scene, views)
    assert len(out) == 4
    assert scene.seen == [0.0, 1.0, 2.0, 3.0]


def test_render_views_empty_is_serial():
    # No views -> workers clamps to 0 -> serial branch returns an empty list.
    assert _render_views(_CountingScene(), []) == []


def test_render_views_parallel_preserves_order(monkeypatch):
    # With several workers and several views, ThreadPoolExecutor.map keeps order.
    monkeypatch.setenv("OPENRCT2VG_RENDER_THREADS", "4")
    scene = _CountingScene()
    views = [np.array([float(i)]) for i in range(6)]
    out = _render_views(scene, views)
    assert len(out) == 6
    assert sorted(scene.seen) == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
