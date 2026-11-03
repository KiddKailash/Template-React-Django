// /settings: account, signed-in devices and appearance. Section layout after
// LLMStockAnalysis's Settings page; add a <Section> per feature your app has.

import { useCallback, useContext, useEffect, useState } from 'react';

import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import DarkModeRoundedIcon from '@mui/icons-material/DarkModeRounded';
import DevicesRoundedIcon from '@mui/icons-material/DevicesRounded';
import LightModeRoundedIcon from '@mui/icons-material/LightModeRounded';
import NotificationsRoundedIcon from '@mui/icons-material/NotificationsRounded';
import PersonRoundedIcon from '@mui/icons-material/PersonRounded';

import ChangePasswordForm from '../components/ChangePasswordForm';
import NotificationSettings from '../components/NotificationSettings';
import DeviceSessions from '../components/DeviceSessions';
import { SnackbarContext } from '../contexts/SnackbarContext';
import { useThemeContext } from '../contexts/ThemeContext';
import UserContext from '../contexts/UserContext';
import {
  changePassword,
  fetchSessions,
  revokeOtherSessions,
  revokeSession,
} from '../services/api';

export function Section({ icon, title, description, children }) {
  return (
    <Box component="section" aria-label={title} sx={{ py: 3 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
        {icon}
        <Typography variant="h6" component="h2">
          {title}
        </Typography>
      </Stack>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {description}
        </Typography>
      )}
      {children}
    </Box>
  );
}

const iconSx = { color: 'primary.main' };

export default function Settings() {
  const { user } = useContext(UserContext);
  const { showSnackbar } = useContext(SnackbarContext);
  const { mode, toggleTheme } = useThemeContext();
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);

  // Re-read after any change (revoke, password change).
  const loadSessions = useCallback(
    () =>
      fetchSessions()
        .then((res) => setOverview(res.data))
        .catch(() => showSnackbar('Could not load signed-in devices.', 'error'))
        .finally(() => setLoading(false)),
    [showSnackbar],
  );

  useEffect(() => {
    let active = true;
    fetchSessions()
      .then((res) => active && setOverview(res.data))
      .catch(() => active && showSnackbar('Could not load signed-in devices.', 'error'))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [showSnackbar]);

  const handleRevoke = async (session) => {
    await revokeSession(session.id);
    showSnackbar(`Signed out ${session.device?.label ?? 'the device'}.`, 'success');
    await loadSessions();
  };

  const handleRevokeOthers = async () => {
    const res = await revokeOtherSessions();
    const n = res.data.revoked;
    showSnackbar(`Signed out ${n} other device${n === 1 ? '' : 's'}.`, 'success');
    await loadSessions();
  };

  const handleChangePassword = async (current, next) => {
    const res = await changePassword(current, next);
    const n = res.data.signed_out;
    showSnackbar(
      n
        ? `Password changed. Signed out ${n} other device${n === 1 ? '' : 's'}.`
        : 'Password changed.',
      'success',
    );
    await loadSessions();
  };

  return (
    <Box sx={{ py: 3, maxWidth: 720 }} aria-label="Settings">
      <Typography variant="h4" component="h1">
        Settings
      </Typography>

      <Section
        icon={<PersonRoundedIcon fontSize="small" sx={iconSx} />}
        title="Account"
        description={
          user ? `Signed in as ${user.username}${user.email ? ` (${user.email})` : ''}.` : null
        }
      >
        <ChangePasswordForm onSubmit={handleChangePassword} />
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Changing your password signs out every other device.
        </Typography>
      </Section>
      <Divider />

      <Section
        icon={<NotificationsRoundedIcon fontSize="small" sx={iconSx} />}
        title="Notifications"
      >
        <NotificationSettings
          overview={overview}
          loading={loading}
          onChange={loadSessions}
          showSnackbar={showSnackbar}
        />
      </Section>
      <Divider />

      <Section
        icon={<DevicesRoundedIcon fontSize="small" sx={iconSx} />}
        title="Devices"
        description="Everywhere you are signed in."
      >
        <DeviceSessions
          overview={overview}
          loading={loading}
          onRevoke={handleRevoke}
          onRevokeOthers={handleRevokeOthers}
        />
      </Section>
      <Divider />

      <Section
        icon={
          mode === 'light' ? (
            <LightModeRoundedIcon fontSize="small" sx={iconSx} />
          ) : (
            <DarkModeRoundedIcon fontSize="small" sx={iconSx} />
          )
        }
        title="Appearance"
      >
        <Button variant="outlined" onClick={toggleTheme}>
          Switch to {mode === 'light' ? 'dark' : 'light'} mode
        </Button>
      </Section>
    </Box>
  );
}
