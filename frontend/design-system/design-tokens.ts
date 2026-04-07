export const designTokens = {
  brand: {
    name: "OnePitch · 一眼项目",
    productIdentity: "把模糊输入压成可发送项目对象的品牌化系统",
  },
  color: {
    bgCanvas: "#020617",
    bgSurface1: "#0B1220",
    bgSurface2: "#0F172A",
    bgSurface3: "#111827",
    bgSurface4: "#172033",
    bgSurface5: "#1B2230",
    textPrimary: "#F8FAFC",
    textSecondary: "#CBD5E1",
    textTertiary: "#94A3B8",
    textMuted: "#64748B",
    accent: "#2563EB",
    accentHover: "#3B82F6",
    accentSoft: "rgba(37,99,235,0.16)",
    borderSubtle: "rgba(255,255,255,0.08)",
    borderStrong: "rgba(255,255,255,0.14)",
  },
  density: {
    display: {
      canvas: "bgCanvas",
      surfacePrimary: "bgSurface1",
      surfaceSecondary: "bgSurface2",
    },
    browse: {
      canvas: "bgSurface3",
      surfacePrimary: "bgSurface4",
      surfaceSecondary: "bgSurface5",
    },
    work: {
      canvas: "bgSurface4",
      surfacePrimary: "bgSurface5",
      surfaceSecondary: "#222B3B",
    },
  },
  type: {
    families: {
      sans: ["Inter", "SF Pro Display", "system-ui", "sans-serif"],
      mono: ["Geist Mono", "SFMono-Regular", "monospace"],
    },
    weights: {
      regular: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
    sizes: {
      h1: "48px",
      h2: "36px",
      h3: "28px",
      body: "16px",
      caption: "13px",
    },
    lineHeights: {
      headline: 1.08,
      title: 1.15,
      body: 1.65,
      compact: 1.45,
    },
  },
  radius: {
    input: "16px",
    panel: "18px",
    card: "20px",
  },
  shadow: {
    soft: "0 8px 32px rgba(2, 6, 23, 0.28)",
    medium: "0 12px 40px rgba(2, 6, 23, 0.36)",
  },
  border: {
    width: "1px",
    subtle: "1px solid rgba(255,255,255,0.08)",
  },
  layout: {
    contentMaxWidth: "1240px",
    textMeasure: "44rem",
    sectionY: "96px",
    blockY: "48px",
    gutter: "24px",
    gridGap: "28px",
  },
  motion: {
    fast: "160ms",
    base: "240ms",
    reveal: "420ms",
    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
  },
} as const;

export type OnePitchDesignTokens = typeof designTokens;
