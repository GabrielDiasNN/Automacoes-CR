import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Factory, LayoutDashboard, ListChecks, Menu, Monitor, Moon, Radio, Rows3, Rows4, Search, Server, Sun, Workflow, X } from "lucide-react";
import { useApiKeyContext } from "../context/ApiKeyContext";
import { useTableDensity } from "../context/TableDensityContext";
import { useTheme, type Theme } from "../context/ThemeContext";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { mediaMaxWidth } from "../styles/breakpoints";
import { StatusBar } from "./StatusBar";
import { CommandPalette } from "./CommandPalette";
import { ErrorBoundary } from "./ErrorBoundary";
import { IconButton, Loading } from "./ui";
import styles from "./Shell.module.css";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  section?: string;
}

export const NAV: NavItem[] = [
  { to: "/painel", label: "Painel", icon: <LayoutDashboard size={16} />, section: "Operação" },
  { to: "/execucoes", label: "Execuções", icon: <ListChecks size={16} /> },
  { to: "/monitor", label: "Monitor", icon: <Radio size={16} /> },
  { to: "/beneficiamento", label: "Beneficiamento", icon: <Factory size={16} />, section: "Análise" },
  { to: "/automacoes", label: "Automações", icon: <Workflow size={16} />, section: "Administração" },
  { to: "/sistema", label: "Sistema", icon: <Server size={16} /> },
];

// Ciclo do ThemeContext: system -> light -> dark -> system.
const NEXT_THEME: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const THEME_LABEL: Record<Theme, string> = { system: "sistema", light: "claro", dark: "escuro" };
const THEME_ICON: Record<Theme, ReactNode> = {
  system: <Monitor size={16} />,
  light: <Sun size={16} />,
  dark: <Moon size={16} />,
};

export function Shell() {
  const [open, setOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { clearKey } = useApiKeyContext();
  const { density, toggleDensity } = useTableDensity();
  const { theme, cycleTheme } = useTheme();
  const location = useLocation();
  const railRef = useRef<HTMLElement>(null);
  // Mesmo breakpoint de Shell.module.css (`wide` em styles/breakpoints.ts):
  // só ABAIXO de 900px o rail vira gaveta fixed+translateX; em desktop ele
  // está sempre visível e `open` nunca chega a ser lido pelo CSS (o botão
  // hambúrguer nem aparece).
  const isMobileRail = useMediaQuery(mediaMaxWidth("wide"));
  const railHidden = isMobileRail && !open;

  // Abaixo de 900px o rail fechado é `translateX(-100%)` mas continuava no
  // DOM, focável e no tab order — um usuário de teclado tabulava para dentro
  // de um menu fora da tela sem indício visual algum. Focus trap real
  // (Escape fecha, Tab cicla) só quando de fato aberto como gaveta mobile.
  useFocusTrap(railRef, isMobileRail && open, () => setOpen(false));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={styles.shell}>
      <a href="#conteudo" className={styles.skip}>
        Pular para o conteúdo
      </a>
      <div className={`hazard ${styles.brandRail}`} aria-hidden="true" />

      <div className={styles.frame}>
        <aside
          ref={railRef}
          className={`${styles.rail} ${open ? styles.railOpen : ""}`}
          {...(railHidden ? { inert: "" } : {})}
        >
          <div className={styles.wordmark}>
            <div>
              <div className={styles.brand}>ORQUESTRADOR</div>
              <div className={styles.tagline}>// sala de instrumentação</div>
            </div>
            <IconButton className={styles.railClose} onClick={() => setOpen(false)} aria-label="Fechar menu de navegação">
              <X size={18} />
            </IconButton>
          </div>

          <nav className={styles.nav} aria-label="Navegação principal">
            {NAV.map((item) => (
              <div key={item.to}>
                {item.section && <div className={styles.section}>{item.section}</div>}
                <NavLink
                  to={item.to}
                  className={({ isActive }) => `${styles.link} ${isActive ? styles.linkActive : ""}`}
                  onClick={() => setOpen(false)}
                >
                  <span className={styles.linkIcon}>{item.icon}</span>
                  {item.label}
                </NavLink>
              </div>
            ))}
          </nav>

          <div className={styles.railFoot}>
            <button className={styles.logout} onClick={clearKey}>
              $ logout
            </button>
          </div>
        </aside>

        {open && <div className={styles.scrim} onClick={() => setOpen(false)} aria-hidden="true" />}

        <div className={styles.main}>
          <header className={styles.topbar}>
            <IconButton
              className={styles.menuBtn}
              onClick={() => setOpen((o) => !o)}
              aria-label="Alternar menu de navegação"
              aria-expanded={open}
            >
              <Menu size={18} />
            </IconButton>
            <IconButton
              onClick={() => setPaletteOpen(true)}
              aria-label="Busca global (Ctrl+K)"
              title="Busca global (Ctrl+K)"
            >
              <Search size={16} />
            </IconButton>
            <IconButton
              onClick={toggleDensity}
              aria-label={density === "compact" ? "Tabelas: modo compacto ativo — trocar para confortável" : "Tabelas: modo confortável ativo — trocar para compacto"}
              title={density === "compact" ? "Densidade de tabela: compacta" : "Densidade de tabela: confortável"}
            >
              {density === "compact" ? <Rows3 size={16} /> : <Rows4 size={16} />}
            </IconButton>
            <IconButton
              onClick={cycleTheme}
              aria-label={`Tema: ${THEME_LABEL[theme]} — trocar para ${THEME_LABEL[NEXT_THEME[theme]]}`}
              title={`Tema: ${THEME_LABEL[theme]}`}
            >
              {THEME_ICON[theme]}
            </IconButton>
            <StatusBar />
          </header>

          <main className={styles.content} id="conteudo">
            {/* key={pathname}: uma exceção de render numa página não deixa o
             *  usuário preso nela — trocar de rota sempre remonta o boundary.
             *  Suspense cobre o `React.lazy` de Monitor/Beneficiamento/Sistema
             *  (App.tsx) — code-splitting tira uPlot e os painéis mais
             *  pesados do bundle inicial. */}
            <ErrorBoundary key={location.pathname}>
              <Suspense fallback={<Loading label="carregando tela" />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </main>
        </div>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} navItems={NAV} />
    </div>
  );
}
