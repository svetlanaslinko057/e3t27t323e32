import { useEffect, useState } from 'react';
import { View, Text, TextInput, StyleSheet } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useAuth } from '@/auth';
import { Screen, H1, Muted, Card, PrimaryButton, GhostButton } from '@/ui';
import { colors, font, radius, spacing } from '@/theme';

export default function AuthScreen() {
  const { demo } = useLocalSearchParams<{ demo?: string }>();
  const { login, demoInvestor, user } = useAuth();
  const [email, setEmail] = useState('client@atlas.dev');
  const [password, setPassword] = useState('client123');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { if (user) router.replace('/(tabs)'); }, [user]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setErr(null);
    try { await fn(); router.replace('/(tabs)'); }
    catch (e: any) { setErr(e?.message || 'Не вдалося увійти'); }
    finally { setBusy(false); }
  };

  useEffect(() => { if (demo === '1') run(() => demoInvestor()); /* eslint-disable-next-line */ }, [demo]);

  return (
    <Screen>
      <View style={{ marginTop: 24 }}>
        <Text style={{ color: colors.green, fontWeight: '900', fontSize: 24, letterSpacing: 1 }}>LUMEN</Text>
        <H1 style={{ marginTop: 16 }}>Вхід до кабінету</H1>
        <Muted style={{ marginTop: 6 }}>Інвестуйте та керуйте портфелем у USD / USDT.</Muted>
      </View>

      <Card style={{ gap: 12 }}>
        <View>
          <Muted>Email</Muted>
          <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" style={styles.input} placeholder="you@email.com" placeholderTextColor={colors.muted} />
        </View>
        <View>
          <Muted>Пароль</Muted>
          <TextInput value={password} onChangeText={setPassword} secureTextEntry style={styles.input} placeholder="••••••••" placeholderTextColor={colors.muted} />
        </View>
        {!!err && <Text style={{ color: colors.danger, fontSize: font.small }}>{err}</Text>}
        <PrimaryButton title="Увійти" loading={busy} onPress={() => run(() => login(email, password))} />
        <GhostButton title="Демо-кабінет інвестора" onPress={() => run(() => demoInvestor())} />
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  input: { marginTop: 6, height: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, backgroundColor: colors.cream, fontSize: font.body, color: colors.ink },
});
