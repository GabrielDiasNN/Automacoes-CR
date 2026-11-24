import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronLeft, ChevronRight, Copy, Download, Image as ImageIcon, Maximize2, X } from "lucide-react";
import { orchestratorApi, type PromovidaCard } from "../api/orchestrator";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { useOverlayDismiss } from "../hooks/useOverlayDismiss";
import { Button, EmptyState } from "./ui";
import styles from "./CardGallery.module.css";

interface LoadedCardState {
  blob: Blob | null;
  src: string | null;
  failed: boolean;
}

function triggerDownload(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    a.remove();
  }, 0);
}

interface CardImageProps {
  slug: string;
  card: PromovidaCard;
  onOpen: (state: LoadedCardState) => void;
}

function CardImageItem({ slug, card, onOpen }: CardImageProps) {
  const [state, setState] = useState<LoadedCardState>({ blob: null, src: null, failed: false });
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setState({ blob: null, src: null, failed: false });
    setCopied(false);

    orchestratorApi
      .getPromovidaCardBlob(slug, card.filename, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ blob, src: objectUrl, failed: false });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ blob: null, src: null, failed: true });
      });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
        copyTimerRef.current = null;
      }
    };
  }, [slug, card.filename]);

  const handleCopy = async () => {
    if (!state.blob || typeof ClipboardItem === "undefined" || !navigator.clipboard?.write) return;
    try {
      await navigator.clipboard.write([new ClipboardItem({ [state.blob.type || "image/png"]: state.blob })]);
      setCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => {
        copyTimerRef.current = null;
        setCopied(false);
      }, 1800);
    } catch {
      // ignora silenciosamente se o navegador bloquear clipboard sem foco/HTTPS
    }
  };

  return (
    <figure className={styles.card}>
      <div className={styles.head}>
        <div className={styles.titleGroup}>
          <strong className={styles.title}>{card.title}</strong>
          <span className={styles.file}>{card.filename}</span>
        </div>
        {state.src && (
          <div className={styles.actions}>
            <Button
              size="sm"
              variant="subtle"
              icon={copied ? <Check size={12} /> : <Copy size={12} />}
              onClick={() => void handleCopy()}
              title="Copiar imagem PNG"
              aria-label={`Copiar ${card.title}`}
            >
              {copied ? "Copiado" : "Copiar"}
            </Button>
            <Button
              size="sm"
              variant="subtle"
              icon={<Download size={12} />}
              onClick={() => state.src && triggerDownload(state.src, card.filename)}
              title="Baixar imagem PNG"
              aria-label={`Baixar ${card.title}`}
            >
              PNG
            </Button>
            <Button
              size="sm"
              variant="subtle"
              icon={<Maximize2 size={12} />}
              onClick={() => onOpen(state)}
              title="Ampliar card"
              aria-label={`Ampliar ${card.title}`}
            />
          </div>
        )}
      </div>
      <div className={styles.media}>
        {state.src ? (
          <button
            type="button"
            className={styles.mediaBtn}
            onClick={() => onOpen(state)}
            aria-label={`Ampliar imagem ${card.title}`}
          >
            <img src={state.src} alt={`Card operacional: ${card.title}`} className={styles.img} />
          </button>
        ) : state.failed ? (
          <span className={styles.placeholder}>Não foi possível carregar a imagem.</span>
        ) : (
          <span className={styles.placeholder}>Carregando card PNG…</span>
        )}
      </div>
      {card.caption && <figcaption className={styles.caption}>{card.caption}</figcaption>}
    </figure>
  );
}

function CardLightbox({
  slug,
  cards,
  activeIndex,
  initialSrc,
  initialBlob,
  onClose,
  onSelectIndex,
}: {
  slug: string;
  cards: PromovidaCard[];
  activeIndex: number;
  initialSrc: string | null;
  initialBlob: Blob | null;
  onClose: () => void;
  onSelectIndex: (idx: number) => void;
}) {
  const card = cards[activeIndex];
  const cardFilename = card?.filename;
  const [src, setSrc] = useState<string | null>(initialSrc);
  const [blob, setBlob] = useState<Blob | null>(initialBlob);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null!);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useFocusTrap(boxRef, Boolean(card), onClose);
  useOverlayDismiss(overlayRef, Boolean(card), onClose);

  useEffect(() => {
    if (!cardFilename) return;
    setFailed(false);
    setCopied(false);

    if (initialSrc && initialBlob) {
      setSrc(initialSrc);
      setBlob(initialBlob);
      return () => {
        if (copyTimerRef.current) {
          clearTimeout(copyTimerRef.current);
          copyTimerRef.current = null;
        }
      };
    }

    const controller = new AbortController();
    let objectUrl: string | null = null;
    setSrc(initialSrc);
    setBlob(initialBlob);

    orchestratorApi
      .getPromovidaCardBlob(slug, cardFilename, controller.signal)
      .then((b) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(b);
        setBlob(b);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setSrc(null);
          setBlob(null);
          setFailed(true);
        }
      });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
        copyTimerRef.current = null;
      }
    };
  }, [slug, cardFilename, initialSrc, initialBlob]);

  useEffect(() => {
    if (!card) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (e.key === "Escape") onClose();
      else if (cards.length > 1 && e.key === "ArrowLeft") onSelectIndex((activeIndex - 1 + cards.length) % cards.length);
      else if (cards.length > 1 && e.key === "ArrowRight") onSelectIndex((activeIndex + 1) % cards.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, activeIndex, cards.length, onClose, onSelectIndex]);

  if (!card) return null;

  const handleCopy = async () => {
    if (!blob || typeof ClipboardItem === "undefined" || !navigator.clipboard?.write) return;
    try {
      await navigator.clipboard.write([new ClipboardItem({ [blob.type || "image/png"]: blob })]);
      setCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => {
        copyTimerRef.current = null;
        setCopied(false);
      }, 1800);
    } catch {
      /* ignora */
    }
  };

  return createPortal(
    <div
      ref={overlayRef}
      className={`overlay-scrim ${styles.lightboxOverlay}`}
      role="dialog"
      aria-modal="true"
      aria-label={card.title}
    >
      <div ref={boxRef} className={styles.lightboxBox}>
        <div className={styles.lightboxHead}>
          <div className={styles.titleGroup}>
            <strong className={styles.title}>{card.title}</strong>
            <span className={styles.file}>
              {card.filename} · {activeIndex + 1} de {cards.length}
            </span>
          </div>
          <div className={styles.actions}>
            {src && (
              <>
                <Button
                  size="sm"
                  variant="subtle"
                  icon={copied ? <Check size={12} /> : <Copy size={12} />}
                  disabled={!blob}
                  onClick={() => void handleCopy()}
                >
                  {copied ? "Copiado" : "Copiar"}
                </Button>
                <Button
                  size="sm"
                  variant="subtle"
                  icon={<Download size={12} />}
                  onClick={() => triggerDownload(src, card.filename)}
                >
                  Baixar PNG
                </Button>
              </>
            )}
            <Button size="sm" variant="subtle" icon={<X size={14} />} onClick={onClose} aria-label="Fechar ampliação">
              Fechar
            </Button>
          </div>
        </div>
        <div className={styles.lightboxMedia}>
          {src ? (
            <img src={src} alt={`Card ampliado: ${card.title}`} className={styles.lightboxImg} />
          ) : failed ? (
            <span className={styles.placeholder}>Não foi possível carregar a imagem ampliada.</span>
          ) : (
            <span className={styles.placeholder}>Carregando imagem ampliada…</span>
          )}
        </div>
        <div className={styles.lightboxFoot}>
          <Button
            size="sm"
            variant="subtle"
            icon={<ChevronLeft size={14} />}
            disabled={cards.length <= 1}
            onClick={() => onSelectIndex((activeIndex - 1 + cards.length) % cards.length)}
          >
            Anterior
          </Button>
          <span className={styles.file}>Use ← / → para navegar ou Esc para fechar</span>
          <Button
            size="sm"
            variant="subtle"
            icon={<ChevronRight size={14} />}
            disabled={cards.length <= 1}
            onClick={() => onSelectIndex((activeIndex + 1) % cards.length)}
          >
            Próximo
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function CardGallery({ slug, cards }: { slug: string; cards: PromovidaCard[] }) {
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);
  const [initialSrc, setInitialSrc] = useState<string | null>(null);
  const [initialBlob, setInitialBlob] = useState<Blob | null>(null);

  const handleClose = useCallback(() => {
    setLightboxIdx(null);
    setInitialSrc(null);
    setInitialBlob(null);
  }, []);

  useEffect(() => {
    handleClose();
  }, [slug, handleClose]);

  useEffect(() => {
    if (lightboxIdx !== null && lightboxIdx >= cards.length) {
      handleClose();
    }
  }, [lightboxIdx, cards.length, handleClose]);

  if (cards.length === 0) {
    return (
      <EmptyState
        icon={<ImageIcon size={24} />}
        title="Nenhum card PNG disponível"
        hint="Cards visuais aparecem aqui quando a automação gera imagens PNG na última execução."
      />
    );
  }
  return (
    <>
      <div className={styles.grid}>
        {cards.map((card, idx) => (
          <CardImageItem
            key={`${slug}-${card.filename}`}
            slug={slug}
            card={card}
            onOpen={(state) => {
              setInitialSrc(state.src);
              setInitialBlob(state.blob);
              setLightboxIdx(idx);
            }}
          />
        ))}
      </div>
      {lightboxIdx !== null && lightboxIdx < cards.length && (
        <CardLightbox
          slug={slug}
          cards={cards}
          activeIndex={lightboxIdx}
          initialSrc={initialSrc}
          initialBlob={initialBlob}
          onClose={handleClose}
          onSelectIndex={(idx) => {
            setInitialSrc(null);
            setInitialBlob(null);
            setLightboxIdx(idx);
          }}
        />
      )}
    </>
  );
}
