import type { EvidenceItem } from "../types";

const MARK: Record<string, string> = {
  pass: "✓",
  fail: "✗",
  skip: "–",
  error: "!",
};

export default function EvidenceChecklist({ evidence }: { evidence: EvidenceItem[] }) {
  if (!evidence || evidence.length === 0) {
    return <p className="muted">No evidence recorded yet.</p>;
  }
  const total = evidence.reduce((sum, item) => sum + item.weight, 0);
  const earned = evidence.reduce(
    (sum, item) => sum + (item.status === "pass" ? item.weight : 0),
    0
  );
  return (
    <div className="checklist">
      <table>
        <thead>
          <tr>
            <th>Check</th>
            <th>Status</th>
            <th className="num">Weight</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {evidence.map((item) => (
            <tr key={item.key} className={`row-${item.status}`}>
              <td>{item.title}</td>
              <td>
                <span className={`badge badge-${item.status}`}>
                  {MARK[item.status]} {item.status.toUpperCase()}
                </span>
              </td>
              <td className="num">
                {item.status === "pass" ? item.weight : 0}/{item.weight}
              </td>
              <td className="details">{item.details}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        Earned {earned} of {total} possible points. Skipped checks contribute 0 and are not
        renormalized.
      </p>
    </div>
  );
}
