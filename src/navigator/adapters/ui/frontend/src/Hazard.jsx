export function Hazard({ hazard }) {
  if (!hazard) return <p className="hazard" data-level="none" aria-hidden="true" />;
  const distance = Number(hazard.distance_m).toFixed(2);
  return (
    <p className="hazard" data-level={hazard.level}>
      {hazard.level} {hazard.bearing}, {distance} m
    </p>
  );
}
