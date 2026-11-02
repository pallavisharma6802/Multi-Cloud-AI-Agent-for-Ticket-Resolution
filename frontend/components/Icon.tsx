import React from "react";
const paths: Record<string, string> = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  inbox: "M4 4h16v16H4z M4 14h5l2 3h2l2-3h5",
  chart: "M4 20V10 M10 20V4 M16 20v-8 M22 20H2",
  plus: "M12 5v14 M5 12h14",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  search: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  spark: "m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3z",
  check: "m5 12 4 4L19 6",
  clock: "M12 7v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  refresh:
    "M20 7V2l-4 4 M4 17v5l4-4 M4 10a8 8 0 0 1 13-6l3 3 M20 14a8 8 0 0 1-13 6l-3-3",
  cloud: "M6 18a5 5 0 1 1 0-10 7 7 0 0 1 13 1 4.5 4.5 0 0 1-1 9z",
  chevron: "m9 5 7 7-7 7",
  shield: "m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6z m-4 10 3 3 5-6",
  external: "M14 3h7v7 M21 3l-11 11 M10 3H3v18h18v-7",
  filter: "M3 5h18 M6 12h12 M9 19h6",
  copy: "M8 8h13v13H8z M16 8V3H3v13h5",
  bolt: "m13 2-9 12h7l-1 8 10-13h-7z",
};
export default function Icon({
  name,
  size = 20,
  ...rest
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      <path d={paths[name] || paths.spark} />
    </svg>
  );
}
