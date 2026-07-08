import { useContext } from 'react';

import UserContext from '../contexts/UserContext';
import { useThemeContext } from '../contexts/ThemeContext';

// MUI
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

const Home = () => {
  const { user, logout } = useContext(UserContext);
  const { mode, toggleTheme } = useThemeContext();

  return (
    <Box sx={{ py: 6 }}>
      <Card elevation={0} sx={{ border: 1, borderColor: 'divider' }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h4">Template App</Typography>
            <Typography variant="body1" color="text.secondary">
              This is the Django + React template landing page. Replace it with your
              app's home screen.
            </Typography>

            {user && (
              <Typography variant="body2" color="text.secondary">
                Signed in as <strong>{user.username}</strong> ({user.email || 'no email'}).
              </Typography>
            )}

            <Stack direction="row" spacing={2}>
              <Button variant="outlined" onClick={toggleTheme}>
                Switch to {mode === 'light' ? 'dark' : 'light'} mode
              </Button>
              <Button variant="contained" color="primary" onClick={logout}>
                Log out
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};

export default Home;
