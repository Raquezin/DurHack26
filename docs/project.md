# Project Overview — Real-Time Audio Navigation Assistant for the Visually Impaired

## Vision

A wearable-style assistive system that lets a blind or visually impaired person
navigate physical space using only a camera and headphones. A live video feed is
converted into a depth map, a vision-language model reasons about the scene, and
spoken instructions are delivered to the user in real time — acting as an
"audio guide" for the world around them.

**Demo scenario:** a person wearing headphones (optionally blindfolded) walks
around a room or corridor guided entirely by the system's spoken instructions.

## Documentation map

| Document | Covers |
| --- | --- |
| [project.md](project.md) | This overview: vision, pipeline, goals, scope |
| [latency-budget.md](latency-budget.md) | Research-backed upper bounds, per-stage budgets, alert distances, how we measure |
| [models.md](models.md) | Depth, reasoning and speech models: candidates, decisions, configuration, benchmark gates |
| [optimization.md](optimization.md) | GPU techniques, the custom CUDA kernels we write, scheduling, cloud and audio paths |
| [architecture.md](architecture.md) | Hexagonal structure, ports, services, threads, layout |
| [contracts.md](contracts.md) | Frozen data types and interfaces between owners; fakes, fixtures, change protocol |
| [plan.md](plan.md) | Split of the work between three people, phases, milestones, risks |

## Pipeline

```
Camera (30 fps)
      │ Frame
      ▼
┌──────────────────────────────┐
│ Perception (local GPU)       │  fused preprocess → metric depth →
│                              │  zone distances, every frame
└──────────────────────────────┘
      │ SceneGeometry: 15 zone distances (3 rows × 5 columns)
      ├─────────────────────────────────────────┐
      ▼                                         ▼
┌──────────────────────────┐      ┌───────────────────────────────┐
│ Hazard tier (local)      │      │ Guidance tier (cloud)         │
│ rules on distances →     │      │ trigger → Gemini → ElevenLabs │
│ cached speech clip       │      │ streamed speech               │
│ ≤ 300 ms, hard           │      │ ≤ 1 s target, dropped at 1.5 s│
└──────────────────────────┘      └───────────────────────────────┘
      │ Utterance (HAZARD)                      │ Utterance (GUIDANCE)
      └───────────────────┬─────────────────────┘
                          ▼
                ┌───────────────────┐
                │ Speech arbiter    │  priority, pre-emption, staleness
                └───────────────────┘
                          ▼
                  Wired headphones
```

### Component notes

- **Perception** — runs on our GPU on every frame. A fused kernel turns the
  camera frame into the network input, Depth Anything 3 Metric-Large produces
  metric depth, and a second kernel reduces it to fifteen robust zone
  distances with the floor removed. Fallback model: Depth Anything V2 Metric
  Small. Details in [models.md](models.md) and
  [optimization.md](optimization.md).
- **Hazard tier** — rule-based and fully local. Thresholds on the zone
  distances raise "Caution" and "Stop". The alert is a short speech clip,
  rendered with ElevenLabs once at startup and played from memory.
- **Guidance tier** — `gemini-3.5-flash-lite` receives a small RGB frame and
  the zone distances and returns a short instruction, streamed. It runs
  event-triggered with at most one request in flight, never per frame. It
  reasons about route and the 2–5 m range; nearer than that belongs to the
  hazard tier.
- **Speech** — ElevenLabs `eleven_flash_v2_5` over a persistent WebSocket for
  free-form guidance; the phrase cache for hazards and common instructions.
- **Speech arbiter** — hazards interrupt guidance; stale utterances are
  dropped; nothing is repeated needlessly.

## Latency constraints

End-to-end latency is the binding constraint of the whole system — an
instruction that arrives late describes a scene that no longer exists.
[latency-budget.md](latency-budget.md) has the research, the per-stage
budgets and the measurement method. In summary:

- **Hazard alerts (hard bound): ≤ 300 ms** from capture to first audio
  sample, under the ~320 ms bound from human response-time research for
  wearable obstacle avoidance. Internal design target: 150 ms p95.
- **Spoken guidance (target): ≤ 1.0 s p50.** Published figures put our
  default model at roughly 1.0–1.2 s with streamed speech and about 0.9 s on
  a phrase-cache hit; the faster candidate model reaches 0.5–0.8 s.
- **Staleness rule:** a cloud answer is spoken only while the scene still
  matches the frame it was asked about, and never more than 5 s after
  capture. Measured first-token times for new images range from 0.6 s to
  over 10 s, so a fixed short deadline discarded almost every answer.
- **Local guidance** steers from the depth grid with no network, so
  directions keep coming when the cloud is slow or down.
- **Two feedback tiers** follow from this: a cloud call cannot meet the
  hazard bound, so imminent hazards are handled locally and the cloud is
  used only for guidance.
- **Wired headphones.** A default Bluetooth link adds about 220 ms.

None of these figures has been measured on our hardware yet; the benchmark
gates in [models.md](models.md) do that first.

## UI

Deliberately minimal — the *user* never sees it; it exists for the demo,
debugging, and judges:

- **Square 1:** raw real-time camera feed.
- **Square 2:** live depth map visualization, with chips for what the camera
  sees (from Gemini). A road crossing is red: depth cannot see a road, so
  that tag is what stops "keep going straight".
- **Chat/panel:** streaming reasoning output / instruction log (what the VLM
  "thinks", what was spoken, what was dropped and why).
- **Latency strip:** per-stage p50 / p95 / p99.

No other chrome. The interface should make the pipeline legible at a glance:
what the camera sees, what the model perceives, what the system says.

## Goals

1. **Primary (must-have):** end-to-end loop working in a controlled
   environment — camera → depth → guidance → speech — good enough to walk a
   simple path blindfolded.
2. **Secondary:** latency within the bounds above, measured and displayed,
   and instruction quality (concise, correct prioritization: hazards >
   navigation > description).
3. **Stretch:** spatial audio cues, distance-aware urgency, object/person
   recognition, describe-on-demand, outdoor robustness.

## Out of scope (for the hackathon)

- Mobile/wearable hardware integration — webcam + laptop demo is fine.
- Multi-language TTS.
- Offline operation (APIs are allowed and encouraged via sponsors). The
  hazard tier nevertheless works without a network.
- Perfect robustness — this is a proof of concept, not a medical device.

## Sponsor / API usage

- **ElevenLabs** — text-to-speech with `eleven_flash_v2_5`: streamed over
  WebSocket for guidance, pre-rendered for the phrase cache.
- **Google API** — vision-language reasoning with `gemini-3.5-flash-lite`
  over small RGB frames
  and zone distances.

## Team & infra notes

- **Team of 3**, split into three vertical slices with frozen contracts
  between them ([plan.md](plan.md)):
  - **A — Perception:** camera, depth, GPU kernels, zone distances.
  - **B — Guidance:** Gemini reasoning, triggering, ElevenLabs speech.
  - **C — Alerts, audio and UI:** hazard rules, speech arbiter, audio
    output, web UI, wiring and latency tracing.
- **Hardware:** the development laptop reports an RTX 5070 Ti Laptop GPU
  with 12 GB (`nvidia-smi`). Local inference uses well under 2 GB.
- **Stack:** Python orchestrating GPU kernels and network I/O; PyTorch,
  CuPy for our own CUDA kernels, TensorRT or prebuilt kernels for the depth
  network; a static web page over WebSocket for the UI.
- **Architecture:** hexagonal ([architecture.md](architecture.md)).
- **Performance-first stack:** every choice should bias toward throughput and
  low end-to-end latency, and every optimisation is justified by a
  measurement.
