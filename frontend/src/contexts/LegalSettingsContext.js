/**
 * LegalSettingsContext — single fetch of /api/public/legal-settings, shared
 * by Footer (socials + legal links) and CookieBanner.
 *
 * Also exposes a lazy loader for full legal-document bodies so the modal
 * can render terms / privacy / cookies on demand.
 */
import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';

const Ctx = createContext({
  socials: [],
  legal: [],
  loading: true,
  reload: async () => {},
  fetchDocument: async () => null,
});

export function LegalSettingsProvider({ children }) {
  const [socials, setSocials] = useState([]);
  const [legal, setLegal] = useState([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get('/public/legal-settings');
      setSocials(Array.isArray(data?.socials) ? data.socials : []);
      setLegal(Array.isArray(data?.legal) ? data.legal : []);
    } catch {
      // Public endpoint failing is non-blocking for the rest of the site.
      setSocials([]);
      setLegal([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const fetchDocument = useCallback(async (kind) => {
    try {
      const data = await api.get(`/public/legal-document/${kind}`);
      return data;
    } catch {
      return null;
    }
  }, []);

  return (
    <Ctx.Provider value={{ socials, legal, loading, reload, fetchDocument }}>
      {children}
    </Ctx.Provider>
  );
}

export function useLegalSettings() {
  return useContext(Ctx);
}
