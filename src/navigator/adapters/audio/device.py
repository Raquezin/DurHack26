import threading
from collections import deque

import sounddevice as sd

from navigator.domain.speech import SAMPLE_RATE_HZ, PcmChunk


class SoundDeviceAudioSink:
    def __init__(self, device: int | None = None, block_frames: int = 240):
        self._device = device
        self._block_frames = block_frames
        self._lock = threading.Lock()
        self._pending: deque[bytes] = deque()
        self._offset = 0
        self._stream: sd.RawOutputStream | None = None
        self._blocks_rendered = 0
        self._blocks_with_audio = 0

    def __enter__(self):
        self._stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE_HZ,
            channels=1,
            dtype="int16",
            device=self._device,
            blocksize=self._block_frames,
            latency="low",
            callback=self._callback,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, outdata, frames, time_info, status) -> None:
        need = frames * 2
        view = memoryview(outdata)[:need]
        filled = 0
        with self._lock:
            while filled < need and self._pending:
                head = self._pending[0]
                take = min(need - filled, len(head) - self._offset)
                view[filled:filled + take] = head[
                    self._offset:self._offset + take
                ]
                filled += take
                self._offset += take
                if self._offset == len(head):
                    self._pending.popleft()
                    self._offset = 0
        if filled < need:
            view[filled:] = bytes(need - filled)
        self._blocks_rendered += 1
        if filled:
            self._blocks_with_audio += 1

    def play(self, chunk: PcmChunk) -> None:
        with self._lock:
            self._pending.append(chunk.samples)

    def interrupt(self) -> None:
        with self._lock:
            self._pending.clear()
            self._offset = 0

    def is_playing(self) -> bool:
        with self._lock:
            return bool(self._pending)

    @property
    def blocks_with_audio(self) -> int:
        return self._blocks_with_audio

    @property
    def blocks_rendered(self) -> int:
        return self._blocks_rendered
