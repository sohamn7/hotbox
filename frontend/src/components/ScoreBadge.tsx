interface Props {
  score: number;
  size?: "sm" | "md";
}

export default function ScoreBadge({ score, size = "sm" }: Props) {
  const color =
    score >= 70
      ? "bg-green-100 text-green-800"
      : score >= 40
      ? "bg-yellow-100 text-yellow-800"
      : "bg-red-100 text-red-800";

  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span className={`inline-block font-semibold rounded-full ${color} ${padding}`}>
      {score}
    </span>
  );
}
