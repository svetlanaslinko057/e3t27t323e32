import { useCallback, useState } from 'react';
import { View, TextInput, StyleSheet, Alert, TouchableOpacity } from 'react-native';
import { useFocusEffect, useLocalSearchParams, router } from 'expo-router';
import { api } from '@/api';
import { UAH_PER_USD, formatUSD, usd, usdFromUah } from '@/format';
import { colors, font, radius, spacing } from '@/theme';
import { Screen, H2, Muted, Body, Card, PrimaryButton } from '@/ui';

export default function Invest() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [a, setA] = useState<any>(null);
  const [amount, setAmount] = useState('1000');
  const [ccy, setCcy] = useState<'USDT' | 'USD'>('USDT');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => { try { setA(await api.get(`/assets/${id}`)); } catch { setA(null); } }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const minUsd = usdFromUah(a?.min_ticket ?? 0);
  const amt = Number(amount) || 0;

  const submit = async () => {
    if (amt < minUsd) { Alert.alert('Сума замала', `Мінімум — ${usd(minUsd)}`); return; }
    setBusy(true);
    try {
      // amounts stored in UAH base on backend; convert USD input -> base.
      await api.post('/investor/intent', { asset_id: id, amount_uah: Math.round(amt * UAH_PER_USD), currency: ccy });
      Alert.alert('Готово', 'Заявку на інвестицію створено. Продовжіть оформлення у кабінеті.', [
        { text: 'OK', onPress: () => router.replace('/(tabs)') },
      ]);
    } catch (e: any) {
      Alert.alert('Помилка', e?.message || 'Не вдалося створити заявку');
    } finally { setBusy(false); }
  };

  return (
    <Screen>
      <View style={{ marginTop: 4 }}>
        <Muted>{a?.title || 'Актив'}</Muted>
        <H2>Сума інвестиції</H2>
      </View>
      <Card>
        <Muted>Сума ({ccy})</Muted>
        <TextInput value={amount} onChangeText={setAmount} keyboardType="numeric" style={styles.amount} />
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
          {(['USDT', 'USD'] as const).map((c) => (
            <TouchableOpacity key={c} activeOpacity={0.85} onPress={() => setCcy(c)} style={{ flex: 1, paddingVertical: 9, borderRadius: radius.sm, alignItems: 'center', backgroundColor: ccy === c ? colors.green : colors.surface }}>
              <Body style={{ fontWeight: '700', color: ccy === c ? '#fff' : colors.ink }}>{c}</Body>
            </TouchableOpacity>
          ))}
        </View>
      </Card>
      <Card style={{ gap: 8 }}>
        <Row label="Мінімум входу" value={usd(minUsd)} />
        <Row label="Сума інвестиції" value={usd(amt)} />
        <Row label="Комісія платформи" value={usd(0)} />
      </Card>
      <PrimaryButton title="Підтвердити інвестицію" loading={busy} onPress={submit} />
      <Muted style={{ textAlign: 'center' }}>Цифровий сертифікат власності після оплати</Muted>
    </Screen>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
      <Muted>{label}</Muted>
      <Body style={{ fontWeight: '700' }}>{value}</Body>
    </View>
  );
}

const styles = StyleSheet.create({
  amount: { fontSize: 30, fontWeight: '900', color: colors.ink, paddingVertical: 4 },
});
