export function splitScreenBounds(screen: {
  availWidth: number; availHeight: number; availLeft?: number; availTop?: number;
}) {
  const left = Math.round(screen.availLeft || 0);
  const top = Math.round(screen.availTop || 0);
  const width = Math.round(screen.availWidth);
  const height = Math.round(screen.availHeight);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width < 800 || height < 400) {
    throw new Error("Amplía la pantalla para abrir el portal y el asistente lado a lado.");
  }
  const half = Math.floor(width / 2);
  return {
    portal: { left, top, width: half, height },
    assistant: { left: left + half, top, width: width - half, height },
  };
}
