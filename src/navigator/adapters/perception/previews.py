import torch
import torch.nn.functional as F
from torchvision.io import encode_jpeg

from navigator.adapters.perception.palette import DEPTH_RANGE_M, depth_palette

PREVIEW_LONG_SIDE = 512
JPEG_QUALITY = 80


class PreviewEncoder:
    def __init__(self, device: torch.device) -> None:
        self._palette = torch.from_numpy(depth_palette()).to(device)

    def encode(
        self, rgb: torch.Tensor, depth: torch.Tensor, usable: torch.Tensor
    ) -> tuple[bytes, bytes]:
        size = _preview_size(*depth.shape)
        camera = F.interpolate(
            rgb[None].float(), size=size, mode="bilinear", antialias=True
        )[0].round().clamp(0, 255).to(torch.uint8)
        small = F.interpolate(depth[None, None], size=size, mode="nearest")[0, 0]
        keep = F.interpolate(usable[None, None].float(), size=size, mode="nearest")
        level = (small.nan_to_num(0.0, DEPTH_RANGE_M, 0.0) / DEPTH_RANGE_M).clamp(0, 1)
        colours = self._palette[(level * 255).round().long()]
        colours = torch.where(keep[0, 0, :, :, None] > 0.5, colours, 0)
        jpegs = encode_jpeg(
            [camera, colours.permute(2, 0, 1).contiguous()], quality=JPEG_QUALITY
        )
        return tuple(j.cpu().numpy().tobytes() for j in jpegs)


def _preview_size(height: int, width: int) -> tuple[int, int]:
    scale = min(1.0, PREVIEW_LONG_SIDE / max(height, width))
    return max(1, round(height * scale)), max(1, round(width * scale))
