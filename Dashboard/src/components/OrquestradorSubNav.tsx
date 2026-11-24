import { NavLink } from "react-router-dom";
import { ListChecks, Radio, Server, Workflow } from "lucide-react";
import styles from "./OrquestradorSubNav.module.css";

const SUB_ITEMS = [
  { to: "/automacoes", label: "Automações & Agendas", icon: <Workflow size={14} /> },
  { to: "/execucoes", label: "Execuções & Resultados", icon: <ListChecks size={14} /> },
  { to: "/monitor", label: "Console & Telemetria", icon: <Radio size={14} /> },
  { to: "/sistema", label: "Saúde & Manutenção", icon: <Server size={14} /> },
];

export function OrquestradorSubNav() {
  return (
    <nav className={styles.bar} aria-label="Subseções de Orquestrador e Sistema">
      {SUB_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
        >
          <span className={styles.icon} aria-hidden="true">
            {item.icon}
          </span>
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
