// Master Sheet: every well in one Excel-style grid.
import { useI18n } from "../i18n";
import WellsGrid from "../book/WellsGrid";

export default function Sheet() {
  const { t } = useI18n();
  return (
    <>
      <div className="topbar"><h1>{t("nav_sheet")}</h1></div>
      <p className="muted" style={{ marginTop: -8 }}>{t("sheet_help")}</p>
      <WellsGrid height="calc(100vh - 230px)" />
    </>
  );
}
