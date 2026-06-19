import { View, Text, Image } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { colors, spacing, font } from '@/theme';
import { PrimaryButton, GhostButton } from '@/ui';

export default function Welcome() {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.green }}>
      <View style={{ flex: 1, padding: spacing.lg, justifyContent: 'space-between' }}>
        <View style={{ marginTop: 48 }}>
          <Text style={{ color: '#fff', fontSize: 34, fontWeight: '900', letterSpacing: 1 }}>LUMEN</Text>
          <Text style={{ color: 'rgba(255,255,255,0.8)', fontSize: font.small, marginTop: 6, letterSpacing: 3, textTransform: 'uppercase' }}>
            Реальні активи · USD / USDT
          </Text>
        </View>

        <View>
          <Text style={{ color: '#fff', fontSize: 30, fontWeight: '800', lineHeight: 38 }}>
            Інвестуйте в реальні активи від $1,000
          </Text>
          <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: font.body, marginTop: 12, lineHeight: 22 }}>
            Купуйте частки в нерухомості та бізнес-активах, отримуйте дивіденди та продавайте частки на OTC-ринку.
          </Text>
        </View>

        <View style={{ gap: 12, marginBottom: 12 }}>
          <PrimaryButton title="Увійти" onPress={() => router.push('/auth')} />
          <View style={{ backgroundColor: 'rgba(255,255,255,0.12)', borderRadius: 14 }}>
            <GhostButton title="Демо-кабінет інвестора" onPress={() => router.push('/auth?demo=1')} />
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}
