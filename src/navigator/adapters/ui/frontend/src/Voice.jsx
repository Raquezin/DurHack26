import { ThinkingOrb } from "thinking-orbs";

export function Voice({ speaking, label, text }) {
  return (
    <section className="voice" data-state={speaking ? "speaking" : "looking"}>
      <ThinkingOrb state="composing" size={64} color="#ff3b30" />
      {label && (
        <p className="source" data-source={label.source}>
          {label.source.toUpperCase()} · {label.ageMs} ms
        </p>
      )}
      <p className="text">{text}</p>
    </section>
  );
}
