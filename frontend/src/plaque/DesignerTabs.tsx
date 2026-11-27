// The designer's tabs (Hayah, 22 Nov 2026): well plaque, sacrifice plaque, Haram water plaque (27 Nov),
// endowment certificate and the official contract. The open order follows you between tabs when it fits: a well opens its
// certificate and contract, a sacrifice opens its contract.
import { useNavigate } from "react-router-dom";
import { useI18n } from "../i18n";

export type DesignerTab = "well" | "sacrifice" | "suqya" | "certificate" | "contract";

export default function DesignerTabs({ on, wellId, sacNo }: { on: DesignerTab; wellId?: string | number; sacNo?: string | number }) {
  const { t } = useI18n();
  const nav = useNavigate();
  const to: Record<DesignerTab, string> = {
    well: wellId ? `/plaque/${wellId}` : "/plaque",
    sacrifice: sacNo ? `/plaque/sacrifice/${sacNo}` : "/plaque/sacrifice",
    suqya: "/plaque/suqya",
    certificate: wellId ? `/plaque/certificate/${wellId}` : "/plaque/certificate",
    contract: wellId ? `/plaque/contract/well/${wellId}` : sacNo ? `/plaque/contract/sacrifice/${sacNo}` : "/plaque/contract",
  };
  const label: Record<DesignerTab, string> = { well: t("pl_tab_well"), sacrifice: t("pl_tab_sac"), suqya: t("sq_tab"), certificate: t("cert_title"), contract: t("ct_tab") };
  return (
    <div className="tabs designer-tabs" role="tablist">
      {(Object.keys(to) as DesignerTab[]).map((k) => (
        <button type="button" role="tab" aria-selected={on === k} key={k} className={on === k ? "on" : ""} onClick={() => nav(to[k])}>{label[k]}</button>))}
    </div>);
}

/** The simple drawn hand pump, for the icon picker (the plaque draws the same shape). */
export function PumpGlyph({ size = 52, color = "#111" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="-50 -62 100 128" aria-hidden="true">
      <g fill={color} stroke={color} strokeLinecap="round">
        <rect x="-14" y="-38" width="28" height="92" rx="6" stroke="none" />
        <rect x="-24" y="50" width="48" height="10" stroke="none" />
        <circle cx="0" cy="-42" r="13" stroke="none" />
        <path d="M-12 -20 L-34 -16 L-38 -4" fill="none" strokeWidth="10" />
        <path d="M10 -42 Q34 -40 36 -10 Q38 14 26 24" fill="none" strokeWidth="6" />
        <circle cx="26" cy="28" r="6" stroke="none" />
      </g>
    </svg>);
}
