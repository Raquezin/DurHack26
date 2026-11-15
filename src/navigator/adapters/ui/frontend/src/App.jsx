import { useCallback, useEffect, useRef, useState } from "react";

import { Feeds, useFeeds } from "./Feeds.jsx";
import { Latency } from "./Latency.jsx";
import { useRoute } from "./Route.jsx";
import { Voice } from "./Voice.jsx";
import { connect } from "./socket.js";
import { speechDurationMs } from "./speech.js";

const GUIDANCE_MATCH_MS = 6000;
const HAZARD_HOLD_MS = 2000;
const TAGS_HOLD_MS = 12000;
const WAITING_TEXT = "Waiting for guidance";

export function App() {
  const feeds = useFeeds();
  const route = useRoute();
  const [text, setText] = useState(WAITING_TEXT);
  const [speaking, setSpeaking] = useState(false);
  const [label, setLabel] = useState(null);
  const [hazard, setHazard] = useState(null);
  const [link, setLink] = useState("offline");
  const [stages, setStages] = useState([]);
  const [tags, setTags] = useState({ frameId: null, list: [] });
  const speechTimer = useRef(null);
  const hazardTimer = useRef(null);
  const tagsTimer = useRef(null);
  const guidanceTexts = useRef([]);

  const stopSpeaking = useCallback(() => {
    clearTimeout(speechTimer.current);
    setSpeaking(false);
  }, []);

  const startSpeaking = useCallback(
    (event) => {
      clearTimeout(speechTimer.current);
      setText(event.text);
      setSpeaking(true);
      const now = Date.now();
      guidanceTexts.current = guidanceTexts.current.filter(
        (entry) => now - entry.at <= GUIDANCE_MATCH_MS,
      );
      const source =
        event.priority === "hazard"
          ? "hazard"
          : guidanceTexts.current.some((entry) => entry.text === event.text)
            ? "gemini"
            : "local";
      setLabel({ source, ageMs: Math.round(event.age_ms) });
      speechTimer.current = setTimeout(
        stopSpeaking,
        speechDurationMs(event.text),
      );
    },
    [stopSpeaking],
  );

  const showHazard = useCallback((event) => {
    clearTimeout(hazardTimer.current);
    setHazard(event);
    hazardTimer.current = setTimeout(() => setHazard(null), HAZARD_HOLD_MS);
  }, []);

  const showTags = useCallback((event) => {
    clearTimeout(tagsTimer.current);
    setTags({ frameId: event.frame_id, list: event.tags });
    tagsTimer.current = setTimeout(
      () => setTags({ frameId: null, list: [] }),
      TAGS_HOLD_MS,
    );
  }, []);

  const onFeedsPreview = feeds.onPreview;
  const onRoute = route.onRoute;
  useEffect(() => {
    return connect({
      onLink: setLink,
      onPreview: onFeedsPreview,
      onEvent: (event) => {
        if (event.type === "utterance" && event.outcome === "spoken")
          startSpeaking(event);
        else if (event.type === "utterance" && event.outcome === "interrupted")
          stopSpeaking();
        else if (event.type === "timing") setStages(event.stages);
        else if (event.type === "hazard") showHazard(event);
        else if (event.type === "tags") showTags(event);
        else if (event.type === "route") onRoute(event);
        else if (event.type === "guidance_text")
          guidanceTexts.current.push({ text: event.delta, at: Date.now() });
      },
    });
  }, [
    onFeedsPreview,
    onRoute,
    startSpeaking,
    stopSpeaking,
    showHazard,
    showTags,
  ]);

  useEffect(() => {
    document.body.dataset.link = link;
  }, [link]);

  return (
    <main>
      <Feeds
        feeds={feeds}
        route={route}
        hazard={hazard}
        tags={tags}
        link={link}
      />
      <Voice speaking={speaking} label={label} text={text} />
      <Latency stages={stages} />
    </main>
  );
}
