import { PUSH_STATE } from '../services/push';

/** The line under Settings' push switch, for each PUSH_STATE. */
export function pushDescription(state) {
  switch (state) {
    case PUSH_STATE.UNSUPPORTED:
      return "This browser can't receive push notifications. On iPhone and iPad, add the app to the Home Screen first.";
    case PUSH_STATE.UNCONFIGURED:
      return "Push isn't configured on this server.";
    case PUSH_STATE.DENIED:
      return "Blocked. Allow notifications for this site in your browser's settings.";
    case PUSH_STATE.GRANTED_SUBSCRIBED:
      return "Notifications arrive here instead of by email while you use this device. After 14 days away, they're emailed.";
    case PUSH_STATE.GRANTED_PENDING:
      return 'Permission granted. Turn on to register this device.';
    default:
      return "Get notifications on this device instead of by email while you're using it.";
  }
}
