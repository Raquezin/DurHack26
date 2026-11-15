# Plan — Three People, Three Vertical Slices

How the work in [project.md](project.md) is split so that three people build
in parallel without waiting on, or colliding with, each other.

Owners are written as **A**, **B** and **C**; put names on them at kickoff.

## 1. How we avoid overlap

1. **Contracts first.** The types and ports in [contracts.md](contracts.md)
   are agreed and frozen before anyone writes an adapter. After that, nobody
   needs anyone else's code to compile, run or test their own.
2. **Vertical slices, not layers.** Each person owns one path from an input
   contract to something observable, including its policy, service, adapters,
   tests and benchmarks. Nobody owns "the backend" or "the models".
3. **A fake for every port.** Each slice runs alone from the first hour, with
   fakes standing in for the other two.
4. **One owner per directory.** After Phase 0 no file has two editors.
5. **Integration is configuration.** Swapping a fake for a real adapter is a
   configuration change ([architecture.md](architecture.md)), so we integrate
   at every merge instead of at the end.
6. **Contract tests.** An adapter that passes its port's suite can be dropped
   in without a meeting.
7. **A recorded session** gives B and C real perception data without the
   camera or the GPU.

Assumption: one machine has the GPU and the camera. It is A's workstation.
B and C work on their own laptops with fakes and replay until milestone M1.

## 2. The three slices

| | A — Perception | B — Guidance | C — Alerts, audio and UI |
| --- | --- | --- | --- |
| Slice | Camera in, fifteen distances out | Scene in, spoken guidance out | Distances in, sound in the ears and pixels on the screen |
| Tier | Feeds both | Guidance tier (cloud) | Hazard tier (local), output, observability |
| Ports implemented | `FrameSource`, `ScenePerception` | `SceneReasoner`, `SpeechSynthesizer` | `AudioSink`, `EventPublisher` |
| Services | `PerceptionLoop` | `GuidanceLoop` | `HazardMonitor`, `SpeechArbiter`, `SceneBoard` |
| Policies | — | `TriggerPolicy`, prompt, phrase wording | `HazardPolicy`, `ArbitrationPolicy` |
| Also owns | GPU kernels, model backends, calibration, session recording | Connection management, phrase rendering | Phrase cache, composition root, latency tracing |
| Gates | G1, G1b, G4 | G2, G3 | glass-to-ear test |
| Latency bound | Perception ≤ 25 ms p99 | First token ≤ 700 ms p50; first audio ≤ 350 ms p95 | Decision → first sample ≤ 30 ms p99 |
| Runs alone as | Live zone grid and depth preview in the log | Fixture scene → Gemini → ElevenLabs → WAV file | Scripted approaching wall → "Stop" in headphones; UI on fake frames |

Directory ownership:

| Owner | Directories and files |
| --- | --- |
| A | `adapters/camera/`, `adapters/perception/`, `application/perception_loop.py`, `fixtures/sessions/`, `bench/` G1 G1b G4 |
| B | `adapters/reasoner/`, `adapters/speech/`, `application/guidance_loop.py`, `domain/policies/trigger.py`, `domain/policies/steering.py`, `domain/phrases.py`, `fixtures/scenes/`, `bench/` G2 G3 |
| C | `adapters/audio/`, `adapters/ui/`, `application/hazard_monitor.py`, `application/speech_arbiter.py`, `application/scene_board.py`, `domain/policies/hazard.py`, `domain/policies/arbitration.py`, `domain/path.py`, `bootstrap/` |
| Frozen, steward C | `domain/` contract types, `ports/` — changed only through the protocol in [contracts.md](contracts.md) |

Tests live beside ownership: each owner writes the contract suites for their
ports and the tests for their policies and services.

## 3. Who waits for whom

Nobody, by construction. Each dependency has a stand-in from Phase 0.

| Consumer | Needs | From | Stand-in until it lands |
| --- | --- | --- | --- |
| B `GuidanceLoop` | perception results | A | scripted fake, `fixtures/scenes/`; recorded session after A4 |
| C `HazardMonitor` | perception results | A | scripted fake (wall approaching at 0.5 m/s) |
| C web UI | camera and depth previews | A | synthetic frame source |
| C phrase cache | `SpeechSynthesizer.render` | B | tone fake |
| B `GuidanceLoop` | `SpeechArbiter.submit` | C | collecting stand-in |
| A | nothing | — | — |

## 4. Phases

Shares are of the total time available. Hour marks assume a 24-hour event;
scale them if it is not.

| Phase | Share | Hours | Mode | Ends with |
| --- | --- | --- | --- | --- |
| 0 — Walking skeleton | 5 % | 0–1 | together | contracts frozen, all-fakes pipeline runs |
| 1 — Thin real slices | 35 % | 1–9 | parallel | M1: first live end-to-end run |
| 2 — Fast and good | 35 % | 9–18 | parallel | M2: blindfold walk within the latency bounds |
| 3 — Harden and present | 25 % | 18–24 | together | demo |

### Phase 0 — Walking skeleton

Even this hour is split three ways, then closed together.

| Owner | Task | Done when |
| --- | --- | --- |
| A | Environment: pin Python, PyTorch with CUDA, CuPy, depth backend; check camera formats | one script imports everything on the GPU and lists camera modes |
| B | Keys and access: Gemini (both candidate models), ElevenLabs; secrets file ignored by git | one script gets a streamed token and an audio chunk |
| C | Skeleton: contract types, ports, a fake per port, composition root, test runner, import-rule and file-length checks | `all-fakes` configuration prints geometry → hazard → utterance events |
| all | Read [contracts.md](contracts.md) against the code; fix; freeze | three approvals on the skeleton pull request |

### Phase 1 — Thin real slices

Goal: the simplest real version of every adapter. No optimisation yet.

| ID | Task | Done when |
| --- | --- | --- |
| A1 | Webcam `FrameSource`: newest frame only, stamped at arrival | contract suite passes; G4 measured |
| A2 | `ScenePerception` v1: primary depth model on the simplest backend; zone reduction as plain tensor operations | contract suite passes on live frames |
| A3 | Gates G1 and G1b; choose model and input size | numbers posted; decision recorded in [models.md](models.md) |
| A4 | Record a walk; replay adapters for both ports | `fixtures/sessions/` replays on a laptop with no GPU |
| B1 | ElevenLabs `SpeechSynthesizer`: `render` and `stream` | contract suite passes; G3 measured |
| B2 | Gemini `SceneReasoner`: streamed, prompt v1 | contract suite passes; G2 measured for both models |
| B3 | `GuidanceLoop` with `TriggerPolicy` v1: fixed cadence, one request in flight, deadline set | fixture scene produces a spoken instruction in a WAV file |
| B4 | Render the phrase catalogue through `render` | every `PhraseId` has a clip |
| C1 | `HazardPolicy` and `HazardMonitor` | policy tests cover thresholds from [latency-budget.md](latency-budget.md); scripted wall raises `STOP` |
| C2 | Sound-device `AudioSink`: low-latency stream, `interrupt` | contract suite passes; interrupt audible within one block |
| C3 | `SpeechArbiter` v1 and phrase cache: priority, pre-emption, deadline drop | service tests on the manual clock |
| C4 | Web UI v1: camera square, depth square, log panel | renders the all-fakes run |

**Milestone M1 — first live run.** Configuration switches every port to its
real adapter on the GPU machine.

- Walking towards a wall produces "Stop". Traced hazard latency ≤ 150 ms p95.
- Guidance is spoken from the live scene.
- The UI shows camera, depth and the log.

### Phase 2 — Fast and good

Goal: meet every bound in [latency-budget.md](latency-budget.md) and make the
instructions worth following.

| ID | Task | Done when |
| --- | --- | --- |
| A5 | Kernels K1, K2 with floor rejection, K3 and GPU JPEG ([optimization.md](optimization.md)) | each matches its reference on recorded frames; before/after posted |
| A6 | Fast backend, warm-up, pinned upload, no allocation in the loop | perception ≤ 25 ms p99 over a 10-minute run |
| A7 | Calibration: intrinsics, scale check, mount height and pitch | G1b ≤ 15 % at 1, 2 and 3 m |
| B5 | Prompt v2: prefers phrase identifiers, respects the 2–5 m look-ahead, never repeats | expected-instruction table over `fixtures/scenes/` and the recorded session |
| B6 | `TriggerPolicy` v2: fires on scene change with a minimum interval; abandons at 1.0 s; cancels on hazard | policy tests on the manual clock |
| B7 | Connection warm-up and reuse, image size, phrase forwarding; rerun G2 and G3 on the venue network | first token ≤ 700 ms p50; guidance ≤ 1.0 s p50 end to end |
| C5 | `ArbitrationPolicy` v2: cool-downs, repeat suppression, escalation; hazard smoothing over consecutive frames | no alert chatter on the recorded session; no missed `STOP` |
| C6 | Latency panel: per-stage p50, p95, p99; glass-to-ear test | measured table replaces the estimates in [latency-budget.md](latency-budget.md) |
| C7 | UI v2: live camera and depth pictures, utterance outcomes, connection state | a judge can read the pipeline at a glance |

**Milestone M2 — blindfold walk.** One person walks the demo route
blindfolded.

- No collision; every `STOP` within the 300 ms bound.
- Guidance ≤ 1.0 s p50; nothing spoken past 1.5 s.
- Ten minutes without a crash or a latency drift.

### Phase 3 — Harden and present

Features freeze at M2. Everyone works on the demo.

| Owner | Task |
| --- | --- |
| A | Lighting and camera-unplug robustness; fallback model switch rehearsed; stretch: YUYV kernel, closing-speed estimate |
| B | Network-loss behaviour (silence, never stale speech); hotspot fallback rehearsed; stretch: describe-on-demand |
| C | Demo script and route; threshold tuning in the room; backup recording of a good run; latency figures for the pitch |
| all | Three full rehearsals; failure drills; documents updated with measured numbers |

## 5. Working agreements

- **Trunk-based.** Short branches, merged several times per phase. `main`
  always runs on the all-fakes configuration.
- **Checks on every pull request:** tests, import rule, 300-line limit, no
  comments.
- **Pull requests stay inside the author's directories.** One that does not
  is a contract change and follows the protocol.
- **Three sync points only:** end of Phase 0, M1, M2. Ten minutes each:
  numbers against bounds, blockers, contract change requests.
- **Numbers go in the documents.** A gate result is recorded where its
  estimate was.
- **The demo configuration is exercised from M1 on**, not assembled at the
  end.

## 6. Risks

| Risk | Owner | Mitigation |
| --- | --- | --- |
| Venue network slow or blocked | B | Measure in Phase 0; hotspot tested; hazard tier needs no network |
| First token too slow on the primary model | B | Try the faster model first; phrase cache; smaller image; priority tier |
| Depth scale wrong in the room | A | Calibration A7; fallback thresholds in [latency-budget.md](latency-budget.md) |
| Laptop GPU throttles | A | 10-minute run in A6; fallback model; lower input size |
| Webcam latency above budget | A | G4 in the first hours; other format or camera |
| Alert chatter or missed alerts | C | Smoothing and cool-downs in C5, tuned on the recorded session |
| Audio device latency | C | Wired headphones; small buffer; glass-to-ear test |
| Depth backend dependency too new | A | TensorRT path is the alternative ([models.md](models.md)) |
| Integration surprises late | all | Config-only integration from M1; contract tests |
| API quota or cost | B | One request in flight, minimum interval, change detection. The key's free tier allows 500 requests a day and ran out on 14 November; the demo needs a billed key |

## 7. Definition of done

- A blindfolded person walks the demo route guided only by the system.
- Hazard and guidance latencies are measured, displayed live, and within the
  bounds.
- The UI shows what the camera sees, what the model perceives and what the
  system says.
- With the network unplugged, hazard alerts still work and nothing stale is
  spoken.
- Every document states measured numbers, not estimates.

## 8. Demo sprint, 2026-11-15 06:45 to 07:35

Evidence from the recorded phone walks: the voice said only "Stop. Turn
left/right." and every column read about 1 m. The chest-worn phone tilts
down, the floor model assumes it is level, so the floor reads as a wall.

| Time | Step | Done when |
| --- | --- | --- |
| 06:45 to 07:05 | Estimate camera pitch from the floor every frame instead of assuming level | Clear corridor reads 3 m or more on the phone |
| 07:05 to 07:15 | Walk with the recorder running | "Keep going straight" and "Move a little left/right" appear in the log |
| 07:15 to 07:25 | Tune stop distance, confirmation frames and repeat interval from the recording | One full walk without a false "Stop" |
| 07:25 to 07:35 | Commit, freeze, rehearse the demo route twice | Demo route walked twice with correct guidance |

After the demo: use labels in decisions (person ahead, door, stairs) and get
the new phrases approved under the contract change protocol.
