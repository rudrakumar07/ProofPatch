export default function DiffViewer({ diff, path }: { diff: string; path?: string }) {
  if (!diff) return <p className="muted">No diff available.</p>;
  const lines = diff.replace(/\n$/, "").split("\n");
  return (
    <div className="diff-viewer">
      {path && <div className="diff-path">{path}</div>}
      <pre>
        {lines.map((line, index) => {
          const cls = line.startsWith("+")
            ? "diff-add"
            : line.startsWith("-")
              ? "diff-del"
              : line.startsWith("@@")
                ? "diff-hunk"
                : line.startsWith("diff --git") || line.startsWith("---") || line.startsWith("+++")
                  ? "diff-meta"
                  : "";
          return (
            <div key={index} className={cls}>
              {line || " "}
            </div>
          );
        })}
      </pre>
    </div>
  );
}
