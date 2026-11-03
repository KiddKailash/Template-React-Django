// Top bar for signed-in pages: app name (home), Settings, Sign out.

import { useContext } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';

import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Toolbar from '@mui/material/Toolbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import SettingsRoundedIcon from '@mui/icons-material/SettingsRounded';

import UserContext from '../contexts/UserContext';

export default function AppHeader() {
  const { isLoggedIn, logout } = useContext(UserContext);
  const navigate = useNavigate();

  if (!isLoggedIn) return null;

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <AppBar position="static" color="transparent" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
      <Toolbar variant="dense">
        <Typography
          variant="h6"
          component={RouterLink}
          to="/"
          sx={{ color: 'text.primary', textDecoration: 'none', fontWeight: 600 }}
        >
          Template App
        </Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Settings">
          <IconButton component={RouterLink} to="/settings" aria-label="Settings">
            <SettingsRoundedIcon />
          </IconButton>
        </Tooltip>
        <Tooltip title="Sign out">
          <IconButton onClick={handleLogout} aria-label="Sign out">
            <LogoutRoundedIcon />
          </IconButton>
        </Tooltip>
      </Toolbar>
    </AppBar>
  );
}
