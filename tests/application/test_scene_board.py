import asyncio
import threading

from navigator.application.scene_board import SceneBoard
from navigator.domain.geometry import Perception, SceneGeometry


def perception(frame_id):
    geometry = SceneGeometry(
        frame_id=frame_id,
        t_capture_ns=frame_id,
        rows=1,
        cols=1,
        distances_m=(1.0,),
        valid=(True,),
        horizontal_fov_deg=70.0,
    )
    return Perception(
        geometry=geometry,
        t_ready_ns=frame_id,
        camera_jpeg=None,
        depth_jpeg=None,
    )


def test_latest_returns_newest():
    board = SceneBoard()
    assert board.latest() is None
    board.put(perception(1))
    board.put(perception(2))
    assert board.latest().geometry.frame_id == 2


async def test_wait_newer_returns_immediately_when_newer():
    board = SceneBoard()
    board.put(perception(3))
    result = await board.wait_newer(2, timeout_s=0.1)
    assert result.geometry.frame_id == 3


async def test_wait_newer_times_out():
    board = SceneBoard()
    board.put(perception(1))
    assert await board.wait_newer(1, timeout_s=0.01) is None


async def test_wait_newer_wakes_from_other_thread():
    board = SceneBoard()
    waiter = asyncio.ensure_future(board.wait_newer(0, timeout_s=2.0))
    await asyncio.sleep(0.05)
    threading.Thread(
        target=board.put, args=(perception(9),), daemon=True
    ).start()
    result = await waiter
    assert result.geometry.frame_id == 9
