import { useCallback, useEffect, useRef, useState } from "react";

import { Feeds, usePreviews } from "./Feeds.jsx";
import { Hazard } from "./Hazard.jsx";
import { Voice } from "./Voice.jsx";
import { connect } from "./socket.js";
import { speechDurationMs } from "./speech.js";

const HAZARD_HOLD_MS = 1200;
const WAITING_TEXT = "Waiting for guidance";

export function App() {
  const previews = usePreviews();
  const [text, setText] = useState(WAITING_TEXT);
  const [speaking, setSpeaking] = useState(false);
  const [hazard, setHazard] = useState(null);
  const [link, setLink] = useState("offline");
  const speechTimer = useRef(null);
  const hazardTimer = useRef(null);

  const stopSpeaking = useCallback(() => {
    clearTimeout(speechTimer.current);
    setSpeaking(false);
  }, []);

  const startSpeaking = useCallback(
    (spoken) => {
      clearTimeout(speechTimer.current);
      setText(spoken);
      setSpeaking(true);
      speechTimer.current = setTimeout(stopSpeaking, speechDurationMs(spoken));
    },
    [stopSpeaking],
  );

  const showHazard = useCallback((event) => {
    clearTimeout(hazardTimer.current);
    setHazard(event);
    hazardTimer.current = setTimeout(() => setHazard(null), HAZARD_HOLD_MS);
  }, []);

  const showPreview = previews.show;
  useEffect(() => {
    return connect({
      onLink: setLink,
      onPreview: showPreview,
      onEvent: (event) => {
        if (event.type === "utterance" && event.outcome === "spoken") startSpeaking(event.text);
        else if (event.type === "utterance" && event.outcome === "interrupted") stopSpeaking();
        else if (event.type === "hazard") showHazard(event);
      },
    });
  }, [showPreview, startSpeaking, stopSpeaking, showHazard]);

  useEffect(() => {
    document.body.dataset.link = link;
  }, [link]);

  return (
    <main>
      <Feeds camera={previews.camera} depth={previews.depth} />
      <Voice speaking={speaking} text={text} />
      <Hazard hazard={hazard} />
    </main>
  );
}
