# Architecture

Hexagonal (ports and adapters). The domain and the application services know
nothing about cameras, CUDA, Gemini, ElevenLabs or browsers; they talk to
ports. Everything with a vendor name is an adapter behind a port.

This is what lets three people work in parallel: each owns adapters and
services on one side of a port, and a fake on the other side stands in until
the real thing lands. The data that crosses ports is specified in
[contracts.md](contracts.md); who owns what is in [plan.md](plan.md).

## 1. The hexagon

```
                    driving side                      driven side

                                  ┌───────────────────────────────┐
  FrameSource ───────────────────▶│                               │
  (webcam | replay | fake)        │   application services        │──▶ ScenePerception
                                  │                               │    (GPU depth | replay | fake)
                                  │   PerceptionLoop              │
                                  │   HazardMonitor               │──▶ SceneReasoner
                                  │   GuidanceLoop                │    (Gemini | fake)
                                  │   SpeechArbiter               │
                                  │                               │──▶ SpeechSynthesizer
                                  │   ┌───────────────────────┐   │    (ElevenLabs | fake)
                                  │   │ domain                │   │
                                  │   │ types, HazardPolicy,  │   │──▶ AudioSink
                                  │   │ TriggerPolicy,        │   │    (sound device | file | fake)
                                  │   │ ArbitrationPolicy     │   │
                                  │   └───────────────────────┘   │──▶ EventPublisher
                                  └───────────────────────────────┘    (web UI | log | fake)
```

Dependencies point inward only: adapters → ports → application → domain.

## 2. Layers

| Layer | Contains | May import | Must not contain |
| --- | --- | --- | --- |
| `domain` | Immutable data types; pure policies (hazard thresholds, guidance triggering, speech arbitration rules) | standard library | I/O, threads, clocks, tensors, vendor SDKs |
| `ports` | One interface per external capability | `domain` | implementations |
| `application` | Services that move data between ports and apply policies | `domain`, `ports` | vendor SDKs, device access |
| `adapters` | One package per technology, each implementing one port; a fake for every port | `domain`, `ports`, vendor SDKs | other adapters |
| `bootstrap` | Composition root: reads configuration, builds adapters, wires services, starts threads | everything | logic |

## 3. Ports

| Port | Capability | Real adapter | Other adapters |
| --- | --- | --- | --- |
| `FrameSource` | Newest camera frame, stamped at capture | webcam | session replay, synthetic fake |
| `ScenePerception` | Frame → zone distances and previews | GPU depth pipeline | geometry replay, scripted fake |
| `SceneReasoner` | Scene snapshot → streamed guidance | Gemini | scripted fake |
| `SpeechSynthesizer` | Text → PCM, streamed or whole | ElevenLabs | tone fake |
| `AudioSink` | Play PCM now, pre-emptibly | sound device | WAV file, recording fake |
| `EventPublisher` | Push events to observers | WebSocket web UI | JSON-lines log, collecting fake |
| `Clock` | Monotonic time | system | manual test clock |

`ScenePerception` deliberately hides the depth map. Tensors never cross a
port: the GPU pipeline, model choice and kernels are internal to one adapter,
and everyone else sees fifteen numbers and two JPEGs.

## 4. Application services

| Service | Reads | Does | Writes |
| --- | --- | --- | --- |
| `PerceptionLoop` | `FrameSource` | Runs `ScenePerception` on the newest frame | `SceneBoard`, `EventPublisher` |
| `HazardMonitor` | each new geometry | Applies `HazardPolicy` to obstacles inside the walking path; speaks when the alert rises, changes side or gets closer, confirmed over consecutive frames | `SpeechArbiter`, `EventPublisher` |
| `GuidanceLoop` | `SceneBoard` | Applies `SteeringPolicy` every frame (local, no network); applies `TriggerPolicy` and calls `SceneReasoner` in the background; speaks a cloud answer only if the scene still matches | `SpeechArbiter`, `EventPublisher` |
| `SpeechArbiter` | utterances | Applies `ArbitrationPolicy`: priority, pre-emption, staleness, repetition; resolves audio from phrase cache or `SpeechSynthesizer` | `AudioSink`, `EventPublisher` |

`SceneBoard` is the one shared in-memory structure: a thread-safe holder of
the newest perception result. Writers overwrite; readers take the latest.

## 5. Data flow

```
FrameSource ──Frame──▶ PerceptionLoop ──▶ ScenePerception
                              │
                              ▼ Perception
                         SceneBoard ───────────────────────┐
                              │                            │
                              ▼                            ▼
                        HazardMonitor                 GuidanceLoop ──▶ SceneReasoner
                              │ Utterance(HAZARD)          │ Utterance(GUIDANCE)
                              └────────────┬───────────────┘
                                           ▼
                                     SpeechArbiter ──▶ SpeechSynthesizer
                                           │
                                           ▼
                                       AudioSink

every service ──Event──▶ EventPublisher ──▶ web UI
```

## 6. Threads

| Thread | Runs | Blocks on |
| --- | --- | --- |
| Capture | `FrameSource` adapter | the camera |
| GPU | `PerceptionLoop`, then `HazardMonitor` inline | the GPU |
| Async loop | `GuidanceLoop`, `SpeechArbiter` network work, `SceneReasoner`, `SpeechSynthesizer`, web UI server | sockets |
| Audio callback | `AudioSink` adapter | the sound device |

Rules:

- Threads exchange data only through size-one mailboxes (`SceneBoard` and the
  frame mailbox) and through `SpeechArbiter.submit`, which is thread-safe.
- `HazardMonitor` runs in the GPU thread right after perception, so a hazard
  never waits for a thread hop.
- A hazard utterance can start playing without touching the async loop: the
  clip is in memory and the arbiter hands it to the sink directly.

## 7. Layout

```
src/navigator/
  domain/          frame.py  geometry.py  hazard.py  guidance.py  speech.py
                   phrases.py  events.py  policies/
  ports/           one module per port
  application/     perception_loop.py  hazard_monitor.py  guidance_loop.py
                   speech_arbiter.py  scene_board.py
  adapters/
    camera/        webcam, replay, fake
    perception/    gpu pipeline (backends, kernels), replay, fake
    reasoner/      gemini, fake
    speech/        elevenlabs, fake
    audio/         sound device, wav file, fake
    ui/            websocket server, static page, log publisher, fake
  bootstrap/       configuration and wiring
tests/
  domain/          policy tests, no I/O
  contract/        one suite per port, run against every adapter of that port
  application/     services wired to fakes
bench/             benchmark gates G1–G4
fixtures/          recorded sessions, sample scenes
```

## 8. Configuration

One configuration object selects an adapter per port and carries the tunable
numbers (thresholds, deadlines, model names, camera mount). The composition
root is the only place that reads it. Running entirely on fakes, entirely on
a replayed session, or with any mix of real and fake adapters is a
configuration change, not a code change. That mix is how each person works
before the others' adapters exist.

Run with `uv run navigator --preset all-fakes`; `--adapter port=name`
(repeatable) swaps one port, `--duration-s` stops the run. Presets:
`all-fakes`, `replay` (session replay, cloud fakes), `live` (every real
adapter), `phone` (phone camera and speaker, the rest real), `video`
(recorded frames through real GPU, Gemini and ElevenLabs, speech to a WAV
file) and `live-offline` (webcam and GPU, cloud fakes). A session comes from
`bench/record_session.py`, with `--camera webcam|phone` or from a video file
with `--video clip.mp4`. Secrets come from `.env` (`.env.sample` lists the keys); the value
`placeholder` counts as absent.

Adapter names and constructors. The composition root imports adapter modules
lazily, so a name may be registered before its module exists. Constructor
signatures are the seam between the bootstrap owner and the adapter owner;
changing one is a contract change.

| Port | Name | Class (under `navigator.adapters`) | Constructor | Lifetime |
| --- | --- | --- | --- | --- |
| `Clock` | `system` | `clock.system.SystemClock` | `()` | — |
| `Clock` | `manual` | `clock.manual.ManualClock` | `(start_ns=0)` | — |
| `FrameSource` | `synthetic` | `camera.synthetic.SyntheticFrameSource` | `(clock, width, height, fps)` | — |
| `FrameSource` | `webcam` | `camera.webcam.WebcamFrameSource` | `(clock, device, width, height, fps, fourcc)` | context manager |
| `FrameSource` | `replay` | `camera.replay.ReplayFrameSource` | `(clock, session_dir)` | context manager |
| `FrameSource` | `phone` | `phone.camera.PhoneFrameSource` | `(clock, link)` | — |
| `ScenePerception` | `scripted` | `perception.scripted.ScriptedScenePerception` | `(clock, rows, cols, horizontal_fov_deg, start_m, speed_mps)` | — |
| `ScenePerception` | `gpu` | `perception.gpu.GpuScenePerception` | `(clock, model, input_long_side, rows, cols, horizontal_fov_deg, scale, mount_height_m, pitch_deg)` | context manager |
| `ScenePerception` | `replay` | `perception.replay.ReplayScenePerception` | `(clock, session_dir)` | — |
| `SceneReasoner` | `scripted` | `reasoner.scripted.ScriptedSceneReasoner` | `(text, phrase, delay_s)` | — |
| `SceneReasoner` | `gemini` | `reasoner.gemini.GeminiSceneReasoner` | `(api_key, model, max_output_tokens)` | async context manager |
| `SpeechSynthesizer` | `tone` | `speech.tone.ToneSpeechSynthesizer` | `(delay_s, seconds_per_char)` | — |
| `SpeechSynthesizer` | `elevenlabs` | `speech.elevenlabs.ElevenLabsSpeechSynthesizer` | `(api_key, voice_id, model)` | async context manager |
| `AudioSink` | `recording` | `audio.recording.RecordingAudioSink` | `(clock)` | — |
| `AudioSink` | `wav` | `audio.wav.WavFileAudioSink` | `(path)` | context manager |
| `AudioSink` | `device` | `audio.device.SoundDeviceAudioSink` | `(device, block_frames)` | context manager |
| `AudioSink` | `phone` | `phone.audio.PhoneAudioSink` | `(clock, link)` | — |
| `EventPublisher` | `collecting` | `ui.collecting.CollectingEventPublisher` | `()` | — |
| `EventPublisher` | `log` | `ui.log.LogEventPublisher` | `(stream)` | — |
| `EventPublisher` | `web` | `ui.web.WebEventPublisher` | `(host, port)` | async context manager |

All arguments are keyword arguments with standard-library values (`Path`
for directories and files).

`phone.link.PhoneLink(host, port)` is the one connection to an iPhone browser
(async context manager, built once when either `phone` adapter is selected
and passed to both as `link`). It serves the capture page; frames go up and
speech comes down over one WebSocket, through a Cloudflare tunnel to port
8001.

## 9. Rules

- Hexagonal dependency rule, enforced by an import-check test.
- Every file under 300 lines.
- No comments in the repository; names, structure and tests carry intent.
- No backward compatibility: when a contract changes, every producer and
  consumer changes in the same pull request.
- A port has exactly one owner ([plan.md](plan.md)). Changing a port follows
  the change protocol in [contracts.md](contracts.md).
- Every port has a fake and a contract test suite before it has a real
  adapter.
- Domain policies are pure functions of their inputs and are tested without
  mocks.
