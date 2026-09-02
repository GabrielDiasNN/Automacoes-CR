import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Factory, LayoutDashboard, ListChecks, Menu, Radio, Rows3, Rows4, Search, Server, Workflow, X } from "lucide-react";
import { useApiKeyContext } from "../context/ApiKeyContext";
import { useTableDensity } from "../context/TableDensityContext";
import { StatusBar } from "./StatusBar";
import { CommandPalette } from "./CommandPalette";
import { ErrorBoundary } from "./ErrorBoundary";
import { IconButton } from "./ui";
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

export function Shell() {
  const [open, setOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { clearKey } = useApiKeyContext();
  const { density, toggleDensity } = useTableDensity();
  const location = useLocation();

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
        <aside className={`${styles.rail} ${open ? styles.railOpen : ""}`}>
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
            <StatusBar />
          </header>

          <main className={styles.content} id="conteudo">
            {/* key={pathname}: uma exceção de render numa página não deixa o
             *  usuário preso nela — trocar de rota sempre remonta o boundary. */}
            <ErrorBoundary key={location.pathname}>
              <Outlet />
            </ErrorBoundary>
          </main>
        </div>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} navItems={NAV} />
    </div>
  );
}
