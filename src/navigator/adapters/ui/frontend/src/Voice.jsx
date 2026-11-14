import { BotAvatar } from "bot-avatars";

import { botMotion } from "./motion.js";

const BOT_SIZE = 200;
const BOT_COLOR = "#A6C8E2";

export function Voice({ speaking, text, posture, hazardActive }) {
  const motion = botMotion(posture, hazardActive);
  return (
    <section
      className="voice"
      data-state={speaking ? "speaking" : "looking"}
      data-posture={hazardActive ? "halt" : posture}
    >
      <BotAvatar
        type="flower"
        theme="light"
        color={BOT_COLOR}
        size={BOT_SIZE}
        {...motion}
      />
      <div className="said">
        <p className="state">{speaking ? "Speaking" : "Looking"}</p>
        <p className="text">{text}</p>
      </div>
    </section>
  );
}
