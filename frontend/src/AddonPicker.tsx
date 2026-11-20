// «الإضافات»: a multi-select of the add-ons a customer bought, separate from the well type.
// Stored as one text ("خزان, خروف ×2") so the sheets and older data keep working. Any value already
// saved that is not in the list (old workbook text) stays selected and can be removed.
import { useState } from "react";
import { useI18n } from "./i18n";

const SPLIT = /\s*[,،;+]\s*/;
const QTY = /^(.*?)\s*(?:[×x*]\s*(\d+)|\((\d+)\))$/;
const SHEEP = new Set(["خروف", "خاروف", "sheep", "lamb"]);

export const splitAddons = (v: string | null | undefined) => (v || "").split(SPLIT).map((x) => x.trim()).filter(Boolean);
const nameQty = (tok: string): [string, number] => { const m = tok.match(QTY); return m ? [m[1].trim(), Number(m[2] || m[3])] : [tok.trim(), 1]; };
export const isSheep = (tok: string) => SHEEP.has(nameQty(tok)[0].toLowerCase());

export function AddonPicker({ value, options, onChange, sheepNote }: { value: string | null | undefined; options: string[];
  onChange: (v: string | null) => void; sheepNote?: boolean }) {
  const { t } = useI18n();
  const [other, setOther] = useState("");
  const items = splitAddons(value);
  const byName = new Map(items.map((i) => [nameQty(i)[0], i]));
  const all = [...options, ...[...byName.keys()].filter((n) => !options.includes(n))];
  const emit = (next: string[]) => onChange(next.length ? next.join(", ") : null);
  const toggle = (name: string) => emit(byName.has(name) ? items.filter((i) => nameQty(i)[0] !== name) : [...items, name]);
  const setQty = (name: string, q: number) => emit(items.map((i) => (nameQty(i)[0] === name ? (q > 1 ? `${name} ×${q}` : name) : i)));
  const addOther = () => { const v = other.trim().replace(/[,،]/g, " "); if (v && !byName.has(v)) emit([...items, v]); setOther(""); };
  return (
    <div className="addons" role="group" aria-label={t("addons")}>
      <div className="addon-chips">
        {all.map((name) => {
          const on = byName.has(name);
          const q = on ? nameQty(byName.get(name)!)[1] : 1;
          return <span key={name} className={`addon-chip${on ? " on" : ""}`}>
            <label><input type="checkbox" checked={on} onChange={() => toggle(name)} /> {name}</label>
            {on && isSheep(name) && <span className="addon-qty">
              <button type="button" className="sm" aria-label="−" disabled={q <= 1} onClick={() => setQty(name, q - 1)}>−</button>
              <b className="num" aria-live="polite">{q}</b>
              <button type="button" className="sm" aria-label="+" onClick={() => setQty(name, q + 1)}>+</button>
            </span>}
          </span>;
        })}
        <span className="addon-other">
          <input value={other} placeholder={t("addon_other")} onChange={(e) => setOther(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addOther(); } }} aria-label={t("addon_other")} />
          {other.trim() && <button type="button" className="sm" onClick={addOther}>＋</button>}
        </span>
      </div>
      {!items.length && <span className="hint muted">{t("addons_none")}</span>}
      {sheepNote && items.some(isSheep) && <span className="hint muted">🐑 {t("addon_sheep_note")}</span>}
    </div>
  );
}

/** The chosen add-ons as small read-only chips (tables, cards, details). */
export function AddonChips({ value }: { value: string | null | undefined }) {
  const items = splitAddons(value);
  if (!items.length) return <span className="muted">—</span>;
  return <span className="addon-list">{items.map((i) => <span key={i} className="chip">{i}</span>)}</span>;
}
