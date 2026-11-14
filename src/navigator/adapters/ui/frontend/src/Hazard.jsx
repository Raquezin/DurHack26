const LABELS = { stop: "Stop", caution: "Caution" };

export function Hazard({ hazard }) {
  if (!hazard) return null;
  const distance = Number(hazard.distance_m).toFixed(2);
  return (
    <p className="hazard" data-level={hazard.level}>
      {LABELS[hazard.level]} {hazard.bearing} · {distance} m
    </p>
  );
}
