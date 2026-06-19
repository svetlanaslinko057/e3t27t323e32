import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Navigation, ExternalLink, Loader2, MapPin } from 'lucide-react';

/**
 * Free, no-API-key interactive map (Leaflet + CARTO/OSM tiles), styled for LUMEN.
 * Shows a marker at the object location immediately. "Прокласти маршрут" detects the
 * user's geolocation and opens Google Maps directions (origin → object), BB-Cars style.
 *
 * Props: lat, lng (numbers), label (string), address (string)
 */
export default function AssetMap({ lat, lng, label, address }) {
  const elRef = useRef(null);
  const mapRef = useRef(null);
  const [geoState, setGeoState] = useState('idle'); // idle | locating | error
  const [geoMsg, setGeoMsg] = useState('');

  const hasCoords = Number.isFinite(Number(lat)) && Number.isFinite(Number(lng))
    && !(Number(lat) === 0 && Number(lng) === 0);

  useEffect(() => {
    if (!hasCoords || !elRef.current || mapRef.current) return;
    const map = L.map(elRef.current, {
      center: [Number(lat), Number(lng)],
      zoom: 14,
      scrollWheelZoom: false,
      zoomControl: true,
      attributionControl: true,
    });
    mapRef.current = map;

    // Clean light basemap (CARTO Positron) — free, no key, matches LUMEN aesthetic.
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      subdomains: 'abcd',
      attribution: '&copy; OpenStreetMap &copy; CARTO',
    }).addTo(map);

    const icon = L.divIcon({
      className: 'lumen-map-pin',
      html: `<span class="lumen-map-pin__dot"><span class="lumen-map-pin__pulse"></span></span>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    const marker = L.marker([Number(lat), Number(lng)], { icon }).addTo(map);
    if (label || address) {
      marker.bindPopup(
        `<b>${escapeHtml(label || '')}</b>${address ? `<br/><span style="color:#5b6b62">${escapeHtml(address)}</span>` : ''}`,
        { closeButton: false },
      );
    }
    // ensure correct sizing after layout settles
    setTimeout(() => map.invalidateSize(), 250);

    return () => { map.remove(); mapRef.current = null; };
  }, [hasCoords, lat, lng, label, address]);

  const destination = `${lat},${lng}`;
  const openMaps = `https://www.google.com/maps/search/?api=1&query=${destination}`;

  const buildRoute = () => {
    if (!navigator.geolocation) {
      // No geolocation API — let Google ask for the origin.
      window.open(`https://www.google.com/maps/dir/?api=1&destination=${destination}`, '_blank', 'noopener');
      return;
    }
    setGeoState('locating');
    setGeoMsg('');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        const url = `https://www.google.com/maps/dir/?api=1&origin=${latitude},${longitude}&destination=${destination}&travelmode=driving`;
        window.open(url, '_blank', 'noopener');
        setGeoState('idle');
      },
      () => {
        // Permission denied / unavailable — still open directions, Google asks origin.
        setGeoState('error');
        setGeoMsg('Не вдалося визначити ваше місцезнаходження — відкриваємо маршрут без точки старту.');
        window.open(`https://www.google.com/maps/dir/?api=1&destination=${destination}`, '_blank', 'noopener');
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
  };

  if (!hasCoords) {
    return (
      <div className="mt-4 flex items-center gap-2 rounded-xl border border-dashed border-border bg-muted/40 px-4 py-6 text-sm text-muted-foreground">
        <MapPin className="h-4 w-4" /> Точні координати об'єкта уточнюються.
        {address && <a href={openMaps} target="_blank" rel="noreferrer" className="ml-1 text-[#2E5D4F] hover:underline">Знайти на карті</a>}
      </div>
    );
  }

  return (
    <div className="mt-4">
      <div className="relative overflow-hidden rounded-2xl border border-border" data-testid="asset-map">
        <div ref={elRef} className="h-[300px] w-full" style={{ background: '#eef2ee' }} aria-label="Карта розташування об'єкта" />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={buildRoute}
          disabled={geoState === 'locating'}
          className="inline-flex items-center gap-2 rounded-xl bg-[#2E5D4F] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#24493e] disabled:opacity-70"
          data-testid="asset-map-route"
        >
          {geoState === 'locating'
            ? <><Loader2 className="h-4 w-4 animate-spin" /> Визначаємо місцезнаходження…</>
            : <><Navigation className="h-4 w-4" /> Прокласти маршрут</>}
        </button>
        <a
          href={openMaps}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-[#2E5D4F] hover:underline"
          data-testid="asset-map-open"
        >
          Відкрити в Google Maps <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>
      {geoMsg && <p className="mt-2 text-xs text-muted-foreground" data-testid="asset-map-geo-msg">{geoMsg}</p>}
    </div>
  );
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
