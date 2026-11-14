# Contracts

The data types and interfaces that cross ownership boundaries. These are
frozen at the end of Phase 0 ([plan.md](plan.md)). Everything not listed here
is private to its owner and can change freely.

Layering and threads are described in [architecture.md](architecture.md).

## 1. Invariants

1. **Provenance.** Every artefact carries the `frame_id` and `t_capture_ns`
   of the frame it was derived from. Age is always `now − t_capture_ns`.
2. **One clock.** All timestamps are monotonic nanoseconds from the `Clock`
   port. Wall-clock time is never used for latency.
3. **Latest wins.** No unbounded queues. Producers overwrite; consumers read
   the newest.
4. **Units.** Metres, degrees, nanoseconds. Left and right are the user's.
5. **Audio.** PCM, signed 16-bit little-endian, mono, 24 000 Hz, everywhere.
6. **Deadlines.** Hazard utterances: `t_capture_ns + 300 ms`. Local
   guidance: `t_capture_ns + 1000 ms`. Cloud guidance: `t_capture_ns +
   5000 ms`, and only while the scene still matches the frame it was asked
   about. All are reduced by the measured capture and output offset, a
   configuration value. An utterance past its deadline before its first
   sample plays is dropped.
7. **Immutability.** All contract types are frozen. Nothing is mutated after
   it is published.
8. **No tensors.** Contract types hold only standard-library values.

## 2. Data types

```python
@dataclass(frozen=True, slots=True)
class Frame:
    frame_id: int
    t_capture_ns: int
    width: int
    height: int
    pixels: bytes


@dataclass(frozen=True, slots=True)
class SceneGeometry:
    frame_id: int
    t_capture_ns: int
    rows: int
    cols: int
    distances_m: tuple[float, ...]
    valid: tuple[bool, ...]
    horizontal_fov_deg: float


@dataclass(frozen=True, slots=True)
class Perception:
    geometry: SceneGeometry
    t_ready_ns: int
    camera_jpeg: bytes | None
    depth_jpeg: bytes | None


@dataclass(frozen=True, slots=True)
class HazardAlert:
    level: HazardLevel
    bearing: Bearing
    distance_m: float
    frame_id: int
    t_capture_ns: int


@dataclass(frozen=True, slots=True)
class GuidanceRequest:
    geometry: SceneGeometry
    camera_jpeg: bytes
    recently_spoken: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GuidanceInstruction:
    phrase: PhraseId | None
    text: str
    frame_id: int
    t_capture_ns: int


@dataclass(frozen=True, slots=True)
class Utterance:
    priority: Priority
    phrase: PhraseId | None
    text: str
    frame_id: int
    t_capture_ns: int
    deadline_ns: int


@dataclass(frozen=True, slots=True)
class PcmChunk:
    samples: bytes
```

| Type | Field | Meaning |
| --- | --- | --- |
| `Frame` | `frame_id` | Strictly increasing per session |
| | `t_capture_ns` | Stamped when the frame reaches the process |
| | `pixels` | BGR, 8 bits per channel, row-major, `width × height × 3` bytes |
| `SceneGeometry` | `rows`, `cols` | Zone grid; 3 × 5 by default |
| | `distances_m` | Row-major, length `rows × cols`. Robust nearest non-floor surface in the zone. `inf` when nothing is within 10 m |
| | `valid` | False when the zone had too few usable pixels; its distance must then be ignored |
| | `horizontal_fov_deg` | Lets consumers turn a column into a bearing |
| `Perception` | `t_ready_ns` | When the geometry became available |
| | `camera_jpeg`, `depth_jpeg` | Previews; `None` on frames where they were skipped |
| `GuidanceRequest` | `recently_spoken` | Last few spoken texts, newest last, so the reasoner does not repeat itself |
| `GuidanceInstruction` | `phrase` | Set when the instruction is exactly a catalogue phrase; `text` is then the catalogue text |
| `Utterance` | `deadline_ns` | Set by the producer according to invariant 6 |
| `PcmChunk` | `samples` | Invariant 5; even number of bytes |

Grid orientation:

| | col 0 | col 1 | col 2 | col 3 | col 4 |
| --- | --- | --- | --- | --- | --- |
| row 0 — head height | far left | left | ahead | right | far right |
| row 1 — torso | far left | left | ahead | right | far right |
| row 2 — legs, low obstacles | far left | left | ahead | right | far right |

Enumerations:

| Enum | Values, in order |
| --- | --- |
| `HazardLevel` | `CAUTION`, `STOP` |
| `Bearing` | `LEFT`, `AHEAD`, `RIGHT` |
| `Priority` | `HAZARD`, `GUIDANCE`, `DESCRIPTION` — earlier pre-empts later |

## 3. Phrase catalogue

Identifiers are frozen; wording is owned by the guidance owner. Every phrase
is pre-rendered into the phrase cache at startup.

| `PhraseId` | Text | Used by |
| --- | --- | --- |
| `STOP` | "Stop." | hazard |
| `CAUTION_AHEAD` | "Careful, obstacle ahead." | hazard |
| `CAUTION_LEFT` | "Obstacle on your left." | hazard |
| `CAUTION_RIGHT` | "Obstacle on your right." | hazard |
| `VEER_LEFT` | "Move a little left." | guidance |
| `VEER_RIGHT` | "Move a little right." | guidance |
| `TURN_LEFT` | "Turn left." | guidance |
| `TURN_RIGHT` | "Turn right." | guidance |
| `GO_STRAIGHT` | "Keep going straight." | guidance |
| `PATH_CLEAR` | "Path is clear." | guidance |
| `SLOW_DOWN` | "Slow down." | guidance |
| `DOOR_AHEAD` | "Door ahead." | guidance |

## 4. Ports

```python
class Clock(Protocol):
    def now_ns(self) -> int: ...


class FrameSource(Protocol):
    def next_frame(self, after_frame_id: int, timeout_s: float) -> Frame | None: ...


class ScenePerception(Protocol):
    def warm_up(self) -> None: ...
    def perceive(self, frame: Frame, with_previews: bool) -> Perception: ...


class SceneReasoner(Protocol):
    def advise(self, request: GuidanceRequest) -> AsyncIterator[GuidanceInstruction]: ...


class SpeechSynthesizer(Protocol):
    def stream(self, text: str) -> AsyncIterator[PcmChunk]: ...
    async def render(self, text: str) -> PcmChunk: ...


class AudioSink(Protocol):
    def play(self, chunk: PcmChunk) -> None: ...
    def interrupt(self) -> None: ...
    def is_playing(self) -> bool: ...


class EventPublisher(Protocol):
    def publish(self, event: Event) -> None: ...
```

| Port | Behaviour every adapter must have |
| --- | --- |
| `FrameSource.next_frame` | Returns the newest frame with `frame_id > after_frame_id`, skipping older ones; `None` on timeout. Never returns the same frame twice |
| `ScenePerception.perceive` | Result carries the input's `frame_id` and `t_capture_ns`. `distances_m` and `valid` have length `rows × cols`. Distances are positive or `inf` |
| `ScenePerception.warm_up` | After it returns, `perceive` meets its latency bound from the first call |
| `SceneReasoner.advise` | Yields zero or more instructions, each carrying the request's `frame_id`. Stops promptly when the consumer stops iterating. Provider failures end the stream; they do not raise into the caller's loop |
| `SpeechSynthesizer.stream` | First chunk is non-empty. Stops promptly when the consumer stops iterating |
| `SpeechSynthesizer.render` | Whole utterance as one chunk; used to build the phrase cache |
| `AudioSink.play` | Non-blocking; appends to what is playing |
| `AudioSink.interrupt` | Silence within one audio block; pending audio discarded |
| `EventPublisher.publish` | Non-blocking, thread-safe; drops events when no observer is connected or an observer is slow |

Adapters that hold a device, socket or GPU context are context managers. The
composition root owns their lifetime.

## 5. Shared application interfaces

Two application objects are called across ownership boundaries.

```python
class SceneBoard:
    def put(self, perception: Perception) -> None: ...
    def latest(self) -> Perception | None: ...
    async def wait_newer(self, frame_id: int, timeout_s: float) -> Perception | None: ...


class SpeechArbiter:
    def submit(self, utterance: Utterance) -> None: ...
```

| Call | Guarantee |
| --- | --- |
| `SceneBoard.put` | Thread-safe; overwrites |
| `SceneBoard.latest` | Thread-safe; newest value or `None` before the first frame |
| `SpeechArbiter.submit` | Thread-safe, non-blocking, callable from any thread. The arbiter decides whether and when the utterance is heard |

Arbitration rules, visible to every producer:

1. A higher priority interrupts a lower one that is playing.
2. Equal priority: the newer utterance replaces one that has not started.
3. An utterance past its deadline is dropped.
4. The same phrase is not repeated within its cool-down unless the hazard
   level rose.
5. Every outcome is published as an event.

## 6. Events

`Event` is a tagged union published to the UI and the log. Over the
WebSocket, JSON events are text messages and previews are binary messages.

| `type` | Payload | Producer |
| --- | --- | --- |
| `geometry` | `frame_id`, `distances_m`, `valid`, `age_ms` | `PerceptionLoop` |
| `hazard` | `level`, `bearing`, `distance_m`, `frame_id` | `HazardMonitor` |
| `guidance_text` | `request_id`, `delta`, `final` | `GuidanceLoop` |
| `utterance` | `text`, `priority`, `outcome`, `age_ms` | `SpeechArbiter` |
| `timing` | stage name → p50, p95, p99 in ms | every service |
| `preview` | `kind` (`camera` or `depth`), `frame_id`, `jpeg` | `PerceptionLoop` |

`outcome` is one of `spoken`, `dropped_stale`, `dropped_repeat`,
`replaced`, `interrupted`.

A `preview` event is sent as the binary message: byte 0 is the kind
(1 camera, 2 depth), bytes 1–8 the `frame_id` as a big-endian integer, the
rest a JPEG. Every other event is a JSON text message with a `type` field;
`inf` distances are sent as `null`.

In code each event type is a frozen dataclass in `domain/events.py`
(`GeometryEvent`, `HazardEvent`, `GuidanceTextEvent`, `UtteranceEvent`,
`TimingEvent`, `PreviewEvent`) with a class-level `type` tag, and `Event` is
their union. `TimingEvent.stages` is a tuple of `StageTiming(name, p50_ms,
p95_ms, p99_ms)`; `outcome` is the `Outcome` enum and `kind` the
`PreviewKind` enum.

## 7. Fakes and fixtures

Every port has a fake that needs no hardware, no network and no keys.

| Port | Fake behaviour |
| --- | --- |
| `FrameSource` | Synthetic frames at 30 fps; replay adapter plays a recorded session at its original timing |
| `ScenePerception` | Scripted geometry (for example a wall approaching at 0.5 m/s); replay adapter returns the recorded geometry for each frame |
| `SceneReasoner` | Returns a scripted instruction after a configurable delay |
| `SpeechSynthesizer` | Returns a tone whose length follows the text length, after a configurable delay |
| `AudioSink` | Records what was played and when |
| `EventPublisher` | Collects events in memory |
| `Clock` | Advanced manually by tests |

Fixtures:

- `fixtures/scenes/` — hand-written `SceneGeometry` samples with a matching
  JPEG: clear corridor, wall ahead at 1 m, obstacle left, doorway. Written in
  Phase 0. Used for policy tests and prompt development.
- `fixtures/sessions/<name>/` — a recorded walk: frames plus one
  `SceneGeometry` per frame as JSON lines. Recorded by the perception owner
  at milestone M1 and replayed by everyone.

## 8. Contract tests

`tests/contract/` has one suite per port, parametrised over every adapter of
that port, asserting the behaviours in section 4. A new adapter is done when
the suite passes for it. Suites for real adapters that need hardware or keys
are marked and skipped where those are absent.

## 9. Change protocol

1. Open a pull request that changes this document and the types together.
2. All three owners approve.
3. The same pull request updates the fakes, the contract tests and every
   producer and consumer. There is no compatibility period.
4. Additive changes to the phrase catalogue need only the guidance owner and
   one other approval.
