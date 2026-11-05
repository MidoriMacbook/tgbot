import { writeFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Inbox, LayoutGrid, ChartNoAxesCombined, Settings2, ArrowRight, ArrowLeft, LogOut, Check, LockKeyhole, ListFilter, Clock3, UserRound, UsersRound, ExternalLink, ShieldCheck, Plus, RefreshCw } from "lucide-react";

const icons = { inbox: Inbox, grid: LayoutGrid, chart: ChartNoAxesCombined, settings: Settings2, arrow: ArrowRight, back: ArrowLeft, logout: LogOut, check: Check, lock: LockKeyhole, filter: ListFilter, clock: Clock3, user: UserRound, users: UsersRound, external: ExternalLink, shield: ShieldCheck, plus: Plus, refresh: RefreshCw };
let template = "{# Иконки Lucide (ISC), создаются frontend/scripts/generate-icons.mjs. #}\n";
Object.entries(icons).forEach(([name, Icon], index) => {
  template += `{% ${index ? "elif" : "if"} name == '${name}' %}`;
  template += renderToStaticMarkup(React.createElement(Icon, { className: "icon", width: 20, height: 20, strokeWidth: 1.7, "aria-hidden": "true", focusable: "false" }));
});
template += "{% endif %}\n";
writeFileSync(new URL("../../app/web/templates/web/icon.html", import.meta.url), template);
