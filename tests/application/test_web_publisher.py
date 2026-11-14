import asyncio
import json
import threading

import pytest
from aiohttp import ClientSession, WSMsgType
from aiohttp.test_utils import unused_port

from navigator.adapters.ui.web import WebEventPublisher
from navigator.domain.events import (
    GeometryEvent,
    Outcome,
    PreviewEvent,
    PreviewKind,
    UtteranceEvent,
)
from navigator.domain.speech import Priority


async def _serve():
    port = unused_port()
    publisher = WebEventPublisher(host="127.0.0.1", port=port)
    await publisher.__aenter__()
    return publisher, publisher.bound_port or port


async def test_ws_receives_json_and_binary_preview():
    publisher, port = await _serve()
    try:
        async with ClientSession() as session:
            async with session.ws_connect(
                f"http://127.0.0.1:{port}/ws"
            ) as ws:
                await asyncio.sleep(0.05)
                threading.Thread(
                    target=publisher.publish,
                    args=(
                        GeometryEvent(
                            frame_id=3,
                            distances_m=(float("inf"), 1.5),
                            valid=(False, True),
                            age_ms=4.0,
                        ),
                    ),
                    daemon=True,
                ).start()
                publisher.publish(
                    PreviewEvent(
                        kind=PreviewKind.CAMERA, frame_id=3, jpeg=b"\xff\xd8jpeg"
                    )
                )
                publisher.publish(
                    PreviewEvent(
                        kind=PreviewKind.DEPTH, frame_id=3, jpeg=b"\xff\xd8depth"
                    )
                )
                texts = []
                binaries = []
                for _ in range(20):
                    message = await asyncio.wait_for(ws.receive(), 5)
                    if message.type == WSMsgType.TEXT:
                        texts.append(json.loads(message.data))
                    elif message.type == WSMsgType.BINARY:
                        binaries.append(message.data)
                    if texts and len(binaries) == 2:
                        break
                assert any(t["type"] == "geometry" for t in texts)
                geometry = next(
                    t for t in texts if t["type"] == "geometry"
                )
                assert geometry["distances_m"] == [None, 1.5]
                assert len(binaries) == 2
                assert binaries[0][0] == 1
                assert binaries[0][9:] == b"\xff\xd8jpeg"
                assert binaries[1][0] == 2
                assert binaries[1][9:] == b"\xff\xd8depth"
                for binary in binaries:
                    assert int.from_bytes(binary[1:9], "big") == 3
    finally:
        await publisher.__aexit__(None, None, None)


async def test_previews_wait_for_acks_and_keep_the_newest():
    publisher, port = await _serve()
    try:
        async with ClientSession() as session:
            async with session.ws_connect(
                f"http://127.0.0.1:{port}/ws"
            ) as ws:
                await asyncio.sleep(0.05)

                def preview(frame_id):
                    return PreviewEvent(
                        kind=PreviewKind.CAMERA,
                        frame_id=frame_id,
                        jpeg=b"jpeg",
                    )

                for frame_id in (1, 2):
                    publisher.publish(preview(frame_id))
                    message = await asyncio.wait_for(ws.receive(), 5)
                    assert message.type == WSMsgType.BINARY
                    assert int.from_bytes(message.data[1:9], "big") == frame_id
                for frame_id in (3, 4, 5):
                    publisher.publish(preview(frame_id))
                    await asyncio.sleep(0.05)
                publisher.publish(
                    GeometryEvent(
                        frame_id=5,
                        distances_m=(1.0,),
                        valid=(True,),
                        age_ms=1.0,
                    )
                )
                message = await asyncio.wait_for(ws.receive(), 5)
                assert message.type == WSMsgType.TEXT
                assert json.loads(message.data)["type"] == "geometry"
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(ws.receive(), 0.3)
                await ws.send_str("ack")
                message = await asyncio.wait_for(ws.receive(), 5)
                assert message.type == WSMsgType.BINARY
                assert int.from_bytes(message.data[1:9], "big") == 5
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(ws.receive(), 0.3)
    finally:
        await publisher.__aexit__(None, None, None)


async def test_publish_without_clients_does_not_block():
    publisher, _ = await _serve()
    try:
        publisher.publish(
            UtteranceEvent(
                text="Stop.",
                priority=Priority.HAZARD,
                outcome=Outcome.SPOKEN,
                age_ms=1.0,
            )
        )
    finally:
        await publisher.__aexit__(None, None, None)


async def test_priority_serialised_by_name():
    publisher, port = await _serve()
    try:
        async with ClientSession() as session:
            async with session.ws_connect(
                f"http://127.0.0.1:{port}/ws"
            ) as ws:
                await asyncio.sleep(0.05)
                publisher.publish(
                    UtteranceEvent(
                        text="Stop.",
                        priority=Priority.HAZARD,
                        outcome=Outcome.SPOKEN,
                        age_ms=1.0,
                    )
                )
                message = await asyncio.wait_for(ws.receive(), 5)
                payload = json.loads(message.data)
                assert payload["priority"] == "hazard"
                assert payload["outcome"] == "spoken"
    finally:
        await publisher.__aexit__(None, None, None)


async def test_index_served():
    publisher, port = await _serve()
    try:
        async with ClientSession() as session:
            async with session.get(
                f"http://127.0.0.1:{port}/"
            ) as response:
                assert response.status == 200
                body = await response.text()
                assert "app.js" in body
    finally:
        await publisher.__aexit__(None, None, None)
