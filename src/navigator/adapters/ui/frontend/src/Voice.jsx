import { ThinkingOrb } from "thinking-orbs";

export function Voice({ speaking, text }) {
  return (
    <section className="voice" data-state={speaking ? "speaking" : "looking"}>
      <ThinkingOrb state="composing" size={64} color="#ff3b30" />
      <p className="text">{text}</p>
    </section>
  );
}
