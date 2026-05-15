export function CandidateGrade({ grade }: { grade: "S" | "A" | "B" | "C" }) {
  const className =
    grade === "S" ? "pill good" : grade === "A" ? "pill" : grade === "B" ? "pill warn" : "pill bad";

  return <span className={className}>{grade} 级</span>;
}
