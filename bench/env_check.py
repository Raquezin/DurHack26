import time

import cupy
import cv2
import fastforks
import torch
import torchvision
from camera_modes import report
from fastforks import depth
from torchvision.io import decode_jpeg, encode_jpeg

SCALE_ADD = cupy.RawKernel(
    r"""
extern "C" __global__ void scale_add(const float* x, float* y, float a, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) y[i] = a * x[i] + y[i];
}
""",
    "scale_add",
)


def versions():
    props = torch.cuda.get_device_properties(0)
    return {
        "torch": f"{torch.__version__} (CUDA {torch.version.cuda}, cuDNN {torch.backends.cudnn.version()})",
        "torchvision": torchvision.__version__,
        "cupy": f"{cupy.__version__} (runtime {cupy.cuda.runtime.runtimeGetVersion()}, driver {cupy.cuda.runtime.driverGetVersion()})",
        "opencv": cv2.__version__,
        "fastforks": fastforks.__version__,
        "gpu": f"{props.name}, sm_{props.major}{props.minor}, {props.total_memory / 2**30:.1f} GiB",
        "torch archs": " ".join(torch.cuda.get_arch_list()),
    }


def torch_op():
    a = torch.randn(1024, 1024, device="cuda", dtype=torch.float16)
    b = (a @ a.T).float()
    torch.cuda.synchronize()
    assert torch.isfinite(b).all()
    return f"fp16 matmul {tuple(b.shape)} on {b.device}"


def cupy_kernel_and_dlpack():
    x = torch.arange(1 << 20, device="cuda", dtype=torch.float32)
    y = torch.ones_like(x)
    cx, cy = cupy.from_dlpack(x), cupy.from_dlpack(y)
    assert cx.data.ptr == x.data_ptr() and cy.data.ptr == y.data_ptr()
    n = x.numel()
    SCALE_ADD(((n + 255) // 256,), (256,), (cx, cy, cupy.float32(2.0), cupy.int32(n)))
    cupy.cuda.Device().synchronize()
    assert torch.equal(y, 2 * x + 1)
    back = torch.from_dlpack(cy)
    assert back.data_ptr() == y.data_ptr()
    return f"RawKernel wrote a torch tensor through DLPack, zero-copy both ways ({n} floats)"


def gpu_jpeg():
    image = torch.randint(0, 256, (3, 480, 640), dtype=torch.uint8, device="cuda")
    encode_jpeg(image, quality=80)
    torch.cuda.synchronize()
    start = time.perf_counter()
    data = encode_jpeg(image, quality=80)
    torch.cuda.synchronize()
    ms = (time.perf_counter() - start) * 1000
    decoded = decode_jpeg(data.cpu())
    assert decoded.shape == image.shape
    return f"encode_jpeg on {image.device}: {data.numel()} bytes, {ms:.2f} ms (output on {data.device})"


def depth_backend(model_id="da3metric-large", runs=20):
    model = depth.load(model_id, mode="kernels")
    image = torch.randint(0, 256, (3, 480, 640), dtype=torch.uint8, device="cuda")
    k = torch.tensor([[500.0, 0.0, 319.5], [0.0, 500.0, 239.5], [0.0, 0.0, 1.0]])
    for _ in range(5):
        model(image, intrinsics=k)
    torch.cuda.synchronize()
    start = time.perf_counter()
    for _ in range(runs):
        result = model(image, intrinsics=k)
    torch.cuda.synchronize()
    ms = (time.perf_counter() - start) / runs * 1000
    assert result.kind == "metric" and result.depth.shape == (480, 640)
    return f"{model_id} {result.backend.mode} {result.backend.dtype} {result.backend.kernels}: depth {tuple(result.depth.shape)} {result.depth.dtype} on {result.depth.device}, {ms:.1f} ms/frame at 640x480"


def main():
    for name, value in versions().items():
        print(f"{name:12} {value}")
    assert (
        torch.cuda.is_available()
        and f"sm_{''.join(map(str, torch.cuda.get_device_capability()))}"
        in torch.cuda.get_arch_list()
    )
    for check in (torch_op, cupy_kernel_and_dlpack, gpu_jpeg, depth_backend):
        print(f"ok {check.__name__}: {check()}")
    print()
    print(report(0))


if __name__ == "__main__":
    main()
