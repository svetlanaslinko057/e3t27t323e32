import { useCallback, useState } from 'react';
import { View, TouchableOpacity } from 'react-native';
import { useFocusEffect, router } from 'expo-router';
import { api } from '@/api';
import { formatUSD, formatPercent } from '@/format';
import { colors, font, radius, spacing } from '@/theme';
import { Screen, H2, Muted, Body, Pill, Card, Empty } from '@/ui';

export default function Assets() {
  const [items, setItems] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/assets');
      const list = Array.isArray(r) ? r : (r?.assets || r?.items || []);
      setItems(list);
    } catch { setItems([]); }
    finally { setLoaded(true); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <Screen>
      <View style={{ marginTop: 8 }}>
        <Muted>Інвестиції</Muted>
        <H2>Активи</H2>
        <Muted style={{ marginTop: 4 }}>Реальні активи від $1,000 · USD / USDT</Muted>
      </View>
      {loaded && items.length === 0 && <Empty title="Немає доступних активів" />}
      {items.map((a: any, i: number) => (
        <TouchableOpacity key={a.id || i} activeOpacity={0.88} onPress={() => router.push(`/asset/${a.id}`)}>
          <Card style={{ padding: 0, overflow: 'hidden' }}>
            <View style={{ height: 120, backgroundColor: colors.green, padding: spacing.md, justifyContent: 'space-between' }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Pill label={a.category || a.type || 'Нерухомість'} bg="rgba(255,255,255,0.18)" />
                <Pill label={`${formatPercent(a.target_yield ?? a.yield ?? 0)} річних`} />
              </View>
            </View>
            <View style={{ padding: spacing.md }}>
              <Body style={{ fontWeight: '800' }}>{a.title || a.name || 'Актив'}</Body>
              <Muted>{a.location || a.city || ''}</Muted>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 }}>
                <View><Muted>Мінімум входу</Muted><Body style={{ fontWeight: '700' }}>{formatUSD(a.min_ticket ?? 0)}</Body></View>
                <View style={{ alignItems: 'flex-end' }}><Muted>Ціль раунду</Muted><Body style={{ fontWeight: '700' }}>{formatUSD(a.round_target ?? a.target_uah ?? 0)}</Body></View>
              </View>
            </View>
          </Card>
        </TouchableOpacity>
      ))}
    </Screen>
  );
}
