const CROSSING = /crossing|crosswalk|zebra/;
const TRAFFIC =
  /\b(road|street|traffic|car|bus|truck|vehicle|bike|bicycle|motorcycle|scooter|tram)s?\b/;

export function tagLevel(tag) {
  if (CROSSING.test(tag)) return "stop";
  if (TRAFFIC.test(tag)) return "caution";
  return "plain";
}

export function Tags({ tags }) {
  if (tags.length === 0) return null;
  const ordered = [...tags].sort(
    (a, b) => Number(tagLevel(b) === "stop") - Number(tagLevel(a) === "stop"),
  );
  return (
    <ul className="tags" aria-label="Visible in the scene">
      {ordered.map((tag) => (
        <li key={tag} data-level={tagLevel(tag)}>
          {tag}
        </li>
      ))}
    </ul>
  );
}
