import { useCallback, useState } from 'react';
import { View, Alert, TouchableOpacity } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { api } from '@/api';
import { formatUSD, formatPercent } from '@/format';
import { colors, font, spacing } from '@/theme';
import { Screen, H2, Muted, Body, Card, Pill, Empty } from '@/ui';

export default function Otc() {
  const [items, setItems] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const r = await api.get('/investor/otc/listings'); setItems(Array.isArray(r) ? r : (r?.listings || r?.items || [])); }
    catch { setItems([]); } finally { setLoaded(true); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const buy = (l: any) => {
    Alert.alert('Купівля частки', `Підтвердити купівлю за ${formatUSD(l.price_uah ?? l.total_uah ?? 0)}?`, [
      { text: 'Скасувати', style: 'cancel' },
      { text: 'Купити', onPress: async () => {
        setBusy(l.id);
        try { await api.post(`/investor/otc/listings/${l.id}/buy`, {}); Alert.alert('Готово', 'Угоду створено.'); await load(); }
        catch (e: any) { Alert.alert('Помилка', e?.message || 'Не вдалося'); }
        finally { setBusy(null); }
      } },
    ]);
  };

  return (
    <Screen>
      <View style={{ marginTop: 8 }}>
        <Muted>Ринок</Muted>
        <H2>OTC — вторинний ринок</H2>
        <Muted style={{ marginTop: 4 }}>Купуйте та продавайте частки 24/7</Muted>
      </View>
      {loaded && items.length === 0 && <Empty title="Немає активних лотів" />}
      {items.map((l: any, i: number) => (
        <Card key={l.id || i} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flex: 1, paddingRight: 8 }}>
            <Body style={{ fontWeight: '700' }}>{l.asset_title || l.title || 'Частка'}</Body>
            <Muted>{formatPercent(l.share_pct ?? l.units_pct ?? 0, 2)} частки · {formatPercent(l.yield ?? 0)} річних</Muted>
          </View>
          <View style={{ alignItems: 'flex-end', gap: 6 }}>
            <Body style={{ fontWeight: '800' }}>{formatUSD(l.price_uah ?? l.total_uah ?? 0)}</Body>
            <TouchableOpacity onPress={() => buy(l)} disabled={busy === l.id} style={{ backgroundColor: colors.green, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 6 }}>
              <Body style={{ color: '#fff', fontWeight: '700', fontSize: font.small }}>{busy === l.id ? '...' : 'Купити'}</Body>
            </TouchableOpacity>
          </View>
        </Card>
      ))}
    </Screen>
  );
}
