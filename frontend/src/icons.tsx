// One icon set for the whole system (line icons, same weight everywhere), so menus, cards and buttons
// look the same. The sheep is drawn here in the same style because the icon set has none.
import type { ComponentType, SVGProps } from "react";
export type IconC = ComponentType<any>;
export {
  LayoutDashboard, Droplets, Wallet, Landmark, Users, UserRound, MessageCircle, Image, CircleCheck, Film, Clapperboard,
  Table2, FolderKanban, HardHat, Truck, Wrench, Images, Search, Bell, Settings, ChartColumn, ClipboardCheck, Hash, GitMerge,
  Pencil, Download, Upload, Phone, CalendarDays, MapPin, Package, ScrollText, Menu, House, ChevronDown, LogOut, Languages,
  KeyRound, Inbox, BadgeCheck, CircleDollarSign, TrendingUp, Clock, TriangleAlert, Sparkles, Globe, Eye, Share2, RotateCcw,
  Plus, HandCoins, Award, CirclePlay,
} from "lucide-react";

export function Sheep({ size = 24, strokeWidth = 2, ...rest }: SVGProps<SVGSVGElement> & { size?: number | string; strokeWidth?: number | string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      <path d="M7 15a3 3 0 0 1-1.8-5.4A3 3 0 0 1 9.5 6.3a3 3 0 0 1 5 0 3 3 0 0 1 4.3 3.3A3 3 0 0 1 17 15H7z" />
      <path d="M5.2 9.6 3.5 9a1.6 1.6 0 0 0-1.4 1.9l.3 1.1A1.8 1.8 0 0 0 4.6 13" />
      <path d="M8.5 15v4M11 15v4M13.5 15v4M16 15v4" />
    </svg>);
}

/** WhatsApp's colour; a plain chat-bubble drawing (not the WhatsApp logo). */
export function WhatsAppGlyph({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M12 2a10 10 0 0 0-8.7 14.9L2 22l5.3-1.3A10 10 0 1 0 12 2zm0 2a8 8 0 1 1-4.1 14.9l-.3-.2-3 .8.8-2.9-.2-.3A8 8 0 0 1 12 4z" />
      <path fill="currentColor" d="M8.6 7.5c.2-.4.4-.4.7-.4h.5c.2 0 .4 0 .6.5l.8 1.9c.1.2 0 .5-.1.6l-.5.6c-.1.2-.2.3 0 .6.6 1 1.4 1.8 2.5 2.4.3.2.5.1.6 0l.7-.8c.2-.2.4-.2.6-.1l1.8.9c.3.1.4.3.4.5 0 .6-.3 1.3-.8 1.6-.6.4-1.4.5-2.5.1a9.4 9.4 0 0 1-4.6-4.1c-.7-1.2-.9-2.3-.4-3.2z" />
    </svg>);
}

/** A tiny line chart for KPI cards (no axes); the last point is the current month. */
export function Sparkline({ values, color = "currentColor", height = 36 }: { values: number[]; color?: string; height?: number }) {
  if (!values.length) return null;
  const w = 120, h = height, max = Math.max(1, ...values), min = Math.min(0, ...values);
  const x = (i: number) => (values.length === 1 ? w : (i * w) / (values.length - 1));
  const y = (v: number) => h - 3 - ((v - min) / (max - min || 1)) * (h - 6);
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true" style={{ height }}>
      <polyline points={`0,${h} ${pts} ${w},${h}`} fill={color} opacity=".12" stroke="none" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>);
}
