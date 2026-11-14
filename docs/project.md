# Project Overview — Real-Time Audio Navigation Assistant for the Visually Impaired

## Vision

A wearable-style assistive system that lets a blind or visually impaired person
navigate physical space using only a camera and headphones. A live video feed is
converted into a depth map, a vision-language model reasons about the scene, and
spoken instructions are delivered to the user in real time — acting as an
"audio guide" for the world around them.

**Demo scenario:** a person wearing headphones (optionally blindfolded) walks
around a room or corridor guided entirely by the system's spoken instructions.

## Pipeline

```
Camera (real-time video)
        │
        ▼
┌──────────────────────────┐
│   Depth Model            │  Per-frame depth estimation, real-time inference
│   (local, on GPU)        │
└──────────────────────────┘
        │
        ▼
┌──────────────────────────┐
│   Distance Estimation    │  Derives metric/contextual distances from the
│   (post-processing)      │  depth map: nearest obstacle, per-region
└──────────────────────────┘  distances (left/center/right), floor plane
        │
        ▼
┌──────────────────────────┐
│  VLM Reasoning           │  Interprets depth + distance data (+ optional
│  (Google API)            │  RGB), decides what the user needs to hear:
└──────────────────────────┘  obstacles, directions, hazards
        │
        ▼
┌───────────────────┐
│       TTS         │  Spoken instructions streamed to headphones
│   (ElevenLabs)    │
└───────────────────┘
        │
        ▼
   🎧 User
```

### Component notes

- **Depth model** — runs locally on our GPU for low-latency, real-time depth
  estimation from the video feed. Specific model: TBD.
- **Distance estimation** — the raw depth map is post-processed locally into
  structured distance context for the VLM: e.g., nearest-obstacle distance,
  per-region distances (left / center / right or a coarse grid), and possibly
  floor/obstacle segmentation. This gives the VLM quantitative grounding
  ("wall 1.5 m ahead, clear path to the right") rather than leaving it to
  interpret a depth image alone.
- **VLM reasoning** — Google API consumes depth frames, the computed distance
  data, and possibly RGB context, and produces short, actionable navigation
  guidance. Reasoning must be throttled/prioritized so instructions stay
  timely — stale advice is worse than no advice. Specific model: TBD.
- **TTS** — ElevenLabs for natural, low-latency speech. Short imperative
  phrases ("step left", "door ahead", "stop — obstacle 1 meter") streamed with
  minimal delay.
- **Latency budget** — the whole loop (frame → depth → reasoning → audio) is
  performance-critical. Optimization target: instructions that arrive while
  they're still true. Technical details TBD, but design every stage for speed.

## UI

Deliberately minimal — the *user* never sees it; it exists for the demo,
debugging, and judges:

- **Square 1:** raw real-time camera feed.
- **Square 2:** live depth map visualization.
- **Chat/panel:** streaming reasoning output / instruction log (what the VLM
  "thinks" and what was spoken).

No other chrome. The interface should make the pipeline legible at a glance:
what the camera sees, what the model perceives, what the system says.

## Goals

1. **Primary (must-have):** end-to-end loop working in a controlled
   environment — camera → depth → guidance → speech — good enough to walk a
   simple path blindfolded.
2. **Secondary:** reasonable latency (instructions feel live, not laggy) and
   instruction quality (concise, correct prioritization: hazards > navigation >
   description).
3. **Stretch:** spatial audio cues, distance-aware urgency, object/person
   recognition, outdoor robustness.

## Out of scope (for the hackathon)

- Mobile/wearable hardware integration — webcam + laptop demo is fine.
- Multi-language TTS.
- Offline operation (APIs are allowed and encouraged via sponsors).
- Perfect robustness — this is a proof of concept, not a medical device.

## Sponsor / API usage

- **ElevenLabs** — text-to-speech (model/voice TBD).
- **Google API** — vision-language reasoning over depth/distance/RGB input
  (model TBD).

## Team & infra notes

- **Team of 3** — the project is designed to split into parallel workstreams
  (depth inference + distance estimation, VLM reasoning + TTS loop,
  UI/integration), but the actual split is TBD — to be decided together.
- **Hardware:** RTX 5070 GPU available for local inference (depth model, and
  anything else we want off the API path).
- **Performance-first stack:** every choice should bias toward throughput and
  low end-to-end latency.
