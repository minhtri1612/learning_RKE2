# ArgoCD Notifications Setup

## Prerequisites

1. Create Slack App: https://api.slack.com/apps
2. Add Bot Token Scopes:
   - `chat:write`
   - `chat:write.public`
3. Install app to workspace
4. Copy Bot User OAuth Token (starts with `xoxb-`)

## Setup

### 1. Create Slack token secret

```bash
kubectl create secret generic argocd-notifications-secret \
  -n argocd \
  --from-literal=slack-token=xoxb-YOUR-SLACK-BOT-TOKEN
```

### 2. Apply notifications ConfigMap

```bash
kubectl apply -f argocd/notifications/argocd-notifications-cm.yaml
```

### 3. Subscribe applications to notifications

Add annotation to Applications:

```yaml
metadata:
  annotations:
    notifications.argoproj.io/subscribe.on-deployed.slack: channel-name
    notifications.argoproj.io/subscribe.on-health-degraded.slack: channel-name
    notifications.argoproj.io/subscribe.on-sync-failed.slack: channel-name
```

Or subscribe all apps in a channel:

```bash
argocd app set <app-name> \
  --annotation notifications.argoproj.io/subscribe.on-deployed.slack=deployments
```

## Testing

### Test notification manually

```bash
kubectl exec -it -n argocd deploy/argocd-notifications-controller -- \
  /app/argocd-notifications trigger on-deployed \
  --app meo-station-backend-dev
```

### Check logs

```bash
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-notifications-controller -f
```

## Triggers Available

- `on-deployed` - Successful deployment
- `on-health-degraded` - App health degraded
- `on-sync-failed` - Sync failed
- `on-sync-running` - Sync started

## Custom Slack Channel per Environment

```yaml
# Dev apps → #dev-deployments
metadata:
  annotations:
    notifications.argoproj.io/subscribe.on-deployed.slack: dev-deployments

# Prod apps → #prod-deployments
metadata:
  annotations:
    notifications.argoproj.io/subscribe.on-deployed.slack: prod-deployments
```
