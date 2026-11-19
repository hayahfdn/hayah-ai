// The small "open" icon beside every project number (Hayah, 2026-11-19).
// It goes straight to the project's own existing page: a well opens its project page with the edit form
// open and its plaque shown; a sacrifice opens its existing plaque page with its details. It is separate
// from clicking the number and from the row's other buttons (it stops the click from reaching them).
import { Link } from "react-router-dom";
import { useI18n } from "./i18n";

export const openPath = (kind: "well" | "sacrifice", no: number | string) =>
  kind === "well" ? `/projects/${no}?edit=1` : `/plaque/sacrifice/${no}`;

export default function OpenIcon({ kind = "well", no }: { kind?: "well" | "sacrifice"; no: number | string }) {
  const { t } = useI18n();
  const label = `${t("open_project")} ${no}`;
  return (
    <Link className="open-ico" to={openPath(kind, no)} title={label} aria-label={label}
      onClick={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
        <path d="M6 3H3.5A1.5 1.5 0 0 0 2 4.5v8A1.5 1.5 0 0 0 3.5 14h8a1.5 1.5 0 0 0 1.5-1.5V10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M9 2h5v5M14 2 7.5 8.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </Link>
  );
}
