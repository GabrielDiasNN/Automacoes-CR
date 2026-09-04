import { act, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// MonitorPage precisa de LiveStatusContext (health/worker/status + fan-out de
// eventos), usePolling (histórico + métricas diárias) e orchestratorApi —
// nenhum deles é o alvo deste teste, então são substituídos por dublês
// mínimos, no mesmo padrão de LiveStatusContext.test.tsx.
let liveEventHandler: ((e: MessageEvent) => void) | null = null;

// MonitorPage importa `TimeSeries`, que importa `uplot` — sua construção toca
// `matchMedia`/`<canvas>`, que o jsdom não implementa. O gráfico não é
// renderizado neste teste (sem dados de histórico), mas o módulo é carregado
// de qualquer forma na importação estática; stub mínimo como em
// TimeSeries.render.test.tsx.
vi.mock("uplot", () => ({ default: vi.fn(() => ({ setData: vi.fn(), setSize: vi.fn(), destroy: vi.fn() })) }));

vi.mock("../context/LiveStatusContext", () => ({
  useLiveStatus: () => ({
    health: { status: "ok", pending_tasks: 0 },
    worker: { active_tasks: 0, tasks_completed: 0, tasks_failed: 0 },
    wsStatus: "open" as const,
  }),
  useLiveEvents: (cb: (e: MessageEvent) => void) => {
    liveEventHandler = cb;
  },
}));

vi.mock("../hooks/usePolling", () => ({
  usePolling: () => ({ data: null, error: null, lastUpdated: null }),
}));

vi.mock("../api/orchestrator", () => ({
  orchestratorApi: {
    getHistory: vi.fn(),
    getSystemMetricsDaily: vi.fn(),
  },
}));

import { MonitorPage } from "../pages/MonitorPage";
import { computeWindow } from "../lib/virtualWindow";

const CONSOLE_H = 420;
const CONSOLE_OVERSCAN = 12;

// `requestAnimationFrame` é enfileirado aqui (não executado inline) para que
// `flushHandleRef.current = requestAnimationFrame(flushLines)` em
// MonitorPage.tsx complete a atribuição ANTES do callback rodar — do
// contrário `flushLines` zera a ref antes da atribuição escrever nela, e o
// componente para de agendar novos flushes após o 1º evento.
let rafQueue: FrameRequestCallback[] = [];

function flushRaf() {
  const queue = rafQueue;
  rafQueue = [];
  queue.forEach((cb) => cb(0));
}

/** Envia um evento LOG_UPDATE real do event bus (mesmo formato que o
 * WebSocket entrega em produção — ver `describeEvent` em MonitorPage.tsx),
 * e resolve o flush em rAF que MonitorPage agenda para ele. */
function sendLogLine(preview: string) {
  act(() => {
    liveEventHandler?.({ data: JSON.stringify({ type: "LOG_UPDATE", data: { exec_id: "e1", preview } }) } as MessageEvent);
  });
  act(() => {
    flushRaf();
  });
}

/** Lê a altura do espaçador inferior do console — ele é `(total - end) * rowH`
 * (ver `computeWindow`), então serve de prova indireta do `rowH` vigente sem
 * expor o estado interno do componente. Só é sensível a `rowH` enquanto
 * `total > end`, garantido aqui por empurrar dezenas de linhas num viewport
 * fixo de 420px. */
function readBottomPad(container: HTMLElement): number {
  const spacers = container.querySelectorAll('[aria-hidden="true"]');
  const bottomSpacer = spacers[spacers.length - 1];
  if (!bottomSpacer) throw new Error("espaçador inferior não encontrado — console sem linhas?");
  return Number((bottomSpacer as HTMLElement).style.height.replace("px", ""));
}

describe("MonitorPage — medição de rowH não oscila (achado nº 8)", () => {
  let rectHeights: number[];
  let rectCallCount: number;

  beforeEach(() => {
    liveEventHandler = null;
    rectCallCount = 0;
    // jsdom não implementa `Element.scrollTo` — MonitorPage chama no
    // useEffect de auto-scroll do console (linha 187), fora do escopo deste
    // teste.
    HTMLDivElement.prototype.scrollTo = vi.fn();
    // MonitorPage buferiza linhas e faz flush num `requestAnimationFrame`
    // (achado nº 32, Onda 5) — enfileirado em `rafQueue` e resolvido por
    // `flushRaf()` dentro de `sendLogLine`.
    rafQueue = [];
    let rafIdCounter = 0;
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      rafQueue.push(cb);
      return (rafIdCounter += 1);
    });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    // Alturas OSCILANTES de propósito: reproduz o cenário do handoff (linhas
    // curtas e longas alternadas com `white-space: pre-wrap`). Se o guard por
    // ref não existisse, cada valor novo reescreveria `rowH` e mudaria `start`
    // em `computeWindow` — o laço de realimentação descrito no item 8.
    rectHeights = [40, 19, 400, 19, 400, 19];
    vi.spyOn(HTMLDivElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLDivElement) {
      const h = rectHeights[Math.min(rectCallCount, rectHeights.length - 1)] ?? 19;
      rectCallCount += 1;
      return { x: 0, y: 0, width: 100, height: h, top: 0, left: 0, right: 100, bottom: h, toJSON: () => ({}) };
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("mede a primeira linha uma única vez e ignora alturas divergentes depois", () => {
    const { container } = render(
      <MemoryRouter>
        <MonitorPage />
      </MemoryRouter>,
    );

    expect(liveEventHandler).not.toBeNull();

    // Precisa de linhas suficientes para que total > end (ver readBottomPad).
    for (let i = 0; i < 60; i += 1) {
      sendLogLine(i % 2 === 0 ? "curta" : "linha de log bem mais longa que a anterior, para forcar quebra de pre-wrap");
    }

    // rowH estimado inicial é 19 (ROW_H_ESTIMATE); a 1ª medição real (40, o
    // primeiro valor da fila) deveria substituí-lo — e só ela. Se a medição
    // ficasse presa em 19 (não mediu) o valor abaixo divergiria.
    const rowHMedido = 40;
    const esperadoApos60 = computeWindow(0, rowHMedido, CONSOLE_H, 60, CONSOLE_OVERSCAN).bottomPad;
    expect(readBottomPad(container)).toBe(esperadoApos60);

    // Continua empurrando linhas — cada uma dispara o layout effect de novo
    // (dep `visibleLines.length`) e `getBoundingClientRect` seguirá
    // devolvendo alturas divergentes (19, 400, 19, 400...). Sem o guard por
    // ref, qualquer uma dessas leituras reescreveria `rowH` de novo.
    for (let i = 0; i < 20; i += 1) {
      sendLogLine(`linha extra ${i}`);
    }

    // Único fator que devia ter mudado é `total` (60 -> 80); `rowH` continua
    // travado nos mesmos 40px medidos na 1ª vez. Se o guard falhasse, `rowH`
    // teria virado 19 ou 400 (últimos valores da fila) e este valor exato
    // não bateria.
    const esperadoApos80 = computeWindow(0, rowHMedido, CONSOLE_H, 80, CONSOLE_OVERSCAN).bottomPad;
    expect(readBottomPad(container)).toBe(esperadoApos80);

    // Prova direta da medição única: o guard (`rowHMeasuredRef`) retorna
    // ANTES de chamar `getBoundingClientRect` assim que já mediu uma vez, então
    // o mock é acionado exatamente 1 vez em ~80 renders do console — não 80
    // vezes convergindo por acaso para o mesmo valor.
    expect(rectCallCount).toBe(1);
  });
});
