# Admin Panel Documentation

## Overview

The Admin Panel provides a simple web interface for managing users in the AI Agent Platform. It allows authorized administrators to view, search, and delete users along with all their associated data.

## Features

- 🔍 **User Search** - Search users by email address
- 📊 **User List** - View all users with their details
- 🗑️ **Single User Deletion** - Delete individual users with cascade deletion
- 🔥 **Bulk Deletion** - Delete all users at once (with progress tracking)
- 🔐 **HTTP Basic Auth** - Simple and secure authentication

## Access

### URL
The admin panel is accessible at: **`/ui`**

For example:
- Local development: `http://localhost:8000/ui`
- Production: `https://your-api-gateway.com/ui`

### Authentication

The admin panel uses HTTP Basic Authentication:
- **Username**: Any username (e.g., "admin")
- **Password**: The value of `ADMIN_SECRET_KEY` from your `.env` file

When you navigate to `/ui`, your browser will prompt for credentials. Enter any username and the admin secret key as the password.

## Configuration

### Environment Variables

Add the following to your `.env` file:

```bash
# Admin Panel Secret Key (minimum 12 characters for security)
ADMIN_SECRET_KEY=your-super-secret-admin-key-change-me-in-production

# LiteLLM Master Key (required for deleting user API keys)
LITELLM_MASTER_KEY=sk-your-litellm-master-key
```

**Important:** Without `LITELLM_MASTER_KEY`, user deletion will fail at the LiteLLM key deletion step.

**Security Notes:**
- Use a strong, random key in production (minimum 12 characters)
- Never commit the actual secret key to version control
- Rotate the key periodically for better security
- The default value `change-me-in-production` will trigger a warning

### Generate a Secure Key

You can generate a secure random key using:

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL
openssl rand -base64 32

# Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
```

## User Management

### View All Users

The dashboard displays:
- **Email** - User's email address
- **User ID** - UUID from Supabase Auth
- **Agent ID** - Associated Letta agent ID (if exists)
- **Agent Status** - Current status of the agent
- **Created** - Account creation date
- **Actions** - Delete button for each user

### Search Users

1. Enter an email (or part of it) in the search box
2. Click "Search" or press Enter
3. Matching users will be displayed
4. Click "Show All" to return to the full list

### Delete Single User

**Cascade Deletion Process:**

When you delete a user, the system performs the following steps in order:

1. ✅ Retrieve user data from `user_profiles` table
2. ✅ Delete Letta agent (if exists)
3. ✅ Delete LiteLLM API key (if exists)
4. ✅ Delete LiteLLM internal user (by email)
5. ✅ Delete record from `user_profiles` table
6. ✅ Delete user from Supabase Auth
7. ✅ Clear all caches

**To delete a user:**
1. Click the "Delete" button next to the user
2. Confirm the action in the browser dialog
3. Wait for the deletion to complete
4. The user list will refresh automatically

**Error Handling:**
- If any step fails, the deletion stops and an error is displayed
- Steps that were already completed (like agent deletion) are not rolled back
- 404 errors (resource not found) are treated as success (already deleted)

### Delete All Users

**⚠️ DANGER: This action cannot be undone!**

**To delete all users:**
1. Click the "🗑️ Delete All Users" button
2. Read the confirmation dialog carefully
3. Click "Yes, Delete All" to proceed
4. A progress bar will show the deletion progress
5. If an error occurs, the process stops and shows which user failed

**What gets deleted:**
- All Letta agents
- All LiteLLM API keys
- All LiteLLM internal users
- All user profile records
- All Supabase Auth accounts

**Progress Tracking:**
- Shows number of users deleted (e.g., "5/20")
- Displays percentage complete
- Shows errors with user details if something fails

## API Endpoints

The admin panel uses the following API endpoints (all require admin authentication):

### GET `/api/v1/admin/users`
Get list of all users.

**Response:**
```json
[
  {
    "id": "uuid",
    "email": "user@example.com",
    "name": "User Name",
    "litellm_key": "sk-...",
    "letta_agent_id": "agent_id",
    "agent_status": "active",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  }
]
```

### GET `/api/v1/admin/users/search?q=email`
Search users by email.

**Parameters:**
- `q` - Search query (email substring, case-insensitive)

**Response:** Same as list users

### DELETE `/api/v1/admin/users/{user_id}`
Delete a specific user with cascade deletion.

**Response:**
```json
{
  "status": "success",
  "message": "User {user_id} deleted successfully",
  "result": {
    "user_id": "uuid",
    "email": "user@example.com",
    "letta_agent_deleted": true,
    "litellm_key_deleted": true,
    "profile_deleted": true,
    "auth_deleted": true
  }
}
```

### POST `/api/v1/admin/users/delete-all`
Delete all users (DANGEROUS operation).

**Success Response:**
```json
{
  "status": "success",
  "total": 20,
  "deleted": 20,
  "message": "Successfully deleted all 20 users",
  "results": [...]
}
```

**Error Response (partial deletion):**
```json
{
  "status": "error",
  "total": 20,
  "deleted": 15,
  "failed_at": 16,
  "failed_user_id": "uuid",
  "failed_user_email": "user@example.com",
  "error": "Error message",
  "results": [...]
}
```

## Security Considerations

### Authentication
- Uses HTTP Basic Auth (simple and reliable)
- Admin secret key must be at least 12 characters
- Browser caches credentials for the session
- No session management or cookies needed

### Authorization
- All admin endpoints check for valid admin credentials
- Uses constant-time comparison to prevent timing attacks
- Invalid credentials return 401 with `WWW-Authenticate` header

### Audit Logging
- All admin actions are logged with structured logging
- Logs include: admin username, action, user ID, timestamp
- Check application logs for audit trail

### Best Practices
1. **Use Strong Keys**: Generate random, long keys (32+ characters)
2. **Rotate Keys**: Change the admin secret key periodically
3. **Limit Access**: Only share credentials with trusted administrators
4. **Monitor Logs**: Regularly review admin action logs
5. **HTTPS Only**: Always use HTTPS in production to protect credentials
6. **IP Whitelist**: Consider restricting admin panel access by IP (via reverse proxy)

## Troubleshooting

### Cannot Access Admin Panel

**Problem:** Browser shows 401 Unauthorized

**Solutions:**
1. Verify `ADMIN_SECRET_KEY` is set in `.env`
2. Check you're using the correct password (copy-paste to avoid typos)
3. Clear browser cache and try again
4. Check application logs for authentication errors

### Users Not Loading

**Problem:** Empty table or loading spinner never ends

**Solutions:**
1. Check browser console for JavaScript errors
2. Verify API endpoints are working: `GET /api/v1/admin/users`
3. Check Supabase connection and credentials
4. Review application logs for errors

### Deletion Fails

**Problem:** User deletion returns an error

**Common Issues:**
1. **Letta Agent Not Found**: Agent may already be deleted (404 is OK)
2. **LiteLLM Key Invalid**: Key may already be deleted (404 is OK)
3. **Supabase Auth Error**: Check service key permissions
4. **Network Timeout**: Increase `REQUEST_TIMEOUT` in settings

**Steps:**
1. Check which step failed in the error message
2. Review application logs for detailed error
3. Manually verify if resources still exist
4. Retry the deletion (idempotent operations)

## Development

### Local Setup

1. Set environment variable:
```bash
ADMIN_SECRET_KEY=dev-admin-key-12345
```

2. Start the application:
```bash
python -m uvicorn src.main:app --reload
```

3. Access admin panel:
```
http://localhost:8000/ui
Username: admin
Password: dev-admin-key-12345
```

### Testing

Test API endpoints with curl:

```bash
# List all users
curl -u admin:your-secret-key http://localhost:8000/api/v1/admin/users

# Search users
curl -u admin:your-secret-key "http://localhost:8000/api/v1/admin/users/search?q=test"

# Delete user
curl -u admin:your-secret-key -X DELETE http://localhost:8000/api/v1/admin/users/{user_id}

# Delete all users (DANGEROUS)
curl -u admin:your-secret-key -X POST http://localhost:8000/api/v1/admin/users/delete-all
```

## Architecture

### Components

```
src/
├── routers/
│   ├── admin_ui.py       # HTML page rendering
│   └── admin_api.py      # REST API endpoints
├── services/
│   ├── admin_service.py  # Business logic (deletion, search)
│   └── litellm_client.py # LiteLLM API client
├── dependencies/
│   └── admin_auth.py     # HTTP Basic Auth verification
└── templates/
    └── admin_dashboard.html  # Single-page admin interface
```

### Data Flow

**User List:**
```
Browser → GET /ui → admin_dashboard.html
         → GET /api/v1/admin/users → Supabase → Response
```

**User Deletion:**
```
Browser → DELETE /api/v1/admin/users/{id}
         → AdminService.delete_user_cascade()
            1. Get user data (Supabase)
            2. Delete Letta agent (Letta API)
            3. Delete LiteLLM key (LiteLLM API)
            4. Delete user_profiles (Supabase)
            5. Delete auth user (Supabase Admin API)
            6. Clear caches (Redis)
         → Success/Error Response
```

## Future Enhancements

Potential improvements for future versions:

- [ ] User activity logs and statistics
- [ ] Soft delete with restore capability
- [ ] Bulk operations (delete selected users)
- [ ] Export user data (CSV/JSON)
- [ ] User filtering (by date, agent status, etc.)
- [ ] Admin user management (multiple admins with roles)
- [ ] Two-factor authentication (2FA)
- [ ] Audit log viewer in UI
- [ ] Pagination for large user lists
- [ ] Real-time updates with WebSockets

