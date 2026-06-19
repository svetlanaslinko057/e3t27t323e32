/**
 * Shared mobile UI primitives — brand-consistent building blocks.
 */
import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet, ScrollView, ViewStyle, TextStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, radius, spacing, font } from './theme';

export function Screen({ children, scroll = true, style }: { children: React.ReactNode; scroll?: boolean; style?: ViewStyle }) {
  const inner = <View style={[{ padding: spacing.md, gap: spacing.md }, style]}>{children}</View>;
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.cream }} edges={['top']}>
      {scroll ? <ScrollView contentContainerStyle={{ paddingBottom: 40 }} showsVerticalScrollIndicator={false}>{inner}</ScrollView> : inner}
    </SafeAreaView>
  );
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function H1({ children, style }: { children: React.ReactNode; style?: TextStyle }) {
  return <Text style={[{ fontSize: font.h1, fontWeight: '800', color: colors.ink, letterSpacing: -0.5 }, style]}>{children}</Text>;
}
export function H2({ children, style }: { children: React.ReactNode; style?: TextStyle }) {
  return <Text style={[{ fontSize: font.h2, fontWeight: '700', color: colors.ink }, style]}>{children}</Text>;
}
export function Muted({ children, style }: { children: React.ReactNode; style?: TextStyle }) {
  return <Text style={[{ fontSize: font.small, color: colors.muted }, style]}>{children}</Text>;
}
export function Body({ children, style }: { children: React.ReactNode; style?: TextStyle }) {
  return <Text style={[{ fontSize: font.body, color: colors.ink }, style]}>{children}</Text>;
}

export function Pill({ label, bg = colors.gold, color = '#fff' }: { label: string; bg?: string; color?: string }) {
  return (
    <View style={{ backgroundColor: bg, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3, alignSelf: 'flex-start' }}>
      <Text style={{ color, fontSize: font.tiny, fontWeight: '700' }}>{label}</Text>
    </View>
  );
}

export function PrimaryButton({ title, onPress, disabled, loading }: { title: string; onPress: () => void; disabled?: boolean; loading?: boolean }) {
  return (
    <TouchableOpacity activeOpacity={0.85} disabled={disabled || loading} onPress={onPress} style={[styles.btn, { backgroundColor: colors.green, opacity: disabled ? 0.5 : 1 }]}>
      {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>{title}</Text>}
    </TouchableOpacity>
  );
}
export function GhostButton({ title, onPress }: { title: string; onPress: () => void }) {
  return (
    <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={[styles.btn, { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.green }]}>
      <Text style={[styles.btnText, { color: colors.green }]}>{title}</Text>
    </TouchableOpacity>
  );
}

export function StatBox({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <Card style={{ flex: 1 }}>
      <Muted>{label}</Muted>
      <Text style={{ fontSize: font.h3, fontWeight: '800', color: accent ? colors.green : colors.ink, marginTop: 2 }}>{value}</Text>
    </Card>
  );
}

export function Loading() {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.cream, alignItems: 'center', justifyContent: 'center' }}>
      <ActivityIndicator color={colors.green} size="large" />
    </SafeAreaView>
  );
}

export function Empty({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <Card style={{ alignItems: 'center', paddingVertical: 28 }}>
      <Body style={{ fontWeight: '700' }}>{title}</Body>
      {!!subtitle && <Muted style={{ marginTop: 4, textAlign: 'center' }}>{subtitle}</Muted>}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  btn: { height: 50, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.lg },
  btnText: { color: '#fff', fontSize: font.body, fontWeight: '700' },
});
