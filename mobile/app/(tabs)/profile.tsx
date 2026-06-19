import { View, TouchableOpacity, Alert } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '@/auth';
import { Screen, H2, Muted, Body, Card } from '@/ui';
import { colors, font, spacing } from '@/theme';

function RowLink({ icon, label, onPress }: { icon: any; label: string; onPress: () => void }) {
  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.8}>
      <Card style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <Ionicons name={icon} size={20} color={colors.green} />
          <Body style={{ fontWeight: '600' }}>{label}</Body>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.muted} />
      </Card>
    </TouchableOpacity>
  );
}

export default function Profile() {
  const { user, logout } = useAuth();
  const doLogout = () => Alert.alert('Вихід', 'Вийти з акаунту?', [
    { text: 'Скасувати', style: 'cancel' },
    { text: 'Вийти', style: 'destructive', onPress: async () => { await logout(); router.replace('/welcome'); } },
  ]);

  return (
    <Screen>
      <View style={{ marginTop: 8, alignItems: 'center', gap: 8 }}>
        <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center' }}>
          <Body style={{ color: '#fff', fontSize: 26, fontWeight: '800' }}>{(user?.name || user?.email || 'L').slice(0, 1).toUpperCase()}</Body>
        </View>
        <H2>{user?.name || 'Інвестор'}</H2>
        <Muted>{user?.email}</Muted>
      </View>

      <View style={{ gap: 10, marginTop: 8 }}>
        <RowLink icon="document-text" label="Документи та сертифікати" onPress={() => Alert.alert('LUMEN', 'Доступно у наступній версії')} />
        <RowLink icon="shield-checkmark" label="Безпека та 2FA" onPress={() => Alert.alert('LUMEN', 'Доступно у наступній версії')} />
        <RowLink icon="gift" label="Реферальна програма" onPress={() => Alert.alert('LUMEN', 'Скоро')} />
        <RowLink icon="settings" label="Налаштування" onPress={() => Alert.alert('LUMEN', 'Доступно у наступній версії')} />
      </View>

      <TouchableOpacity onPress={doLogout} style={{ marginTop: 8 }}>
        <Card style={{ alignItems: 'center' }}>
          <Body style={{ color: colors.danger, fontWeight: '700' }}>Вийти</Body>
        </Card>
      </TouchableOpacity>
    </Screen>
  );
}
