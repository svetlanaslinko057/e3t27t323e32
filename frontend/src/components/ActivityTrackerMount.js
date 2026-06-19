import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import tracker, { trackPage } from '@/lib/activityTracker';
import { useAuth } from '@/App';

/**
 * Mounts the F2 site-activity tracker.
 *  • Initialises the beacon once (session_start, CTA capture, flush loop).
 *  • Fires page_view on every route change.
 *  • Stitches identity whenever the authenticated user resolves.
 */
export default function ActivityTrackerMount() {
  const location = useLocation();
  const auth = useAuth();
  const user = auth ? auth.user : null;

  // init once
  useEffect(() => { tracker.init(); }, []);

  // page_view on navigation
  useEffect(() => {
    trackPage(location.pathname + location.search);
  }, [location.pathname, location.search]);

  // identity stitching on auth resolve
  useEffect(() => {
    if (user && (user.user_id || user.id)) {
      tracker.setIdentity({
        user_id: user.user_id || user.id,
        manager_id: user.manager_id || user.owner_id || user.assigned_manager_id || null,
      });
    }
  }, [user]);

  return null;
}
