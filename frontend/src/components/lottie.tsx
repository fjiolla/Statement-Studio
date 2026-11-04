"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const Lottie = dynamic(() => import("lottie-react"), { ssr: false });
const cache = new Map<string, unknown>();

/**
 * Lottie used only for state moments (upload, scanning, success). Honours
 * prefers-reduced-motion by showing the first frame, and renders `fallback`
 * if the JSON can't be loaded.
 */
export function LottieAnim({
  name,
  loop = true,
  className,
  fallback = null,
  onComplete,
}: {
  name: "upload" | "scanning" | "success";
  loop?: boolean;
  className?: string;
  fallback?: React.ReactNode;
  onComplete?: () => void;
}) {
  const [data, setData] = useState<unknown>(cache.get(name) ?? null);
  const [failed, setFailed] = useState(false);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    if (cache.has(name)) return;
    let alive = true;
    fetch(`/lottie/${name}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        cache.set(name, j);
        if (alive) setData(j);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [name]);

  if (failed) return <>{fallback}</>;
  if (!data) return <div className={className} />;
  return (
    <Lottie
      animationData={data}
      loop={reduced ? false : loop}
      autoplay={!reduced}
      className={className}
      onComplete={onComplete}
      rendererSettings={{ preserveAspectRatio: "xMidYMid meet" }}
    />
  );
}
