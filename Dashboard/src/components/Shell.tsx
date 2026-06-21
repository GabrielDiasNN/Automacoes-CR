import { useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Factory, LayoutDashboard, ListChecks, Menu, Radio, Server, Workflow } from "lucide-react";
import { useApiKeyContext } from "../context/ApiKeyContext";
import { StatusBar } from "./StatusBar";
import styles from "./Shell.module.css";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  section?: string;
}

const NAV: NavItem[] = [
  { to: "/painel", label: "Painel", icon: <LayoutDashboard size={16} />, section: "Operação" },
  { to: "/execucoes", label: "Execuções", icon: <ListChecks size={16} /> },
  { to: "/observabilidade", label: "Observabilidade", icon: <Radio size={16} /> },
  { to: "/beneficiamento", label: "Beneficiamento", icon: <Factory size={16} />, section: "Análise" },
  { to: "/automacoes", label: "Automações", icon: <Workflow size={16} />, section: "Administração" },
  { to: "/sistema", label: "Sistema", icon: <Server size={16} /> },
];

export function Shell() {
  const [open, setOpen] = useState(false);
  const { clearKey } = useApiKeyContext();

  return (
    <div className={styles.shell}>
      <a href="#conteudo" className={styles.skip}>
        Pular para o conteúdo
      </a>
      <div className={`hazard ${styles.brandRail}`} aria-hidden="true" />

      <div className={styles.frame}>
        <aside className={`${styles.rail} ${open ? styles.railOpen : ""}`}>
          <div className={styles.wordmark}>
            <div className={styles.brand}>ORQUESTRADOR</div>
            <div className={styles.tagline}>// sala de instrumentação</div>
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
            <button
              className={styles.menuBtn}
              onClick={() => setOpen((o) => !o)}
              aria-label="Alternar menu de navegação"
              aria-expanded={open}
            >
              <Menu size={18} />
            </button>
            <StatusBar />
          </header>

          <main className={styles.content} id="conteudo">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
