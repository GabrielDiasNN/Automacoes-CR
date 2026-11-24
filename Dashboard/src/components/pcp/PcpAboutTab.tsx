import type { Automation, PromovidaResumo, PromovidaSnapshot } from "../../api/orchestrator";
import { formatAge, formatDateTimeBr, formatNumber } from "../../lib/format";
import { Card, DescriptionList, KeyValue, StatusTag } from "../ui";

interface PcpAboutTabProps {
  item: PromovidaResumo;
  snapshot: PromovidaSnapshot;
  linkedAutomation: Automation | null;
}

export function PcpAboutTab({ item, snapshot, linkedAutomation }: PcpAboutTabProps) {
  const origem = item.origem ?? snapshot.origem ?? "promovida";
  const origemLabel = origem === "automacao" ? "Automação operacional" : "Consulta promovida";
  const codigo = item.codigo ?? snapshot.codigo ?? "—";
  const setor = item.setor ?? snapshot.setor ?? "—";
  const modo = snapshot.modo || item.modo;
  const destinos = item.destinos.length > 0 ? item.destinos.join(", ") : "Nenhum destino configurado";
  const formattedDate = formatDateTimeBr(snapshot.generated_at);
  const ageLabel =
    snapshot.age_minutes !== null && snapshot.generated_at
      ? `${formattedDate} (${formatAge(snapshot.age_minutes * 60)})`
      : formattedDate;

  return (
    <Card label="Sobre / Regra de Negócio">
      <DescriptionList>
        <KeyValue k="Título" v={snapshot.titulo || item.titulo} />
        <KeyValue k="Código" v={codigo} />
        <KeyValue k="Slug" v={item.slug} />
        <KeyValue
          k="Origem"
          v={
            <StatusTag tone={origem === "automacao" ? "cyan" : "grey"} dot>
              {origemLabel}
            </StatusTag>
          }
        />
        <KeyValue k="Setor" v={setor} />
        <KeyValue
          k="Modo de execução"
          v={
            <StatusTag tone={modo === "sombra" ? "amber" : "green"} dot>
              {modo}
            </StatusTag>
          }
        />
        <KeyValue k="Destinos configurados" v={destinos} />
        <KeyValue k="Última atualização" v={ageLabel} />
        <KeyValue
          k="Linhas / Exceções"
          v={`${formatNumber(snapshot.total_rows)} linhas · ${formatNumber(snapshot.excecoes_count)} exceções`}
        />
        {linkedAutomation && (
          <>
            <KeyValue
              k="Status da automação"
              v={
                <StatusTag tone={linkedAutomation.enabled ? "green" : "amber"} dot>
                  {linkedAutomation.enabled ? "Ativa" : "Pausada"}
                </StatusTag>
              }
            />
            <KeyValue
              k="Modo sandbox"
              v={
                <StatusTag tone={linkedAutomation.test_mode ? "amber" : "cyan"} dot>
                  {linkedAutomation.test_mode ? "Sandbox (teste)" : "Produção"}
                </StatusTag>
              }
            />
            <KeyValue
              k="Agenda configurada"
              v={linkedAutomation.schedule_summary ?? linkedAutomation.schedule ?? "Manual / sem agenda"}
            />
            {linkedAutomation.description && (
              <KeyValue k="Descrição" v={linkedAutomation.description} />
            )}
          </>
        )}
      </DescriptionList>
    </Card>
  );
}
