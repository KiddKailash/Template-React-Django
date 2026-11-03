// Settings -> Devices: every signed-in device, which of them notifications go
// to, and sign-out for the others. Presentational: the Settings page owns the
// overview (GET /api/sessions/) and the revoke calls. From LLMStockAnalysis.

import { useState } from 'react';

import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import LaptopRoundedIcon from '@mui/icons-material/LaptopRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import NotificationsActiveRoundedIcon from '@mui/icons-material/NotificationsActiveRounded';
import NotificationsPausedRoundedIcon from '@mui/icons-material/NotificationsPausedRounded';
import PhoneIphoneRoundedIcon from '@mui/icons-material/PhoneIphoneRounded';
import TabletMacRoundedIcon from '@mui/icons-material/TabletMacRounded';

import { formatDate, timeAgo } from '../utils/time';

const KIND_ICON = {
  mobile: PhoneIphoneRoundedIcon,
  tablet: TabletMacRoundedIcon,
  desktop: LaptopRoundedIcon,
};

function NotificationBadge({ state }) {
  if (state === 'receiving') {
    return (
      <Tooltip title="Notifications are pushed to this device" placement="left">
        <NotificationsActiveRoundedIcon fontSize="small" color="primary" />
      </Tooltip>
    );
  }
  if (state === 'idle') {
    return (
      <Tooltip
        title="Push is on, but this device hasn't opened the app in 14 days, so notifications are emailed instead"
        placement="left"
      >
        <NotificationsPausedRoundedIcon fontSize="small" color="primary" />
      </Tooltip>
    );
  }
  return null;
}

function SessionRow({ session, onRevoke, busy }) {
  const Icon = KIND_ICON[session.device?.kind] ?? LaptopRoundedIcon;
  const label = session.device?.label ?? 'Unknown device';
  const meta = [
    session.current ? 'Active now' : `Active ${timeAgo(session.last_seen_at)}`,
    `Signed in ${formatDate(session.created_at)}`,
    session.ip_address,
  ].filter(Boolean);

  return (
    <Stack
      direction="row"
      spacing={2}
      alignItems="center"
      justifyContent="space-between"
      sx={{ py: 1.25 }}
      role="listitem"
    >
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ minWidth: 0 }}>
        <Icon fontSize="small" sx={{ color: 'text.secondary', flexShrink: 0 }} />
        <Box sx={{ minWidth: 0 }}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2" fontWeight={500}>
              {label}
            </Typography>
            {session.current && <Chip size="small" label="This device" sx={{ height: 20 }} />}
          </Stack>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {meta.join(' · ')}
          </Typography>
        </Box>
      </Stack>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ flexShrink: 0 }}>
        <NotificationBadge state={session.notifications} />
        {!session.current && (
          <Tooltip title="Sign out this device" placement="left">
            <span>
              <IconButton
                size="small"
                disabled={busy}
                onClick={() => onRevoke(session)}
                aria-label={`Sign out ${label}`}
              >
                <LogoutRoundedIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        )}
      </Stack>
    </Stack>
  );
}

export default function DeviceSessions({ overview, loading, onRevoke, onRevokeOthers }) {
  const [busy, setBusy] = useState(false);

  const run = async (fn) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  if (loading || !overview) {
    return (
      <Stack spacing={1}>
        <Skeleton variant="rounded" height={44} />
        <Skeleton variant="rounded" height={44} />
      </Stack>
    );
  }

  const { sessions } = overview;
  const others = sessions.filter((s) => !s.current);

  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        Signing a device out ends its session immediately and stops its push notifications.
      </Typography>
      <Box role="list" aria-label="Signed-in devices" sx={{ mt: 0.5 }}>
        {sessions.map((session, i) => (
          <Box key={session.id}>
            {i > 0 && <Divider />}
            <SessionRow session={session} busy={busy} onRevoke={(s) => run(() => onRevoke(s))} />
          </Box>
        ))}
      </Box>
      {others.length > 0 && (
        <Button
          size="small"
          variant="outlined"
          color="error"
          disabled={busy}
          onClick={() => run(onRevokeOthers)}
          sx={{ mt: 1 }}
        >
          {others.length === 1
            ? 'Sign out the other device'
            : `Sign out all ${others.length} other devices`}
        </Button>
      )}
    </Box>
  );
}
