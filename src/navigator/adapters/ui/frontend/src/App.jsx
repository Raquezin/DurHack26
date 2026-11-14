import { useCallback, useEffect, useRef, useState } from "react";

import { Feeds } from "./Feeds.jsx";
import { Voice } from "./Voice.jsx";
import { connect } from "./socket.js";
import { speechDurationMs } from "./speech.js";

const WAITING_TEXT = "Waiting for guidance";

export function App() {
  const [text, setText] = useState(WAITING_TEXT);
  const [speaking, setSpeaking] = useState(false);
  const [link, setLink] = useState("offline");
  const speechTimer = useRef(null);

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

  useEffect(() => {
    return connect({
      onLink: setLink,
      onEvent: (event) => {
        if (event.type === "utterance" && event.outcome === "spoken") startSpeaking(event.text);
        else if (event.type === "utterance" && event.outcome === "interrupted") stopSpeaking();
      },
    });
  }, [startSpeaking, stopSpeaking]);

  useEffect(() => {
    document.body.dataset.link = link;
  }, [link]);

  return (
    <main>
      <Feeds />
      <Voice speaking={speaking} text={text} />
    </main>
  );
}
