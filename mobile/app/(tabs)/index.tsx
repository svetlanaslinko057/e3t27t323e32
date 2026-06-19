import { useCallback, useState } from 'react';
import { View, RefreshControl, ScrollView, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, router } from 'expo-router';
import { api } from '@/api';
import { formatUSD, formatPercent } from '@/format';
import { colors, spacing, font, radius } from '@/theme';
import { Card, H2, Muted, Body, Pill, Empty } from '@/ui';
import { useAuth } from '@/auth';

export default function Home() {
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { const r = await api.get('/investor/portfolio'); setData(r); } catch { setData(null); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const s = data?.summary || {};
  const investments = data?.investments || [];
  const upcoming = data?.upcoming_payouts || [];

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.cream }} edges={['top']}>
      <ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: 40 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.green} />}>
        <View>
          <Muted>Огляд</Muted>
          <H2>Вітаємо, {user?.name || 'інвесторе'}</H2>
        </View>

        <Card style={{ backgroundColor: colors.green }}>
          <Muted style={{ color: 'rgba(255,255,255,0.75)' }}>Загальний портфель</Muted>
          <Body style={{ color: '#fff', fontSize: 32, fontWeight: '900', marginTop: 2 }}>{formatUSD(s.total_invested_uah ?? s.total_value_uah ?? 0)}</Body>
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 6, alignItems: 'center' }}>
            <Pill label={`${formatPercent(s.avg_yield ?? s.weighted_yield ?? 0)} річних`} />
          </View>
        </Card>

        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <Card style={{ flex: 1 }}><Muted>Активних</Muted><Body style={{ fontWeight: '800', fontSize: font.h3 }}>{investments.length}</Body></Card>
          <Card style={{ flex: 1 }}><Muted>Виплачено</Muted><Body style={{ fontWeight: '800', fontSize: font.h3, color: colors.green }}>{formatUSD(s.total_paid_uah ?? 0)}</Body></Card>
        </View>

        <H2 style={{ fontSize: font.h3, marginTop: 4 }}>Мої інвестиції</H2>
        {investments.length === 0 && <Empty title="Ще немає інвестицій" subtitle="Оберіть актив у розділі «Активи» та оформіть першу позицію." />}
        {investments.map((inv: any, i: number) => (
          <TouchableOpacity key={inv.id || i} activeOpacity={0.85} onPress={() => inv.asset_id && router.push(`/asset/${inv.asset_id}`)}>
            <Card style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <View style={{ flex: 1, paddingRight: 8 }}>
                <Body style={{ fontWeight: '700' }}>{inv.asset_title || inv.title || 'Актив'}</Body>
                <Muted style={{ color: colors.green }}>{formatPercent(inv.yield ?? inv.target_yield ?? 0)} річних</Muted>
              </View>
              <Body style={{ fontWeight: '800' }}>{formatUSD(inv.amount_uah ?? inv.invested_uah ?? 0)}</Body>
            </Card>
          </TouchableOpacity>
        ))}

        {upcoming.length > 0 && (
          <>
            <H2 style={{ fontSize: font.h3, marginTop: 4 }}>Найближчі виплати</H2>
            {upcoming.map((p: any, i: number) => (
              <Card key={i} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Muted>{p.asset_title || 'Виплата'}</Muted>
                <Body style={{ fontWeight: '700', color: colors.green }}>{formatUSD(p.amount_uah ?? 0)}</Body>
              </Card>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}
