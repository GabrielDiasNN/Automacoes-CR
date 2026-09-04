import { describe, expect, it } from "vitest";
import {
  countByLevel,
  filterLines,
  parseLine,
  parseLog,
  type Level,
} from "../lib/logParser";

describe("parseLine", () => {
  it("extrai hora, origem e nível do cabeçalho padrão", () => {
    const linha = parseLine("[30/07/2026 08:30:05] [PS] [INFO] mensagem qualquer");
    expect(linha.time).toBe("30/07/2026 08:30:05");
    expect(linha.source).toBe("PS");
    expect(linha.level).toBe("info");
    expect(linha.message).toBe("mensagem qualquer");
  });

  it("descarta blocos extras entre o nível e a mensagem", () => {
    const linha = parseLine(
      "[30/07/2026 08:30:05] [PS] [ERROR] [ExecId:CRON_2_1785411000] falhou feio",
    );
    expect(linha.level).toBe("error");
    expect(linha.message).toBe("falhou feio");
  });

  it("normaliza as variantes de nível usadas pelos scripts PT-BR", () => {
    expect(parseLine("[t] [s] [ERRO] x").level).toBe("error");
    expect(parseLine("[t] [s] [WARNING] x").level).toBe("warn");
    expect(parseLine("[t] [s] [WARN] x").level).toBe("warn");
    expect(parseLine("[t] [s] [DEBUG] x").level).toBe("debug");
    expect(parseLine("[t] [s] [info] x").level).toBe("info");
  });

  it("trata linha sem cabeçalho como plain preservando o texto", () => {
    const linha = parseLine("saída crua do PowerShell");
    expect(linha.level).toBe("plain");
    expect(linha.time).toBeNull();
    expect(linha.source).toBeNull();
    expect(linha.message).toBe("saída crua do PowerShell");
  });

  it("cai para o raw quando a mensagem do cabeçalho é vazia", () => {
    const linha = parseLine("[t] [s] [INFO]   ");
    expect(linha.message).toBe("[t] [s] [INFO]   ");
  });
});

describe("parseLine — evento estruturado (JSON Lines)", () => {
  const base = {
    ts: "2026-08-27T07:01:51Z",
    component: "python_domain",
    automation: "OBs Restricao Branco",
    exec_id: "CRON_6_x",
    trace_id: "orb-20260827T070140Z-a4f2",
  };

  it("mapeia envelope de evento 'log' para a forma LogLine", () => {
    const linha = parseLine(
      JSON.stringify({ ...base, level: "WARN", event: "log", step: "dispatch", message: "OB #185260 estoque insuficiente" }),
    );
    expect(linha.level).toBe("warn");
    expect(linha.source).toBe("PY");
    expect(linha.event).toBe("log");
    expect(linha.step).toBe("dispatch");
    expect(linha.traceId).toBe("orb-20260827T070140Z-a4f2");
    expect(linha.message).toContain("estoque insuficiente");
  });

  it("resume execution.end com código, motivo e contadores", () => {
    const linha = parseLine(
      JSON.stringify({
        ...base,
        level: "INFO",
        event: "execution.end",
        message: "fim",
        outcome_code: 2,
        outcome_reason: "idempotente: nada a notificar",
        duration_ms: 11120,
        record_counts: { read: 120, notified: 0 },
        steps: [],
      }),
    );
    expect(linha.level).toBe("info");
    expect(linha.message).toContain("code=2");
    expect(linha.message).toContain("idempotente: nada a notificar");
    expect(linha.message).toContain("read=120");
  });

  it("formata step.end com duração e marca de sucesso", () => {
    const linha = parseLine(
      JSON.stringify({ ...base, level: "INFO", event: "step.end", step: "extract", ok: true, duration_ms: 8300, message: "120 lidas" }),
    );
    expect(linha.message).toContain("✓ extract");
    expect(linha.message).toContain("8.3s");
  });

  it("normaliza ERRO -> error e mantém texto legado quando não é JSON", () => {
    expect(parseLine(JSON.stringify({ ...base, level: "ERRO", event: "log", message: "x" })).level).toBe("error");
    expect(parseLine("[t] [s] [INFO] linha legada").source).toBe("s");
  });

  it("JSON malformado ou objeto sem envelope cai para plain/legado", () => {
    expect(parseLine("{isso não é json}").level).toBe("plain");
    expect(parseLine(JSON.stringify({ foo: 1 })).level).toBe("plain");
  });
});

describe("parseLog", () => {
  it("ignora linhas em branco", () => {
    expect(parseLog("\n\n   \n")).toEqual([]);
  });

  it("anexa continuações à última linha com cabeçalho", () => {
    const linhas = parseLog(
      ["[t] [s] [ERROR] stack trace a seguir", "  at Foo.bar()", "  at Baz.qux()"].join("\n"),
    );
    expect(linhas).toHaveLength(1);
    expect(linhas[0]!.message).toBe("stack trace a seguir\n  at Foo.bar()\n  at Baz.qux()");
  });

  it("não funde linhas quando a anterior também é plain", () => {
    const linhas = parseLog(["saida crua 1", "saida crua 2"].join("\n"));
    expect(linhas).toHaveLength(2);
  });

  it("aceita CRLF", () => {
    const linhas = parseLog("[t] [s] [INFO] um\r\n[t] [s] [INFO] dois");
    expect(linhas).toHaveLength(2);
    expect(linhas[1]!.message).toBe("dois");
  });
});

describe("countByLevel", () => {
  it("conta por nível incluindo os zerados", () => {
    // A linha plain vem PRIMEIRO de propósito: depois de uma linha com
    // cabeçalho ela seria absorvida como continuação, não contada à parte.
    const linhas = parseLog(
      ["cru", "[t] [s] [ERROR] a", "[t] [s] [ERROR] b", "[t] [s] [INFO] c"].join("\n"),
    );
    expect(countByLevel(linhas)).toEqual({ error: 2, info: 1, plain: 1, warn: 0, debug: 0 });
  });
});

describe("filterLines", () => {
  const linhas = parseLog(
    ["[t] [s] [ERROR] falha de conexao", "[t] [s] [INFO] conexao ok", "[t] [s] [DEBUG] detalhe"].join(
      "\n",
    ),
  );

  it("conjunto de níveis vazio não filtra nada", () => {
    expect(filterLines(linhas, new Set<Level>(), "")).toHaveLength(3);
  });

  it("filtra pelos níveis ativos", () => {
    expect(filterLines(linhas, new Set<Level>(["error"]), "")).toHaveLength(1);
  });

  it("busca é case-insensitive e ignora espaços em volta", () => {
    expect(filterLines(linhas, new Set<Level>(), "  CONEXAO  ")).toHaveLength(2);
  });

  it("combina nível e busca", () => {
    const r = filterLines(linhas, new Set<Level>(["info"]), "conexao");
    expect(r).toHaveLength(1);
    expect(r[0]!.message).toBe("conexao ok");
  });
});
