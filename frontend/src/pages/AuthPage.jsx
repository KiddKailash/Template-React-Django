import { useState, useContext } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';

import UserContext from '../contexts/UserContext';
import { SnackbarContext } from '../contexts/SnackbarContext';

// MUI
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Container from '@mui/material/Container';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';

// MUI Icons
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';

const AuthPage = () => {
  const navigate = useNavigate();
  const { showSnackbar } = useContext(SnackbarContext);
  const { login, isLoggedIn } = useContext(UserContext);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    const result = await login(username, password);
    setLoading(false);

    if (result.success) {
      showSnackbar('Login successful', 'success');
      navigate('/');
    } else {
      showSnackbar(result.message || 'Login failed', 'error');
    }
  };

  if (isLoggedIn) {
    return <Navigate to="/" />;
  }

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Container maxWidth="xs">
        <Box component="form" noValidate onSubmit={handleLogin} sx={{ p: 4 }}>
          <Stack spacing={2}>
            <Typography variant="h4" align="center" color="primary.main">
              Sign in to Account
            </Typography>

            <TextField
              label="Username"
              required
              fullWidth
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              margin="normal"
            />
            <TextField
              label="Password"
              required
              fullWidth
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              margin="normal"
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPassword(!showPassword)} edge="end">
                      {showPassword ? (
                        <Tooltip title="Hide password">
                          <VisibilityOffIcon />
                        </Tooltip>
                      ) : (
                        <Tooltip title="Show password">
                          <VisibilityIcon />
                        </Tooltip>
                      )}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            <Button
              fullWidth
              variant="contained"
              type="submit"
              size="large"
              disabled={loading || !username || !password}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : 'Login'}
            </Button>
          </Stack>
        </Box>
      </Container>
    </Box>
  );
};

export default AuthPage;
