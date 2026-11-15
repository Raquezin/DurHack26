# Models

Which model runs at each stage, why, how it is configured, and what we still
have to measure. Latency bounds referenced here are defined in
[latency-budget.md](latency-budget.md).

Timings are published by third parties (sources at the end) unless stated
as ours. Our own gate results replace them as they are measured (G1 in
section 2, the rest in section 7).

## 1. Decisions at a glance

| Stage | Primary | Fallback | Runs |
| --- | --- | --- | --- |
| Depth | Depth Anything 3 Metric-Large (`da3metric-large`) | DA3 Metric-Large at long side 392; then DA V2 Metric Hypersim-S | local GPU |
| Reasoning | `gemini-3.5-flash-lite`, thinking `MINIMAL`, streamed | none: `gemini-2.5-flash-lite` refuses our key (G2) | Google API |
| Speech, guidance | ElevenLabs `eleven_flash_v2_5`, HTTP streaming endpoint | — | ElevenLabs API |
| Speech, hazards | Same model, rendered once at startup into a local phrase cache | — | local playback |

## 2. Depth model

### Requirements

- **Metric output.** The hazard tier compares distances with thresholds in
  metres; relative depth cannot do that without extra alignment.
- **≤ 20 ms p99** forward pass on our GPU.
- **Indoor range** 0.3–10 m.
- Weights usable without a non-commercial restriction.

### Candidates

Speed is on an RTX 5060 Ti 16 GB, fp16, 994×1482 input resized by the model,
unless stated. Metric error is AbsRel on Middlebury 2014 (indoor scenes)
without any alignment to ground truth, then with a per-image oracle scale.

| Model | Params | Forward (ms) | Metric error | With oracle scale | Weights licence |
| --- | --- | --- | --- | --- | --- |
| **DA3 Metric-Large** | 0.35 B | 14.4 TensorRT, 14.7 custom kernels, 24.3 PyTorch | 12.3 % (true focal length given) | 6.0 % | Apache-2.0 |
| **DA V2 Metric Hypersim-S** | 24.8 M | 4.5 TensorRT, 4.7 custom kernels, 7.7 PyTorch | 29.9 % | 8.9 % | Apache-2.0 |
| DA V2 Metric Hypersim-B | 97.5 M | 10.8 | not in the benchmark | — | Apache-2.0 |
| DA V2 Metric Hypersim-L | 335 M | 31.7 | not in the benchmark | — | Apache-2.0 |
| UniDepth V2-S | — | 42 on Jetson AGX Orin | 24.7 % | 5.7 % | CC BY-NC 4.0 |
| Metric3D v2-S | — | 54 on Jetson AGX Orin | 60 % | 6.5 % | permissive |
| Depth Pro | — | 803 on Jetson AGX Orin | 12.0 % | — | Apple licence |
| YOLO26n-depth | 6.3 M | 2.7 on Tesla T4 | not compared under a shared protocol | — | AGPL-3.0 |

Other data points for DA3 Metric-Large: 19.9 ms on an RTX 3080 (TensorRT
fp16, 518×518); 33 ms on a Jetson AGX Orin (350×504); 30 fps on an RTX 5070
Laptop GPU using 1.2 GB (every model size reports the same 30 fps there, so
the source frame rate was probably the limit).

### Decision

**Primary: DA3 Metric-Large.** It is the only candidate that fits the 20 ms
bound *and* has usable metric scale out of the box. Raw metric error is the
number that matters for the hazard tier, and it is 12 % against ≈ 30 % for the
small V2 metric model. Run it at its native size (long side ≈ 504 px): the
same benchmark shows its scale drifting at larger inputs (14 % at 700×1008,
55 % at full resolution).

**Second fallback: DA V2 Metric Hypersim-S.** Three times faster, but not
in `fastforks` 0.1.0, so it needs the TensorRT path. Its raw scale
is poor — it places surfaces about 1.45× too close in that benchmark — but
its shape is good (8.9 % with the right scale), so it must be used with the
scale calibration below. Its metric head saturates at 20 m, which is
irrelevant indoors.

Rejected: Depth Pro (24× slower than DA3 Metric-Large on the same device),
UniDepth V2 (non-commercial, slower), Metric3D v2-S (60 % raw error),
YOLO26-depth (AGPL, single global scale needs per-camera calibration, and its
speed advantage buys nothing once the V2-S fallback is already at 4.5 ms).

### Gate G1, measured

Ours: `bench/g1_depth.py` on the RTX 5070 Ti Laptop GPU, `fastforks` 0.1.0
kernels, one 640×480 webcam frame, 20 warm-up passes, then 1000 frames per
row timed with CUDA events. `perceive` is the whole adapter call: upload,
colour swap, forward, zone reduction and the one 30-value download.

| Long side | Stage | p50 ms | p95 ms | p99 ms | max ms |
| --- | --- | --- | --- | --- | --- |
| 504 | forward | 15.71 | 15.86 | 15.96 | 16.36 |
| 504 | perceive | 16.02 | 16.17 | 16.24 | 16.70 |
| 504 | perceive + both GPU JPEGs | 16.32 | 16.55 | 16.67 | 17.00 |
| 392 | forward | 10.19 | 10.30 | 10.34 | 10.50 |
| 392 | perceive | 10.49 | 10.60 | 10.68 | 10.93 |
| 392 | perceive + both GPU JPEGs | 10.82 | 10.98 | 11.02 | 11.05 |

The GPU went from 36 °C to 72 °C during the run (2062 MHz at the end); the
10-minute run of A6 is still owed. **Decision: DA3 Metric-Large at long side
504.** G1 passes with 4 ms to spare; zone reduction and upload add 0.3 ms,
previews 0.3–0.4 ms. Long side 392 saves 5.6 ms and is the first lever if
throttling eats the margin; its accuracy waits for G1b.

### Calibration

Monocular metric depth is only as good as the camera model it is given.

1. **Intrinsics.** DA3 Metric-Large outputs depth relative to focal length:
   `metres = output × focal_px / 300`, where `focal_px` is the focal length
   in pixels of the resized image the network sees. The `fastforks` wrapper
   assumes 300 px when given no intrinsics, which is wrong for a webcam.
   Obtain `fx` once per camera from a checkerboard calibration, or from the
   horizontal field of view: `fx = (width / 2) / tan(HFOV / 2)`.
2. **Scale check.** At startup, point the camera at a wall from a taped
   mark at 1 m, 2 m and 3 m. Fit one scalar correction and store it in the
   configuration. This is mandatory for the fallback model and a sanity
   check for the primary.
3. **Floor model.** Lens height and pitch are fitted per frame from the
   farthest surface below the horizon, mount height the prior, last fit
   held when no floor shows. Zone reduction tells floor from obstacle
   ([optimization.md](optimization.md), kernel K2).

### Runtime backend

Three ways to run the same weights, fastest first:

| Backend | DA3 Metric-L | DA V2-S | Start-up cost | Note |
| --- | --- | --- | --- | --- |
| TensorRT fp16 engine | 14.4 ms | 4.5 ms | 30–60 s engine build, cached | engine is tied to GPU and TensorRT version |
| `fastforks` custom CUDA kernels | 14.7 ms; ours 15.7 ms p50 (G1) | 4.7 ms | none | prebuilt for compute capability 12.0; needs driver ≥ 570 |
| Plain PyTorch fp16 | 24.3 ms | 7.7 ms | none | always works; DA3 misses the 20 ms bound |

Start with `fastforks` kernels: no build step and already within budget. Keep
TensorRT as the alternative. Before adding `fastforks`, check that the pinned
release is at least seven days old; it is a young project (0.1.x). If it is
not, use TensorRT.

fp16 is free: both sources report no measurable accuracy change against fp32.

## 3. Reasoning model (VLM)

### Requirements

- Image + text in, short text out, streamed.
- Time to first token ≤ 700 ms p50 and under 1.0 s for 90 % of requests.
- Callable at 0.5–1 Hz for the length of a demo.

### Candidates

| Model | Time to first token | Output speed | Status | Note |
| --- | --- | --- | --- | --- |
| **`gemini-3.5-flash-lite`** | 0.64–0.80 s p50 | ≈ 140–350 tokens/s | stable, recommended for new projects | thinking defaults to `MINIMAL` |
| `gemini-2.5-flash-lite` | ≈ 0.3 s | ≈ 300 tokens/s | 404 for our key (G2) | not available to new users |
| `gemini-3.1-flash-lite` | 4.3 s on one aggregator | ≈ 360 tokens/s | stable | no reason to prefer it |
| `gemini-3.8-live` (Live API) | 1.9 s median response, 2.4 s p95 | audio out | stable | see below |

Published 3.5 Flash-Lite figures range from 0.64 s p50 (router traffic) to
4.6 s (first answer token, thinking included), so thinking is pinned to
`MINIMAL`.

### Decision

**Primary: `gemini-3.5-flash-lite`** over the streaming generate-content
endpoint. It is the model Google directs new projects to. On published
figures its p50 straddles our 700 ms target, so its tail will lose some
responses to the 1.5 s deadline. Three levers, in order: the phrase
cache (section 4), a smaller image, and the priority inference tier (0.58 s
p50 reported).

**Not the Live API.** It is designed for this kind of use, but it does not
fit our design:

- Its current models output audio only. Speech would bypass ElevenLabs and
  our staleness and priority control.
- Video input is capped at 1 frame per second.
- Measured median response is 1.9 s, above our 1.5 s discard deadline.
- Audio-plus-video sessions last 2 minutes without context compression.

It remains a stretch option for "what is in front of me?" on demand.

### Request configuration

- Streaming response; thinking pinned to `MINIMAL`.
- Output capped at about 40 tokens.
- One downscaled JPEG (long side ≤ 512 px) plus the zone distances as text.
  Lowest media-resolution setting that still reads the scene.
- One persistent HTTP connection, opened and warmed with a dummy request at
  startup. A cold first turn of about 3 s has been reported on the Live API.
- Output format: a phrase identifier from the fixed catalogue when one fits,
  otherwise one short imperative sentence ([contracts.md](contracts.md)).
- The system prompt states the division of labour: hazards under 2 m are
  already handled locally; describe route and the 2–5 m range.

## 4. Speech (TTS)

### Candidates

| Model | Server-side latency | Transport | Note |
| --- | --- | --- | --- |
| **`eleven_flash_v2_5`** | ≈ 100 ms median | HTTP streaming, `stream-input` WebSocket | 32 languages, half price |
| `eleven_v4_turbo` | ≈ 100 ms median | Text to Dialogue WebSocket | more expressive; no benefit for imperatives |
| `eleven_v3_conversational` | ≈ 165 ms | WebSocket | slower |
| `eleven_multilingual_v2` | ≈ 700 ms to first audio (one benchmark) | both | too slow |

Client-side time to first audio for Flash v2.5, which is what the user
experiences: 100–150 ms from Europe according to ElevenLabs; 144 ms p50 /
192 ms p95 in one independent benchmark; 324 ms p50 in another measured from
Paris. Budget 150–350 ms.

### Decision and configuration

**`eleven_flash_v2_5`** in both tiers.

- **Guidance tier:** the HTTP streaming endpoint on a client kept open
  for the session.
  - `output_format=pcm_24000`: raw PCM, no decoder, no container header.
  - A default (premade) voice; professional voice clones are slower.
- **Hazard tier and frequent guidance: phrase cache.** At startup every
  phrase in the catalogue is rendered once with the same voice and stored as
  PCM on disk. Hazard alerts play from memory with no network. Guidance that
  resolves to a catalogue phrase also plays from the cache and skips TTS.
  The cache also holds "Continue for N metres." for N = 0–9, and a
  streamed sentence is kept in memory after it has played once.

## 5. Not used

| Idea | Why not now |
| --- | --- |
| Object detector on the GPU (YOLO class) | The VLM already names objects from RGB. Stretch goal only. |
| Local TTS | The phrase cache already removes the network from the hazard tier. |
| Gemini TTS models | TTS is the ElevenLabs sponsor slot. |
| Video depth models with temporal state | Per-frame depth plus a temporal filter on 45 zone values is enough. |
| INT8 quantisation | Vision transformers lose accuracy without careful calibration; fp16 already meets the bound. |

## 6. GPU memory

`nvidia-smi` on the development laptop reports an RTX 5070 Ti Laptop GPU with
12 GB and compute capability 12.0. If the demo machine is a different
RTX 5070, re-run gate G1 there.

| Consumer | Memory |
| --- | --- |
| DA3 Metric-Large with buffers and JPEG encoder, long side 504 | 0.63 GiB allocated, 0.78 GiB peak (ours) |
| DA V2 Metric-S, fp16 | ≈ 0.2–0.3 GB |

Memory is not a constraint. Both depth models can be loaded together to
compare them live.

## 7. Benchmark gates

Each gate is a script in `bench/` that prints p50 / p95 / p99 and is run on
the demo hardware and venue network.

| Gate | Question | Pass | If it fails |
| --- | --- | --- | --- |
| G1 | DA3 Metric-L forward pass on our GPU, warm, 1000 frames | ≤ 20 ms p99 | lower input resolution, then fall back to DA V2 Metric-S |
| G1b | Distance error against a tape measure at 1, 2, 3 m | ≤ 15 % | apply scale correction; fix intrinsics |
| G2 | Time to first token with the real payload, both Gemini models | ≤ 700 ms p50 and ≥ 90 % under 1.0 s | smaller image; shorter prompt; priority tier; other model |
| G3 | ElevenLabs time to first audio on the kept-open client | ≤ 350 ms p95 | regional endpoint; widen phrase cache |
| G4 | Camera glass-to-frame delay per capture format | ≤ 70 ms | other pixel format, resolution or camera |

Results (ours, November 2026):

| Gate | Setup | Result | Verdict |
| --- | --- | --- | --- |
| G1b | iPhone in portrait, 480×640, by hand at a wall, `hfov_deg=58` | 1 m +11.8 %, 2 m −3.5 %, 3 m +7.1 % | pass, scale 1.0 |
| G2 | a new walk frame per request, server network, 12 requests | 1037 ms p50, 11.4 s p95, 42 % under 1.0 s | fail |
| G3 | `eleven_flash_v2_5`, HTTP stream on the kept-open client, 20 sentences | 192 ms p50, 206 ms p95, 206 ms p99 (a WebSocket per request: 248, 272, 380) | pass |
| G4 | webcam, all four modes, `exposure_dynamic_framerate` off | frame interval 32.1 ms p50, ≤ 36.5 ms p99 | glass-to-frame unmeasured |

- G1b: at 70° every distance read 20–25 % short; 58° (iPhone wide camera,
  short side) is now the default. The webcam's field of view is unmeasured.
- G2: the first run reused one fixture image and read 806 ms p50; Gemini is
  fast on an image it has seen and slow on a new one, so that number was
  flattering. Guidance now waits up to 5 s and checks the scene still
  matches. `gemini-2.5-flash-lite` returns HTTP 404 for our key.
- G4: `--glass` needs a screen the camera can film; the GPU server has none.

## 8. Sources

- fastforks model pages, measured November 2026 —
  https://fastforks.dev/models/depth_anything_v2 and
  https://fastforks.dev/models/depth_anything_3
- "Which Depth Estimator for Jetson AGX Orin? A 2026 Benchmark of Monocular
  and Stereo Methods" — https://arxiv.org/html/2610.27199v1
- DA3 Metric-Large on TensorRT, RTX 3080 —
  https://github.com/yester31/Monocular_Depth_Estimation_TRT/blob/main/models/depth_anything_v3/README.md
- DA3 on DeepStream, RTX 5070 Laptop —
  https://github.com/Raessan/depth_anything_v3_deepstream
- YOLO26 depth — https://docs.ultralytics.com/tasks/depth
- Gemini model list and deprecations —
  https://ai.google.dev/gemini-api/docs/models
- Gemini time to first token — https://modelgrep.com/best/lowest-latency/google,
  https://openrouter.ai/google/gemini-3.5-flash-lite,
  https://www.requesty.ai/model/google/gemini-3.5-flash-lite,
  https://artificialanalysis.ai/models/gemini-3-5-flash-lite and
  https://suhasbhairav.com/research/llm-leaderboard/models/gemini-3-5-flash-lite
- Gemini thinking levels —
  https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking
- Gemini Live API limits and benchmark —
  https://aistudio.google.com/docs/live-api/session-management and
  https://www.cekura.ai/blogs/gemini-live-api
- ElevenLabs latency methodology and optimisation —
  https://elevenlabs.io/docs/eleven-api/concepts/latency-methodology and
  https://elevenlabs.io/docs/eleven-api/guides/how-to/best-practices/latency-optimization
- ElevenLabs WebSocket guide —
  https://elevenlabs.io/docs/eleven-api/guides/how-to/websockets/realtime-tts
- Independent TTS benchmarks — https://breezeblue.ai/benchmarks/tts-latency and https://onepin.ai/blog/streaming-tts-latency-ttfb-2026
