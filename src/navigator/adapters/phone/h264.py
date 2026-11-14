import av
from av.codec.context import Flags
from av.error import FFmpegError


class H264Decoder:
    def __init__(self) -> None:
        self._context = _open()

    def decode(self, access_unit: bytes):
        try:
            frames = self._context.decode(av.Packet(access_unit))
        except FFmpegError:
            frames = []
        if not frames:
            self._context = _open()
            return None
        return frames[-1]


def _open():
    context = av.CodecContext.create("h264", "r")
    context.thread_count = 1
    context.flags |= Flags.low_delay
    return context
