import { useCallback, useState } from 'react';
import { View } from 'react-native';
import { useFocusEffect, useLocalSearchParams, router } from 'expo-router';
import { api } from '@/api';
import { formatUSD, formatPercent } from '@/format';
import { colors, font, spacing } from '@/theme';
import { Screen, H2, Muted, Body, Card, Pill, PrimaryButton, Loading } from '@/ui';

export default function AssetDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [a, setA] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setA(await api.get(`/assets/${id}`)); } catch { setA(null); } finally { setLoading(false); }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (loading) return <Loading />;
  if (!a) return <Screen><Card><Body>Актив не знайдено.</Body></Card></Screen>;

  return (
    <Screen>
      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <View style={{ height: 150, backgroundColor: colors.green, padding: spacing.md, justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Pill label={a.category || a.type || 'Нерухомість'} bg="rgba(255,255,255,0.18)" />
            <Pill label={`${formatPercent(a.target_yield ?? a.yield ?? 0)} річних`} />
          </View>
        </View>
      </Card>
      <View>
        <H2>{a.title || a.name}</H2>
        <Muted>{a.location || a.city || ''}</Muted>
      </View>
      {!!a.description && <Card><Body style={{ lineHeight: 21 }}>{a.description}</Body></Card>}
      <View style={{ flexDirection: 'row', gap: spacing.sm }}>
        <Card style={{ flex: 1 }}><Muted>Дохідність</Muted><Body style={{ fontWeight: '800' }}>{formatPercent(a.target_yield ?? a.yield ?? 0)}</Body></Card>
        <Card style={{ flex: 1 }}><Muted>Мінімум</Muted><Body style={{ fontWeight: '800' }}>{formatUSD(a.min_ticket ?? 0)}</Body></Card>
      </View>
      <Card style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <View><Muted>Ціль раунду</Muted><Body style={{ fontWeight: '700' }}>{formatUSD(a.round_target ?? a.target_uah ?? 0)}</Body></View>
        <View style={{ alignItems: 'flex-end' }}><Muted>Термін</Muted><Body style={{ fontWeight: '700' }}>{a.term_months ? `${a.term_months} міс` : '—'}</Body></View>
      </Card>
      <PrimaryButton title={`Інвестувати · від ${formatUSD(a.min_ticket ?? 0)}`} onPress={() => router.push(`/invest/${a.id}`)} />
    </Screen>
  );
}
