const BOUNDS = {
  perception: { p99: 25 },
  previews: { p99: 3 },
  hazard_decision: { p99: 30 },
  hazard: { p95: 150 },
  reasoner: { p50: 700 },
  tts: { p95: 350 },
  guidance: { p50: 1000 },
};

const PERCENTILES = ["p50", "p95", "p99"];

function format(ms) {
  return ms < 10 ? ms.toFixed(1) : String(Math.round(ms));
}

export function Latency({ stages }) {
  if (!stages.length) return null;
  return (
    <section className="latency">
      {stages.map((stage) => {
        const bounds = BOUNDS[stage.name] || {};
        return (
          <div className="stage" key={stage.name}>
            <span className="stage-name">{stage.name.replaceAll("_", " ")}</span>
            {PERCENTILES.map((p) => {
              const value = stage[`${p}_ms`];
              const bound = bounds[p];
              return (
                <span className="percentile" key={p}>
                  <span className="label">{p}</span>
                  <span className="value" data-over={bound !== undefined && value > bound || undefined}>
                    {format(value)}
                    {bound !== undefined && (
                      <span className="bound"> / {bound}</span>
                    )}
                  </span>
                </span>
              );
            })}
          </div>
        );
      })}
    </section>
  );
}
