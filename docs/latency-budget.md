# Latency Budget

End-to-end latency is the binding constraint ([project.md](project.md)). This
document turns that into numbers: what research says the upper bounds are, how
the budget is split per stage, and how we measure it.

Every figure is tagged:

- **[M]** — a measurement published by someone else (source in the last
  section). None of these were taken on our hardware or network.
- **[E]** — our engineering estimate. Unverified until we measure it.

Figures marked "ours" were measured by us; the benchmark gates in
[models.md](models.md) replace the remaining tags as they run.

## 1. What the research says

| Finding | Value | Tag |
| --- | --- | --- |
| End-to-end delay bound for wearable obstacle avoidance, from human response time | ≤ 320 ms | [M] Gao et al. 2025 |
| Simple reaction time to a sound (lab, button press) | 140–160 ms | [M] cited in Shelton & Kumar 2010 |
| Same, other student samples | 250–285 ms | [M] Shelton & Kumar 2010; IJMRR |
| Reaction time of blind subjects to spoken navigation commands | 1.47 s indoor, 1.66 s outdoor | [M] Adebiyi et al. 2017 |
| Blind/low-vision walking speed, no obstacles | ≈ 1.09 m/s | [M] cited in Sensors 2023 |
| Same, with cane among obstacles | ≈ 0.4 m/s | [M] cited in Sensors 2023 |
| Speeds used to test a head-mounted aid | 0.5, 0.75, 1.0 m/s | [M] Sensors 2023 |
| Alert type ranking for accuracy and reaction time | speech ≈ spearcons > auditory icons > earcons | [M] meta-analysis 2023 |
| Bluetooth audio delay, default SBC codec | ≈ 220 ms; 150–800 ms across A2DP | [M] Avantree; AES |
| Webcam glass-to-screen delay, OpenCV loop | ≈ 133 ms (one user report) | [M] anecdotal |

Consequences we adopt:

1. **Hazard alerts: ≤ 300 ms hard**, capture to first audio sample. This keeps
   20 ms under the 320 ms literature bound.
2. **Hazard alerts are speech, not beeps** — very short clips ("Stop").
   Speech beats abstract tones on both accuracy and reaction time, and
   pre-rendered clips cost no network time.
3. **Wired headphones only.** A default Bluetooth link alone would consume
   most of the hazard budget.
4. **Reaction time is outside our budget but inside the physics.** The user
   needs 0.15–0.3 s to react to "Stop" and about 1.5 s to act on a spoken
   direction. Alert distances (section 5) must cover both.

## 2. The two bounds

| Tier | Bound | Type |
| --- | --- | --- |
| Hazard | ≤ 300 ms capture → first audio sample | Hard. Above it the alert is useless. |
| Hazard | ≤ 150 ms p95 | Internal design target (section 3). |
| Guidance | ≤ 1.0 s p50 capture → first audio sample | Target. |
| Guidance | 5 s, and the scene must still match | Cloud answers past either are discarded, never spoken. Local guidance has no network term. |

The earlier "ideally ~600 ms" guidance figure is only reachable with a
~300 ms time-to-first-token model (section 4). With our default model, expect
about 1.0–1.2 s unless the phrase cache hits.

## 3. Hazard path budget

Camera → depth → zone distances → rule → cached clip. No network.

| Stage | Budget (ms) | Expected (ms) | Basis |
| --- | --- | --- | --- |
| Sensor exposure, USB, driver, wait for next frame | 70 | 35–100 | [E] glass-to-frame not yet measured; ours, G4: frame interval 32.1 ms p50, 36.5 ms p99 with `exposure_dynamic_framerate=0` |
| Upload + fused preprocess | 2 | 0.3 with zone reduction | ours, G1: perceive − forward at p50 |
| Depth network | 20 | 15.7 p50, 16.0 p99 | ours, G1 at long side 504 ([models.md](models.md)) |
| Zone reduction + result download | 2 | included above | ours, G1 |
| Hazard rule + speech arbiter | 1 | 0.16 p50, 0.79 p99 | ours, stage `hazard_decision` (section 8), 99 decisions |
| Cached clip → DAC | 25 | 10–25 | [E] small PortAudio buffer |
| Scheduling jitter | 30 | 0.7 p50, 1.2 p99 before perception; output side unmeasured | ours, stage `frame_wait` (section 8); [E] for the rest |
| **Total** | **150** | **≈ 60–140** | |

The other 150 ms under the hard bound is margin for thermal throttling on a
laptop GPU, garbage collection, and a webcam slower than assumed. The capture
stage is the largest and least controllable line; it is the first thing to
measure.

Measured at M1 (ours, RTX 5070 Ti Laptop, `UtteranceEvent.age_ms` of spoken
hazard clips: frame arrival → clip handed to the sink):

| Run | Spoken hazards | p50 ms | p95 ms | max ms |
| --- | --- | --- | --- | --- |
| `phone` preset, live walk to a wall | 47 | 17 | 18 | 37 |
| `video` preset, recorded walk replayed | 41 | 16 | 16 | 22 |

Both are far inside the 150 ms target. Not included: phone capture, JPEG
encode and upload before arrival, and playback on the phone after; the phone
link round trip is 48–55 ms through the Cloudflare tunnel. Glass-to-frame is
still unmeasured: the GPU machine is a remote server with no screen to flash.

## 4. Guidance path budget

Camera → geometry → trigger → Gemini → ElevenLabs → headphones, p50.

| Stage | Gemini 3.5 Flash-Lite | Basis |
| --- | --- | --- |
| Capture → SceneGeometry | 100 | [E] section 3 |
| Trigger, JPEG encode, request build | 10 | [E] |
| Network + time to first token | 806 | ours, G2 p50 with image; 1207 p95; 1.2–4.2 s on recorded walk frames at M1 |
| First phrase complete (≈ 12 tokens at ≈ 290 tokens/s) | 40 | [M] output speed |
| TTS time to first audio | 248 | ours, G3 p50; 272 p95 |
| Audio output | 25 | [E] |
| **Total, streamed TTS** | **≈ 1.23 s** | sum; over the 1.0 s target |
| **Total, phrase-cache hit (no TTS)** | **≈ 0.98 s** | sum |

Notes:

- Time to first token is the dominant term and the least certain. With our
  image payload it is 806 ms p50 (G2), above the 700 ms target.
- Published figures for the primary model range from 0.64 s (router
  production traffic) to 4.6 s (first answer token on a reasoning-heavy
  benchmark, thinking time included). Thinking must be pinned to its minimum.
- The phrase cache ([models.md](models.md)) removes the TTS term whenever the
  model answers with a phrase from the fixed catalogue.

What moves the cloud term (ours, 14 November, development network, a new
walk frame for every request, ms from request to answer):

| Request | n | First token p50 | Whole answer p50 | Range |
| --- | --- | --- | --- | --- |
| Image at long side 512, as shipped | 6 | 1149 | 1223 | 1053–1702 |
| Image at long side 256 | 8 | 1119 | 1176 | 787–1977 |
| 512, output constrained to phrase names | 5 | 1535 | 1616 | 1317–3218 |
| 256, output constrained to phrase names | 5 | 1190 | 1256 | 1041–2138 |
| Zone distances only, no image | 6 | 479 | 546 | 402–1094 |

- The image is the cost: about 265 input tokens at any size, and roughly
  0.7 s. A smaller JPEG and constrained output change nothing we can see;
  answers are already three or four tokens and complete about 50 ms after
  the first one. The samples are few because the key's free tier stopped
  the run (500 requests a day).
- So no payload change brings a request with an image under the 700 ms
  bound, and a request without one only sees what local steering already
  uses. Local steering with cached clips is the guidance path that meets
  the 1.0 s target (16 ms p50, section 8); a Gemini answer is an addition
  that arrives about 1.2–1.6 s after capture when the scene still matches.

## 5. Alert distance

Latency converts to distance: at 1 m/s every 100 ms is 10 cm of travel.

```
d_alert = ( v · (t_system + t_reaction) + d_brake ) / (1 − e_depth)
```

| Symbol | Value | Basis |
| --- | --- | --- |
| t_system | 0.30 s | hard bound |
| t_reaction | 0.28 s | [M] upper end of simple auditory reaction time |
| d_brake | 0.5 m | [E] one step to stop — assumption, no source |
| e_depth | 0.15 | [M] 12 % metric error of the primary depth model, rounded up |

| Walking speed | d_alert (primary model) | d_alert (e_depth = 0.30, fallback model uncalibrated) |
| --- | --- | --- |
| 0.5 m/s | 0.9 m | 1.1 m |
| 0.75 m/s | 1.1 m | 1.3 m |
| 1.0 m/s | 1.3 m | 1.5 m |

Starting thresholds, to be tuned in the room:

- **STOP** when the nearest obstacle in the walking corridor is < 1.5 m.
- **CAUTION** when it is < 3.0 m.
- Demo walking speed ≤ 0.75 m/s.

## 6. Guidance look-ahead

A spoken direction is acted on about 1.5 s after it is heard [M], and a
cloud answer may be 1.5 s old when it starts playing. The guidance tier must
therefore talk about what is

```
v · (1.5 s + 1.5 s) = 3 m ahead at 1.0 m/s, 1.5 m at 0.5 m/s
```

or further. This splits the scene between the tiers: the hazard tier owns
everything nearer than 3 m; the guidance tier reasons about the 3–5 m range
and route choice. The VLM prompt states this explicitly.

## 7. Upper bounds per inference stage

These are the limits each component owner must stay under. Exceeding one
means changing the model, resolution or technique, not relaxing the bound.

| Stage | Upper bound | Reason |
| --- | --- | --- |
| Fused preprocess | 1 ms p99 | noise next to the network |
| Depth network forward | 20 ms p99 | whole frame must fit in one 33 ms camera interval |
| Zone reduction + download | 1 ms p99 | same |
| Perception total per frame | 25 ms p99 | keeps 30 fps with headroom; no frame ever waits |
| Preview JPEG encode (camera + depth) | 3 ms p99 | runs after the hazard decision, never before it |
| Hazard decision → first audio sample | 30 ms p99 | fits section 3 |
| VLM time to first token | 700 ms p50 | keeps guidance near the 1.0 s target |
| VLM request abandoned | 5 s after capture | first token for a new image measured at 1.0 s p50, 11.4 s p95 (G2) |
| TTS time to first audio | 350 ms p95 | fits the 1.5 s deadline |
| Guidance cadence | ≤ 1 request in flight; on scene change, ≥ 2 s apart; every 8 s otherwise | cost, rate limits, no self-interruption |

## 8. How we measure

- **One clock.** Every frame is stamped with `time.monotonic_ns()` at capture.
  The stamp travels with every derived artefact ([contracts.md](contracts.md)),
  so any stage can compute its age.
- **Stage timestamps.** Every service records its stage durations into one
  `LatencyTrace`, which publishes a `timing` event once a second. The UI
  shows per-stage p50 / p95 / p99 over a sliding window of the last 600
  samples, next to the bound, in red when over it.
- **GPU timings** use synchronised measurements (CUDA events or an explicit
  synchronise) after warm-up; wall-clock around an asynchronous GPU call
  measures nothing.
- **Percentiles, not averages.** Bounds are p95 or p99. Averages hide the
  slow calls that cause collisions.
- **Glass-to-ear test.** The stamps start at frame arrival and miss sensor
  and DAC delay. Once per setup: film an LED and the headphone speaker with a
  phone in slow motion, with a rule that plays a click when the LED lights.
  The frame difference is the true end-to-end figure; the gap to the traced
  figure is the capture + DAC offset. That offset is a configuration value
  and is subtracted from the deadlines the software enforces.
- **Venue network.** Cloud figures are re-measured on the venue network at
  the start, and on a phone hotspot as fallback.

### Traced stages

| Stage | From → to | Recorded by | Bound |
| --- | --- | --- | --- |
| `frame_wait` | frame arrival → perception starts | `PerceptionLoop` | — |
| `perception` | perception starts → geometry ready | `PerceptionLoop` | 25 ms p99 |
| `previews` | geometry ready → previews encoded, preview frames only | `PerceptionLoop` | 3 ms p99 |
| `hazard_decision` | geometry ready → alert handed to the arbiter, which plays a cached clip in the same call | `HazardMonitor` | 30 ms p99 |
| `hazard` | frame arrival → first hazard audio handed to the sink | `SpeechArbiter` | 150 ms p95 |
| `reasoner` | request sent → first instruction back | `GuidanceLoop` | 700 ms p50 |
| `tts` | utterance submitted → first streamed chunk | `SpeechArbiter` | 350 ms p95 |
| `guidance` | frame arrival → first guidance audio handed to the sink | `SpeechArbiter` | 1.0 s p50 |

- `guidance` counts everything heard as guidance, local steering and cloud
  answers together. For a cloud answer alone, add the age of the geometry at
  the request (frame arrival → geometry published, below) to `reasoner`, and
  `tts` when the answer is not a catalogue phrase.
- `reasoner` ends at the first complete sentence, not the first token, and a
  request that times out leaves no sample. `tts` is recorded even when the
  utterance is then dropped as stale.
- `hazard_decision` includes the preview encode on preview frames, because
  the perception port returns previews together with the geometry.
- For figures over a whole run instead of the sliding window:
  `--set timing_window=20000 --set timing_interval_s=60`. The last `timing`
  event is published at shutdown and covers the run.

Measured with the trace (ours, RTX 5070 Ti Laptop, p50 / p95 / p99 in ms):

| Stage | Webcam device, 10 minutes, cloud fakes | Recorded walk looped for 150 s, real Gemini and ElevenLabs |
| --- | --- | --- |
| `frame_wait` | 0.69 / 0.89 / 1.16 | 0.19 / 0.36 / 0.42 |
| `perception` | 14.99 / 15.45 / 15.66 | 15.32 / 15.90 / 16.25 |
| `previews` | 0.51 / 0.65 / 0.69 | 0.46 / 0.56 / 0.59 |
| `hazard_decision` | one alert | 0.16 / 0.73 / 0.79 |
| `hazard` | one alert, 16.2 | 15.91 / 16.37 / 22.10 |
| `reasoner` | fake | 784 / 941 / 1018 |
| `tts` | fake | no samples: every answer was a catalogue phrase |
| `guidance` | none spoken | 16.3 / 812 / 816 |

- **Ten-minute run:** 17 779 frames, none skipped. The laptop webcam was
  shuttered and delivered its "camera off" placeholder, so this times the
  pipeline at 30 fps on a still image, not a real scene. Perception
  is 15.66 ms p99 against the 25 ms bound. Frame arrival → geometry published
  is 15.8–16.0 ms p50 and 16.7–17.1 ms p99 in every one of the ten minutes,
  so there is no drift; the GPU went from 41 °C to 47 °C.
- **Looped walk:** 43 hazard clips and 28 guidance clips spoken; Gemini
  returned 17 answers that still matched the scene. The walk is 10.7 s
  long, so Gemini saw each image many times, and it is faster on an image
  it has seen ([models.md](models.md), G2): 784 ms is flattering and does
  not replace the G2 result. Development network, not the venue.
- Not covered by the trace: sensor to frame arrival, and sink to ear. Both
  need the glass-to-ear test.
- **Cloud failure drills** on the recorded walk, real cloud adapters
  configured. Gemini refusing every request (quota, HTTP 429), 60 s: 17
  hazard clips at ≤ 17 ms and 11 local directions spoken, nothing from the
  cloud, no crash. Started with no network at all (empty network
  namespace, phrase cache already on disk), 45 s: 12 hazard clips at
  ≤ 20 ms and 9 local directions. Not yet drilled: the network dropping in
  the middle of a run.

## 9. Sources

- Gao et al., "A wearable obstacle avoidance device for visually impaired
  individuals with cross-modal learning", Nature Communications 2025 —
  https://pmc.ncbi.nlm.nih.gov/articles/PMC11933268/
- Shelton & Kumar, "Comparison between Auditory and Visual Simple Reaction
  Times", 2010 — https://www.scirp.net/journal/paperinformation?paperid=2689
- IJMRR reaction time study —
  https://ijmrr.medresearch.in/index.php/ijmrr/article/view/628
- Adebiyi et al., "Assessment of feedback modalities for wearable visual aids
  in blind mobility", 2017 — https://pmc.ncbi.nlm.nih.gov/articles/PMC5300186/
- "Intelligent Head-Mounted Obstacle Avoidance Wearable for the Blind and
  Visually Impaired", Sensors 2023 — https://www.mdpi.com/1424-8220/23/23/9598
- "Auditory Icons, Earcons, Spearcons, and Speech" meta-analysis, 2023 —
  https://www.tandfonline.com/doi/full/10.1080/25742442.2023.2219201
- Bluetooth codec delay — https://support.avantree.com/hc/en-us/articles/31257100736793-Different-Bluetooth-Codecs-Latency
  and https://secure.aes.org/forum/pubs/ebriefs/?elib=17406
- Webcam latency report —
  https://stackoverflow.com/questions/70597020/lower-latency-from-webcam-cv2-videocapture
- Model and API latency sources are listed in [models.md](models.md).
