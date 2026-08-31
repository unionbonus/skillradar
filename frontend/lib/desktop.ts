export type SkillRadarDesktop = {
  desktop: true;
  version: string;
  openExternal: (url: string) => Promise<void>;
  openManual: () => Promise<void>;
  getPaths: () => Promise<{
    userData: string;
    db: string;
    clones: string;
    version: string;
    packaged: boolean;
  }>;
};

export function desktop(): SkillRadarDesktop | null {
  if (typeof window === 'undefined') return null;
  const api = (window as Window & { skillradar?: SkillRadarDesktop }).skillradar;
  return api && api.desktop ? api : null;
}
