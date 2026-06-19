import { Redirect } from 'expo-router';
import { useAuth } from '@/auth';
import { Loading } from '@/ui';

// Entry gate: route to the cabinet if authed, otherwise to welcome.
export default function Index() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return <Redirect href={user ? '/(tabs)' : '/welcome'} />;
}
