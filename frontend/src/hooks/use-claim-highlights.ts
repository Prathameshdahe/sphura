import { useCallback, useEffect, useRef, useState, type PointerEvent, type RefObject } from "react";
import type { Verification } from "@/lib/feature-types";
import { claimAtPoint, mapClaims, revealClaim, setClaimHighlights, type ClaimRange } from "@/lib/verification";

export interface HoveredClaim {
  claim: ClaimRange;
  x: number;
  y: number;
}

/**
 * Underline an answer's claims by verdict while `enabled`, expose the claim under the pointer
 * (tooltip) and `locate(i)` to scroll to one. `version` should change whenever the rendered text may.
 */
export function useClaimHighlights(
  rootRef: RefObject<HTMLElement | null>,
  key: string,
  verification: Verification | null,
  enabled: boolean,
  version: unknown,
) {
  const claims = useRef<ClaimRange[]>([]);
  const [mapped, setMapped] = useState<{ count: number; total: number } | null>(null);
  const [hovered, setHovered] = useState<HoveredClaim | null>(null);

  const compute = useCallback((): ClaimRange[] => {
    const root = rootRef.current;
    if (!root || !verification) return [];
    return mapClaims(root, verification.sentences);
  }, [rootRef, verification]);

  useEffect(() => {
    if (!enabled || !verification) {
      claims.current = [];
      return;
    }
    // After the markdown commit: the answer's text nodes exist now.
    const list = compute();
    claims.current = list;
    setClaimHighlights(key, list);
    const t = setTimeout(() => setMapped({ count: list.length, total: verification.sentences.length }), 0);
    return () => {
      clearTimeout(t);
      setClaimHighlights(key, null);
      claims.current = [];
      setHovered(null);
    };
  }, [enabled, verification, key, compute, version]);

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      if (!enabled || e.pointerType === "touch" || claims.current.length === 0) return;
      const hit = claimAtPoint(claims.current, e.clientX, e.clientY);
      setHovered((prev) => {
        if (!hit) return prev ? null : prev;
        if (prev && prev.claim === hit) return prev;
        return { claim: hit, x: e.clientX, y: e.clientY };
      });
    },
    [enabled],
  );

  const onPointerLeave = useCallback(() => setHovered(null), []);

  const locate = useCallback(
    (index: number): boolean => {
      const list = claims.current.length ? claims.current : compute();
      const hit = list.find((c) => c.index === index);
      if (!hit) return false;
      revealClaim(hit.range);
      return true;
    },
    [compute],
  );

  return { hovered, onPointerMove, onPointerLeave, locate, mapped: enabled ? mapped : null };
}
