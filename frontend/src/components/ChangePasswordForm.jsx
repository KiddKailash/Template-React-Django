// Settings -> Account: change the password. The server keeps this device signed
// in and signs every other device out (backend/accounts/views.py).

import { useState } from 'react';

import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';

/** First error message for a field in a DRF 400 body, if any. */
const fieldError = (errors, name) => {
  const value = errors?.[name];
  return Array.isArray(value) ? value[0] : value;
};

export default function ChangePasswordForm({ onSubmit }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);

  const mismatch = confirm.length > 0 && next !== confirm;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setErrors({});
    try {
      await onSubmit(current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (error) {
      setErrors(error.response?.data ?? { detail: 'Could not change the password.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack component="form" spacing={2} onSubmit={handleSubmit} sx={{ maxWidth: 400 }}>
      <TextField
        label="Current password"
        type="password"
        size="small"
        autoComplete="current-password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        error={Boolean(fieldError(errors, 'current_password'))}
        helperText={fieldError(errors, 'current_password')}
        required
      />
      <TextField
        label="New password"
        type="password"
        size="small"
        autoComplete="new-password"
        value={next}
        onChange={(e) => setNext(e.target.value)}
        error={Boolean(fieldError(errors, 'new_password'))}
        helperText={fieldError(errors, 'new_password')}
        required
      />
      <TextField
        label="Confirm new password"
        type="password"
        size="small"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        error={mismatch}
        helperText={mismatch ? 'Passwords do not match.' : fieldError(errors, 'detail')}
        required
      />
      <Button
        type="submit"
        variant="contained"
        disabled={busy || !current || !next || !confirm || mismatch}
        sx={{ alignSelf: 'flex-start' }}
      >
        Change password
      </Button>
    </Stack>
  );
}
