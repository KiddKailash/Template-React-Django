// Settings -> Notifications: where the next notification goes, push on/off for
// this device, and a test push. From LLMStockAnalysis's Settings page. The
// "where" answer comes from GET /api/sessions/ (the same choose_channel the
// server sends with), so it is passed in from the page, which also owns the
// device list.

import { useEffect, useState } from 'react';

import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Typography from '@mui/material/Typography';
import EmailRoundedIcon from '@mui/icons-material/EmailRounded';
import NotificationsActiveRoundedIcon from '@mui/icons-material/NotificationsActiveRounded';

import {
  PUSH_STATE,
  disablePush,
  enablePush,
  getPushState,
  sendTestNotification,
} from '../services/push';
import { pushDescription } from '../utils/pushCopy';

const deviceName = (session) =>
  `${session.device?.label ?? 'Unknown device'}${session.current ? ' (this device)' : ''}`;

/** One sentence: where the next notification goes, and why. */
export function NotificationDestination({ overview, loading }) {
  if (loading || !overview?.notifications) {
    return <Skeleton variant="rounded" height={40} />;
  }
  const { notifications, sessions } = overview;
  const receiving = sessions.filter((s) => notifications.devices.includes(s.id));
  const unlinked = notifications.unlinked_devices;

  let Icon = EmailRoundedIcon;
  let headline;
  let detail;
  if (notifications.channel === 'push') {
    Icon = NotificationsActiveRoundedIcon;
    const names = receiving.map(deviceName);
    if (unlinked) names.push(`${unlinked} other device${unlinked === 1 ? '' : 's'}`);
    headline = `Pushed to ${names.join(', ')}`;
    detail =
      'Devices with push on that have opened the app in the last 14 days. If none of them can be reached, it is emailed instead.';
  } else if (notifications.channel === 'email') {
    headline = `Emailed to ${notifications.email}`;
    detail = sessions.some((s) => s.notifications === 'idle')
      ? "Push is on for a device, but it hasn't opened the app in 14 days. Open the app there to get pushes again."
      : 'No device has push on. Turn it on below to get notifications here instead of by email.';
  } else {
    headline = 'Nowhere: no device or email to send to';
    detail = 'Turn on push for this device, or add an email address to your account.';
  }

  return (
    <Stack direction="row" spacing={1.25} alignItems="flex-start">
      <Icon
        fontSize="small"
        sx={{ mt: 0.25, color: notifications.channel ? 'primary.main' : 'warning.main' }}
      />
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" fontWeight={500}>
          Notifications go to: {headline}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {detail}
        </Typography>
      </Box>
    </Stack>
  );
}

export default function NotificationSettings({ overview, loading, onChange, showSnackbar }) {
  const [pushState, setPushState] = useState('loading');
  const [working, setWorking] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    let active = true;
    getPushState()
      .then((state) => active && setPushState(state))
      .catch(() => active && setPushState(PUSH_STATE.UNSUPPORTED));
    return () => {
      active = false;
    };
  }, []);

  const handleToggle = async (e) => {
    if (working) return;
    const wantOn = e.target.checked;
    setWorking(true);
    try {
      const next = wantOn ? await enablePush() : await disablePush();
      setPushState(next);
      if (wantOn && next === PUSH_STATE.DENIED) {
        showSnackbar('Notifications are blocked for this site.', 'warning');
      }
    } catch (err) {
      showSnackbar(err?.message || "Couldn't update push notifications.", 'error');
    } finally {
      setWorking(false);
      // Turning push on or off changes where notifications go.
      onChange?.();
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await sendTestNotification();
      const n = res.data.delivered;
      showSnackbar(`Test notification sent to ${n} device${n === 1 ? '' : 's'}.`, 'success');
    } catch (err) {
      const status = err.response?.status;
      showSnackbar(
        status === 429
          ? 'Too many test notifications. Try again later.'
          : status === 502
            ? 'No device received it. Turn push on for a device first.'
            : err.response?.data?.detail || "Couldn't send a test notification.",
        'error',
      );
    } finally {
      setTesting(false);
    }
  };

  const checked = pushState === PUSH_STATE.GRANTED_SUBSCRIBED;
  const disabled =
    working ||
    pushState === 'loading' ||
    pushState === PUSH_STATE.UNSUPPORTED ||
    pushState === PUSH_STATE.UNCONFIGURED ||
    pushState === PUSH_STATE.DENIED;
  const pushOnSomewhere = overview?.notifications?.channel === 'push';

  return (
    <Stack spacing={2}>
      <NotificationDestination overview={overview} loading={loading} />
      <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between">
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" fontWeight={500}>
            Push notifications on this device
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {pushState === 'loading' ? ' ' : pushDescription(pushState)}
          </Typography>
        </Box>
        {pushState === 'loading' ? (
          <CircularProgress size={20} />
        ) : (
          <Switch
            checked={checked}
            onChange={handleToggle}
            disabled={disabled}
            slotProps={{ input: { 'aria-label': 'Push notifications on this device' } }}
          />
        )}
      </Stack>
      <Box>
        <Button
          variant="outlined"
          size="small"
          onClick={handleTest}
          disabled={testing || !pushOnSomewhere}
        >
          Send a test notification
        </Button>
      </Box>
    </Stack>
  );
}
