// /chat: today's conversation with the assistant (backend/chat/).
//
// Each turn streams (services/chat.js): the page shows what the assistant is
// doing while it works, and a turn that takes minutes still arrives. The
// thread is the server's: on `done` the optimistic question is replaced by
// the saved messages.

import { useContext, useEffect, useRef, useState } from 'react';

import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import SendRoundedIcon from '@mui/icons-material/SendRounded';

import { SnackbarContext } from '../contexts/SnackbarContext';
import { fetchTodayThread, sendChatTurn } from '../services/chat';
import { describeProgress } from '../utils/chatProgress';

const MAX_CHARS = 4000; // backend/chat/views.py MAX_MESSAGE_CHARS

function Bubble({ message }) {
  const mine = message.role === 'user';
  return (
    <Box sx={{ display: 'flex', justifyContent: mine ? 'flex-end' : 'flex-start' }}>
      <Paper
        elevation={0}
        sx={{
          px: 1.75,
          py: 1,
          maxWidth: '85%',
          bgcolor: mine ? 'action.selected' : 'transparent',
          border: mine ? 0 : 1,
          borderColor: 'divider',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          opacity: message.pending ? 0.7 : 1,
        }}
      >
        <Typography variant="body2">{message.content}</Typography>
      </Paper>
    </Box>
  );
}

export default function Chat() {
  const { showSnackbar } = useContext(SnackbarContext);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState('');
  const [progress, setProgress] = useState(null); // null = idle
  const [error, setError] = useState('');
  const endRef = useRef(null);

  useEffect(() => {
    let active = true;
    fetchTodayThread()
      .then((res) => active && setMessages(res.data.messages))
      .catch(() => active && setError("Couldn't load today's conversation."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages, progress]);

  const busy = progress !== null;

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setError('');
    setDraft('');
    const pending = { id: `pending-${Date.now()}`, role: 'user', content: text, pending: true };
    setMessages((prev) => [...prev, pending]);
    setProgress('Thinking…');
    try {
      const result = await sendChatTurn({
        message: text,
        onEvent: (frame) => setProgress(describeProgress(frame)),
      });
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== pending.id),
        result.user_message,
        result.assistant_message,
      ]);
      if (result.cost_capped) showSnackbar('Monthly LLM spending cap reached.', 'warning');
    } catch (err) {
      // A turn that started server-side is saved there even if this tab lost
      // it; reload the thread rather than offering to send it again.
      if (err.streamStarted) {
        fetchTodayThread()
          .then((res) => setMessages(res.data.messages))
          .catch(() => {});
      } else {
        setMessages((prev) => prev.filter((m) => m.id !== pending.id));
        setDraft(text);
      }
      setError(err.response?.data?.detail || err.message || 'The assistant failed to answer.');
    } finally {
      setProgress(null);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <Stack sx={{ py: 3, maxWidth: 820, mx: 'auto', width: '100%', flexGrow: 1 }} spacing={2}>
      <Typography variant="h4" component="h1">
        Chat
      </Typography>

      <Stack spacing={1.5} sx={{ flexGrow: 1 }} role="log" aria-live="polite" aria-label="Conversation">
        {loading && <CircularProgress size={24} sx={{ alignSelf: 'center' }} />}
        {!loading && messages.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            Ask anything. The assistant can use the app&apos;s tools; long answers stream in as it
            works.
          </Typography>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} message={m} />
        ))}
        {busy && (
          <Stack direction="row" spacing={1} alignItems="center" sx={{ color: 'text.secondary' }}>
            <CircularProgress size={14} color="inherit" />
            <Typography variant="caption">{progress}</Typography>
          </Stack>
        )}
        <div ref={endRef} />
      </Stack>

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Stack direction="row" spacing={1} alignItems="flex-end">
        <TextField
          fullWidth
          multiline
          maxRows={8}
          size="small"
          placeholder="Message the assistant"
          value={draft}
          onChange={(e) => setDraft(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={onKeyDown}
          disabled={loading}
          slotProps={{ htmlInput: { 'aria-label': 'Message' } }}
        />
        <Tooltip title="Send (Enter)">
          <span>
            <IconButton
              color="primary"
              onClick={send}
              disabled={busy || loading || !draft.trim()}
              aria-label="Send"
            >
              <SendRoundedIcon />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
    </Stack>
  );
}
