import { useCallback, useState } from 'react';
import { View } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { api } from '@/api';
import { formatUSD } from '@/format';
import { colors, font, spacing } from '@/theme';
import { Screen, H2, Muted, Body, Card, Empty } from '@/ui';

export default function Income() {
  const [income, setIncome] = useState<any>(null);
  const [payouts, setPayouts] = useState<any[]>([]);

  const load = useCallback(async () => {
    try { setIncome(await api.get('/investor/income')); } catch { setIncome(null); }
    try { const r = await api.get('/investor/income/payouts?limit=50'); setPayouts(Array.isArray(r) ? r : (r?.payouts || r?.items || [])); } catch { setPayouts([]); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const total = income?.total_paid_uah ?? income?.summary?.total_paid_uah ?? 0;

  return (
    <Screen>
      <View style={{ marginTop: 8 }}>
        <Muted>Дохід</Muted>
        <H2>Дивіденди та виплати</H2>
      </View>
      <Card>
        <Muted>Виплачено за весь час</Muted>
        <Body style={{ fontSize: 30, fontWeight: '900', color: colors.green, marginTop: 2 }}>{formatUSD(total)}</Body>
      </Card>
      <H2 style={{ fontSize: font.h3 }}>Історія</H2>
      {payouts.length === 0 && <Empty title="Виплат ще немає" subtitle="Дивіденди з'являться після першої інвестиції." />}
      {payouts.map((p: any, i: number) => (
        <Card key={p.id || i} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
            <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: colors.greenSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="arrow-up" size={16} color={colors.green} />
            </View>
            <View style={{ flex: 1 }}>
              <Body style={{ fontWeight: '700' }}>{p.asset_title || p.title || 'Виплата'}</Body>
              <Muted>{p.date || p.paid_at || p.created_at || ''}</Muted>
            </View>
          </View>
          <Body style={{ fontWeight: '800', color: colors.green }}>+{formatUSD(p.amount_uah ?? p.amount ?? 0)}</Body>
        </Card>
      ))}
    </Screen>
  );
}
