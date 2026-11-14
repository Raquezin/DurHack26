import { BotAvatar } from "bot-avatars";

const BOT_SIZE = 200;
const BOT_COLOR = "#A6C8E2";

export function Voice({ speaking, text }) {
  return (
    <section className="voice" data-state={speaking ? "speaking" : "looking"}>
      <BotAvatar
        type="flower"
        theme="light"
        color={BOT_COLOR}
        size={BOT_SIZE}
        state={speaking ? "working" : "default"}
      />
      <div className="said">
        <p className="state">{speaking ? "Speaking" : "Looking"}</p>
        <p className="text">{text}</p>
      </div>
    </section>
  );
}
