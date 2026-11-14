# Optimisation Techniques

How we meet the bounds in [latency-budget.md](latency-budget.md) with the
models in [models.md](models.md). Covers the GPU path (including the custom
CUDA kernels we write), host-side scheduling, the cloud path and audio output.

Speed figures quoted from others are marked **[M]**; our own expectations are
marked **[E]** and stay unverified until the benchmark scripts run.

## 1. Principles

1. **Measure first.** No optimisation lands without a before/after number
   from `bench/`. If the simpler version is within 1 ms, keep the simpler one.
2. **Latest frame wins.** Never queue frames. A stage that is busy drops what
   it could not start; it never works on stale input. This matters more than
   any kernel.
3. **One upload, one tiny download.** A frame crosses to the GPU once, as
   uint8. Only a few dozen numbers and two small JPEGs come back.
4. **Nothing per-frame on the CPU that scales with pixels.**
5. **No allocation in the loop.** Every buffer is created once at startup.

## 2. The GPU frame path

```
host                         │ GPU
─────────────────────────────┼──────────────────────────────────────────────
camera buffer (uint8 BGR)    │
  pinned memory ─────────────┼─▶ frame_u8
                             │     │ K1 fused preprocess
                             │     ▼
                             │   input_f16 (CHW, normalised, model size)
                             │     │ depth network
                             │     ▼
                             │   depth (metres)
                             │     ├─ K2 zone reduction ─▶ 15 distances
15 floats ◀──────────────────┼─────┘
hazard decision              │     ├─ K3 colourmap + resize ─▶ depth_rgb_u8
                             │     │                             │ nvJPEG
2 JPEGs (UI, VLM) ◀──────────┼─────┴─ frame_u8 resize ───────────┘
```

The hazard decision depends only on the left column up to "15 floats". The
preview branch runs after it and can be skipped on any frame.

## 3. Technique ladder for the depth network

Depth Anything V2-S on an RTX 5060 Ti, 994×1482 input [M]. Each row keeps the
previous ones.

| Step | Technique | Time per frame | Gain | Cost to us |
| --- | --- | --- | --- | --- |
| 0 | Authors' code, fp32 | 53.6 ms | — | — |
| 1 | fp16 autocast | 41.0 ms | 1.3× | one line |
| 2 | Clean PyTorch port, fp16, input already on GPU | 7.8 ms | 6.9× | use an existing port |
| 3 | `torch.compile` | 6.7 ms | 8.1× | 16 s compile at startup |
| 4 | Fused custom CUDA kernels, or a TensorRT fp16 engine | 4.5 ms | 12× | prebuilt library, or 30 s engine build |

DA3 Metric-Large follows the same shape [M]: 128 ms → 85 ms → 24.3 ms →
21.2 ms → 14.4–14.7 ms.

What this tells us:

- **Most of the gain is steps 1–2**, which are not kernel work at all:
  half precision, no CPU pre-processing, no host round-trips, no redundant
  resizes.
- **Hand-written kernels and TensorRT land in the same place** (4.51 vs
  4.46 ms). TensorRT fuses layers automatically; the kernel library does it
  by hand. Neither leaves much for a third party to gain.
- fp16 costs no measurable accuracy [M]. INT8 is not worth the calibration
  risk on a vision transformer when fp16 already meets the bound.

Further levers if gate G1 fails, in order:

1. **Input resolution.** Cost follows the token count,
   `(H / 14) × (W / 14)`. 518×686 is 1813 tokens; 392×518 is 1036. Our output
   is 15 zone distances, so a small input loses little.
2. **Skip the final upsample.** The models resize depth back to the camera
   resolution. We reduce to zones at the network's native output size.
3. **CUDA graphs.** A launch costs the host 5–15 µs per kernel [M]. Capturing
   the fixed-shape forward pass as one graph removes that overhead. TensorRT
   supports it directly.
4. **The fallback model**, three times faster.

## 4. Custom CUDA kernels we write

Model-internal kernels are a solved problem (section 5). The pixels *around*
the model are not: no library has our exact operations, and the naive
versions bounce through the CPU. These are the kernels worth writing.

All three are written as CUDA C through CuPy `RawKernel`. The source is
compiled once by NVRTC and cached on disk. Arrays are shared with PyTorch
with no copy through DLPack.

### K1 — fused preprocess

| | |
| --- | --- |
| Input | `frame_u8`: H×W×3 uint8, BGR, camera resolution |
| Output | `input_f16`: 3×h×w half float, RGB, ImageNet-normalised, model resolution |
| Work | one thread per output pixel: bilinear sample of the source, channel swap, scale, subtract mean, divide by deviation, write three planes |
| Replaces | colour conversion, layout permute, float conversion, resize and normalise as five separate operations with three intermediate buffers — or the same on the CPU followed by a float upload four times larger than the uint8 frame |
| Bound | ≤ 1 ms p99 |

A second variant takes the camera's raw YUYV buffer directly, which removes
the CPU colour conversion in the capture thread. Write it only if gate G4
shows that conversion matters.

### K2 — zone reduction

| | |
| --- | --- |
| Input | `depth`: h×w metres; per-row floor distance table; grid shape (3 rows × 5 columns) |
| Output | 15 robust near-distances and 15 valid-pixel counts |
| Work | pass 1, one thread per pixel: skip invalid depth; skip pixels at or beyond the expected floor distance for their row; bin the rest into a log-spaced 64-bin histogram for the pixel's zone using atomic adds. Pass 2, one thread per zone: walk the histogram to the 5th percentile |
| Replaces | downloading a full depth map every frame and running percentiles on the CPU |
| Bound | ≤ 1 ms p99 including the 15-float download |

Design notes:

- **5th percentile, not minimum.** A single noisy pixel must not trigger
  "Stop". Monocular depth scatters points at object edges.
- **Floor rejection** uses the mount's height and pitch
  ([models.md](models.md), calibration): for each image row below the
  horizon the floor is expected at a known distance. Anything clearly nearer
  is an obstacle; the rest is ground.
- A zone with too few valid pixels is reported as not valid rather than as
  clear.

### K3 — depth preview

| | |
| --- | --- |
| Input | `depth`: h×w metres |
| Output | UI-resolution uint8 RGB image through a colour lookup table, fixed range 0–5 m |
| Then | GPU JPEG encode (nvJPEG via `torchvision.io.encode_jpeg` on a CUDA tensor), same for the downscaled camera frame |
| Bound | ≤ 3 ms p99 for both JPEGs, after the hazard decision |

A fixed range keeps colours stable from frame to frame; per-frame
normalisation flickers.

### Rules for kernel work

- Each kernel has a reference implementation in plain PyTorch operations and
  a test that compares the two on recorded frames.
- The reference version ships first. The kernel replaces it only with a
  measured gain.
- Kernels are compiled during startup warm-up, never on the first live frame.
- Fixed shapes, preallocated outputs, no synchronisation points except the
  single download of the K2 result.

Expected gain [E]: low single-digit milliseconds and, more importantly, less
jitter, because the CPU and the Python interpreter leave the per-pixel path.

## 5. Kernels inside the model

The `fastforks` backend runs the Depth Anything networks on two hand-written
kernel libraries, `fastbb` and `dpt_fused` — going by the names, the
transformer backbone and a fused DPT decoder head. That is what takes the
clean PyTorch port from 7.8 ms to 4.5 ms [M].

The standard technique is fusion: several operations (for example
normalisation, activation and projection) run in one kernel, so intermediate
results stay in registers instead of going through GPU memory between kernel
launches. Published examples report 2–2.6× on the fused operations [M].

We use these kernels; we do not rewrite them. Writing our own
attention or decoder kernels would be justified only if all of these hold:

1. Gate G1 fails on both models at reduced resolution.
2. A profile shows one operation dominating.
3. Neither the kernel library nor TensorRT already fuses it.

In that case the candidate is the decoder head at our reduced output size,
not attention.

## 6. Host side

- **Threads by role:** one blocking capture thread; one GPU thread that runs
  perception and the hazard rule back to back; one asyncio loop for all
  network I/O and the UI; the audio callback thread. GPU calls and socket
  I/O release the interpreter lock, so the threads do not fight as long as
  no thread does per-pixel Python work.
- **Mailboxes of size one** between threads. A writer overwrites; a reader
  takes the newest. No queue can grow.
- **Camera:** request the format and resolution explicitly, buffer size 1,
  and keep reading continuously so the driver buffer never holds an old
  frame. Compare MJPEG and YUYV in gate G4: MJPEG costs a decode, YUYV costs
  USB bandwidth.
- **Pinned host memory** for the upload buffer; non-blocking copy.
- **Warm-up:** 20 forward passes, all kernels, one dummy VLM request, one
  TTS request and the audio stream opened before the user starts walking.
- **Hazard rule in the GPU thread.** The decision runs immediately after
  the 15 floats arrive, with no thread hop.

## 7. Cloud path

| Technique | Saves | Where |
| --- | --- | --- |
| Persistent, pre-warmed connections to Gemini and ElevenLabs | connection setup on every call; a cold first turn | both |
| Thinking pinned to `MINIMAL`; output capped at ≈ 40 tokens | seconds of hidden reasoning | Gemini |
| One small JPEG (long side ≤ 512 px) and distances as text | upload and image tokens | Gemini |
| Streamed response, forwarded to TTS at the first complete phrase | waiting for the full answer | Gemini → TTS |
| Phrase identifiers resolved from the local cache | the whole TTS round-trip, 150–325 ms [M] | TTS |
| `auto_mode`, `flush`, raw PCM output | server-side buffering; decode | ElevenLabs |
| Event-triggered requests with a minimum interval; one in flight | calls that would be discarded anyway | Gemini |
| Change detection on zone distances | repeating advice for an unchanged scene | trigger |
| Deadline carried with every request; abandon at 1.0 s without a token | speaking stale advice | arbiter |
| Priority inference tier | queueing on Google's side | Gemini, if G2 fails |

## 8. Audio output

- Wired headphones. Default Bluetooth adds about 220 ms [M].
- One output stream, opened once, small block size, callback-driven.
- Raw PCM at 24 kHz mono end to end: phrase cache, TTS stream and device
  agree, so nothing is resampled or decoded while playing.
- No player-side buffering. A typical player buffers 500 ms before it starts
  [M]; we start on the first chunk.
- Hazard clips are in memory. Pre-emption cuts the current audio at the next
  block boundary and starts the alert.

## 9. Machine checklist

- Mains power, performance power profile, no battery saver.
- Discrete GPU selected for the process.
- Nothing else on the GPU during the demo: no browser video, no other model.
- Watch GPU temperature and clock during a 10-minute run; laptop GPUs
  throttle, and the p99 after ten minutes is the real figure.
- Wired network if the venue offers it; phone hotspot tested as fallback.

## 10. What we do not do

| Not doing | Why |
| --- | --- |
| Rewriting attention or decoder kernels | Already at parity with TensorRT (section 3) |
| INT8 quantisation | Accuracy risk; fp16 meets the bound |
| Batching frames | Raises latency; we have one camera |
| GPU video decode pipeline | One USB camera; capture is not a decode problem |
| Moving the orchestrator out of Python | The hot path is GPU kernels and sockets; measure before assuming otherwise |

## 11. Sources

- fastforks benchmarks and kernel backend —
  https://fastforks.dev/models/depth_anything_v2,
  https://fastforks.dev/models/depth_anything_3 and https://fastforks.dev/usage
- TensorRT CUDA graphs and launch overhead —
  https://docs.nvidia.com/deeplearning/tensorrt/latest/performance/optimization.html
  and https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/performance/optimization.html
- Torch-TensorRT performance tuning —
  https://docs.pytorch.org/TensorRT/user_guide/performance_tuning.html
- Kernel fusion for transformers —
  https://buildai.substack.com/p/cuda-kernels-for-transformers-custom
- CuPy `RawKernel` —
  https://docs.cupy.dev/en/stable/reference/generated/cupy.RawKernel.html
- ElevenLabs latency concepts (player buffering) —
  https://elevenlabs.io/docs/eleven-api/concepts/latency
- Camera buffering —
  https://stackoverflow.com/questions/30032063/opencv-videocapture-lag-due-to-the-capture-buffer
