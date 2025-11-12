# Post-Installation Setup

1. **Create a Xero connected app**
   - Register a confidential app in the Xero developer portal.
   - Add your ERPNext site URL as the redirect URI.
   - Capture the client ID and client secret.

2. **Configure `Xero Settings` in ERPNext**
   - Navigate to `Xero Settings`.
   - Populate the client ID, client secret, and desired synchronisation settings.
   - Grant consent by following the OAuth flow.

3. **Map accounts and tax templates**
   - Review the account, tax, and item mappings to ensure they align with your chart of accounts.
   - Use the fixtures to seed default mappings, then adjust per local requirements.

4. **Schedule synchronisation jobs**
   - Enable the background jobs you need (e.g. invoice sync, payment sync) using the Scheduler or by editing the hooks.
   - Optionally trigger an initial sync via the provided server scripts.

5. **Verify permissions**
   - Confirm that the integration user in ERPNext can create and update the necessary DocTypes.
   - Review the Xero connected app scopes to make sure required permissions are enabled.

