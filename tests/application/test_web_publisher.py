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
                        kind=PreviewKind.DEPTH, frame_id=3, jpeg=b"\xff\xd8jpeg"
                    )
                )
                texts = []
                binary = None
                for _ in range(20):
                    message = await asyncio.wait_for(ws.receive(), 5)
                    if message.type == WSMsgType.TEXT:
                        texts.append(json.loads(message.data))
                    elif message.type == WSMsgType.BINARY:
                        binary = message.data
                    if texts and binary:
                        break
                assert any(t["type"] == "geometry" for t in texts)
                geometry = next(
                    t for t in texts if t["type"] == "geometry"
                )
                assert geometry["distances_m"] == [None, 1.5]
                assert binary is not None
                assert binary[0] == 2
                assert int.from_bytes(binary[1:9], "big") == 3
                assert binary[9:] == b"\xff\xd8jpeg"
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
